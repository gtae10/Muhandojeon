"""
app/services/intent_service.py
AI1 연동 지점 - 이미지 분석 → 컨디션 점수 산출

현재: 목업 데이터 반환
교체 지점: analyze_texture() 함수 내부 로직만 실제 AI1 모델 호출로 바꾸면 됨
"""
import random
from app.schemas.models import WearDetail


async def analyze_texture(image_bytes: bytes, product_id: str) -> dict:
    """
    AI1 연동 함수.

    Args:
        image_bytes: 업로드된 이미지 바이너리
        product_id: 분석 대상 상품 ID

    Returns:
        {
            "condition_score": int (1~100),
            "condition_grade": str,
            "wear_detail": WearDetail,
            "summary": str,
        }

    TODO (AI1 담당):
        - image_bytes를 AI1 모델 서버로 전달
        - 모델 응답에서 score, wear_detail 파싱
        - 아래 목업 return 값을 실제 모델 결과로 교체
    """
    # ── 목업 구간 (AI1 연동 전까지 사용) ──────────────────
    score = random.randint(40, 95)
    grade = _score_to_grade(score)
    severity = (100 - score) / 100

    wear = WearDetail(
        scratches=int(severity * 8),
        cracks=int(severity * 2),
        color_fade=severity > 0.4,
        hardware_tarnish=severity > 0.3,
        lining_damage=severity > 0.5,
        strap_wear=severity > 0.35,
    )

    summary = (
        f"분석 결과 컨디션 점수 {score}점({grade})입니다. "
        f"스크래치 {wear.scratches}개가 감지되었으며, "
        + ("크랙이 발견되었습니다. " if wear.cracks else "크랙은 없습니다. ")
        + ("하드웨어 변색이 시작되었습니다." if wear.hardware_tarnish else "하드웨어 상태는 양호합니다.")
    )
    # ── 목업 구간 끝 ────────────────────────────────────────

    return {
        "condition_score": score,
        "condition_grade": grade,
        "wear_detail": wear,
        "summary": summary,
    }


def _score_to_grade(score: int) -> str:
    if score >= 90: return "Mint"
    if score >= 75: return "Excellent"
    if score >= 55: return "Good"
    if score >= 30: return "Fair"
    return "Poor"
