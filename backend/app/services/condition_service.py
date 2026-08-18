"""
app/services/condition_service.py
OpenCV 기반 컨디션 점수 분석 서비스 (백엔드 담당).

docs/BACKEND_INTEGRATION.md 및 docs/INTEGRATION.md 에 따라:
- 비전 API(LLM)는 사용하지 않는다 → 고전 CV(OpenCV)로 구현
- 계약: POST /condition/score
  입력: {asset_id, image_paths[]}
  출력: {asset_id, score, findings[], next_service_months, confidence}

분석 전략:
    이미지 있음 → ORB 특징점 기반 텍스처 분석 (마모 지수 추출)
    이미지 없음 → fixture_provider 에서 마지막 스캔 결과 반환
"""

from __future__ import annotations

import base64
import io
import logging
import math
from pathlib import Path
from typing import Any

from app.data.fixture_provider import get_asset

logger = logging.getLogger(__name__)

# OpenCV 는 선택적 의존성. 없으면 목업으로 폴백.
try:
    import cv2
    import numpy as np
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False
    logger.warning(
        "opencv-python-headless 가 설치되지 않았습니다. "
        "컨디션 분석이 픽스처 데이터로 폴백됩니다."
    )

_REPO_ROOT = Path(__file__).resolve().parents[3]  # Muhandojeon/


def _load_image_bytes(image_path: str) -> bytes | None:
    """경로 기반 이미지 로드. 절대/상대 경로 모두 처리."""
    # 절대 경로 시도
    p = Path(image_path)
    if not p.is_absolute():
        p = _REPO_ROOT / image_path
    if p.exists():
        return p.read_bytes()
    return None


def _analyze_image_cv2(image_bytes: bytes) -> dict[str, float]:
    """
    OpenCV ORB 기반 텍스처 복잡도 분석.
    특징점이 많을수록 텍스처가 복잡/풍부 → 상태 양호.
    마모된 표면은 결 손실 → 특징점 수 감소.

    Returns:
        {
          "texture_score": float,   # 0~1, 1=신품급
          "edge_density": float,    # 엣지 밀도 0~1
          "brightness_std": float,  # 밝기 표준편차
        }
    """
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return {"texture_score": 0.8, "edge_density": 0.5, "brightness_std": 30.0}

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 1) ORB 특징점 수 (마모 지표)
    orb = cv2.ORB_create(nfeatures=1000)
    kp, _ = orb.detectAndCompute(gray, None)
    kp_count = len(kp)
    texture_score = min(kp_count / 500.0, 1.0)  # 500개 = 만점 기준

    # 2) Canny 엣지 밀도 (스크래치·균열 지표)
    edges = cv2.Canny(gray, 50, 150)
    edge_density = edges.mean() / 255.0

    # 3) 밝기 표준편차 (색 바램 지표)
    brightness_std = float(gray.std())

    return {
        "texture_score": texture_score,
        "edge_density": edge_density,
        "brightness_std": brightness_std,
    }


def _metrics_to_condition(metrics_list: list[dict]) -> dict[str, Any]:
    """
    복수 이미지의 분석 지표를 통합해 컨디션 점수로 변환.

    점수 구성 (0~100):
        - 텍스처 점수 (50점 비중): 마모 심할수록 감소
        - 엣지 밀도 패널티 (30점): 과도한 엣지=스크래치
        - 밝기 안정성 (20점): 표준편차 크면 색 바램
    """
    if not metrics_list:
        return {"score": 75, "findings": [], "confidence": 0.5}

    avg_texture = sum(m["texture_score"] for m in metrics_list) / len(metrics_list)
    avg_edge = sum(m["edge_density"] for m in metrics_list) / len(metrics_list)
    avg_brightness_std = sum(m["brightness_std"] for m in metrics_list) / len(metrics_list)

    # 텍스처 (신품급 기준)
    texture_component = avg_texture * 50  # 0~50

    # 엣지 패널티 (엣지 밀도 0.3 이하면 정상, 높을수록 스크래치)
    edge_penalty = max(0.0, avg_edge - 0.15) * 100  # 0~30 패널티
    edge_component = max(0.0, 30 - edge_penalty)

    # 밝기 안정성 (std 20 이하=양호, 50 이상=불량)
    brightness_norm = max(0.0, 1.0 - (avg_brightness_std - 20) / 80)
    brightness_component = brightness_norm * 20  # 0~20

    raw_score = texture_component + edge_component + brightness_component
    score = max(0, min(100, int(raw_score)))

    # findings 생성
    findings: list[dict] = []
    if avg_edge > 0.3:
        findings.append({
            "part": "exterior",
            "severity": "HIGH" if avg_edge > 0.5 else "MEDIUM",
            "note": f"표면 스크래치/균열 감지 (엣지 밀도 {avg_edge:.2f})",
        })
    if avg_texture < 0.4:
        findings.append({
            "part": "exterior",
            "severity": "MEDIUM",
            "note": f"가죽 결 마모 진행 (텍스처 지수 {avg_texture:.2f})",
        })
    if avg_brightness_std > 50:
        findings.append({
            "part": "exterior",
            "severity": "LOW",
            "note": f"색상 불균일, 색 바램 의심 (편차 {avg_brightness_std:.1f})",
        })

    confidence = min(0.95, 0.5 + len(metrics_list) * 0.15)

    return {
        "score": score,
        "findings": findings,
        "confidence": round(confidence, 2),
    }


def _next_service_months(score: int) -> int:
    """
    컨디션 점수로 케어 권장 시점(월) 계산.
    docs/CONTRACTS.md: '컨디션 70 이 케어 권장 임계값'
    연 8점 감소 가정 (docs/BACKEND_INTEGRATION.md).
    """
    if score <= 70:
        return 0
    # 70점까지 남은 점수 / 월당 감소율(약 0.67점/월)
    months = math.ceil((score - 70) / (8 / 12))
    return max(0, months)


# ──────────────────────────────────────────────
# 공개 API
# ──────────────────────────────────────────────

async def score_condition(asset_id: str, image_paths: list[str]) -> dict[str, Any]:
    """
    컨디션 점수 산출.

    Args:
        asset_id: 대상 개체 id
        image_paths: 스캔 이미지 경로 목록. 비어 있으면 픽스처 반환.

    Returns:
        ConditionScoreResponse 형식 dict:
        {asset_id, score, findings, next_service_months, confidence}
    """
    # 이미지 없음 → 픽스처 데이터 반환
    if not image_paths or not _CV2_AVAILABLE:
        return _fallback_from_fixture(asset_id)

    # OpenCV 분석
    metrics_list: list[dict] = []
    for img_path in image_paths:
        img_bytes = _load_image_bytes(img_path)
        if img_bytes:
            try:
                m = _analyze_image_cv2(img_bytes)
                metrics_list.append(m)
            except Exception as exc:
                logger.warning("이미지 분석 실패 [%s]: %s", img_path, exc)

    if not metrics_list:
        # 이미지를 불러왔지만 전부 실패 → 픽스처 폴백
        return _fallback_from_fixture(asset_id)

    result = _metrics_to_condition(metrics_list)
    score = result["score"]

    return {
        "asset_id": asset_id,
        "score": score,
        "findings": result["findings"],
        "next_service_months": _next_service_months(score),
        "confidence": result["confidence"],
    }


async def score_condition_from_base64(asset_id: str, images_b64: list[str]) -> dict[str, Any]:
    """base64 인코딩 이미지로 컨디션 분석."""
    if not images_b64 or not _CV2_AVAILABLE:
        return _fallback_from_fixture(asset_id)

    metrics_list: list[dict] = []
    for b64 in images_b64:
        try:
            img_bytes = base64.b64decode(b64)
            m = _analyze_image_cv2(img_bytes)
            metrics_list.append(m)
        except Exception as exc:
            logger.warning("base64 이미지 분석 실패: %s", exc)

    if not metrics_list:
        return _fallback_from_fixture(asset_id)

    result = _metrics_to_condition(metrics_list)
    score = result["score"]

    return {
        "asset_id": asset_id,
        "score": score,
        "findings": result["findings"],
        "next_service_months": _next_service_months(score),
        "confidence": result["confidence"],
    }


def _fallback_from_fixture(asset_id: str) -> dict[str, Any]:
    """
    이미지 없거나 OpenCV 미설치 시 픽스처 데이터로 폴백.
    fixtures/assets.json 의 condition_score 와 findings 를 그대로 반환.
    """
    asset = get_asset(asset_id)
    if not asset:
        return {
            "asset_id": asset_id,
            "score": 75,
            "findings": [],
            "next_service_months": 6,
            "confidence": 0.5,
        }

    score = asset.get("condition_score", 75)
    findings = asset.get("findings", [])
    nsm = asset.get("next_service_months", _next_service_months(score))

    return {
        "asset_id": asset_id,
        "score": score,
        "findings": findings,
        "next_service_months": nsm,
        "confidence": 0.8,  # 픽스처 = 사람이 직접 지정한 값이므로 높은 신뢰도
    }
