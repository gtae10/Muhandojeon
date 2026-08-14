"""개체 지문 등록 CLI — 촬영 이미지 품질 검증 + 경로 등록.

개체 지문용 공개 데이터셋은 존재하지 않는다(같은 모델 두 개를 구분하는 미세 텍스처 데이터셋은
공개된 게 없다). 팀원 소지품 직접 촬영이 유일한 방법이므로, **촬영 규약과 등록 CLI를 미리
만들어 둔다.** 임베딩 추출은 백엔드 담당 몫이라 여기서는 경로 등록과 품질 검증까지만 한다.

디렉토리 규약
    data/fingerprints/{asset_id}/{angle}_{index}.jpg
    예: data/fingerprints/AS-000031/handle_01.jpg

품질 판정 (기준 미달은 재촬영 대상으로 리스트업)
    - 해상도   : 짧은 변 800px 이상
    - 블러     : 라플라시안 분산 60 이상 (낮으면 흐림)
    - 밝기     : 평균 60~200 (0~255)
    - 대비     : 표준편차 18 이상
    - 과노출   : 250 초과 픽셀 비율 12% 미만

    python -m scripts.register_fingerprint data/fingerprints/AS-000031
    python -m scripts.register_fingerprint --all
    python -m scripts.register_fingerprint --all --dry-run
    python -m scripts.register_fingerprint --make-sample AS-000031   # 규약 확인용 샘플 생성
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from app.config import FINGERPRINT_DIR, ROOT
from app.db import init_db, session_scope
from app.domain import CAPTURE_ANGLES
from app.models import AssetRow, FingerprintRow
from contracts.common import ProductCategory
from scripts.common import REFERENCE_NOW, banner

MIN_SHORT_SIDE = 800
MIN_BLUR_VAR = 60.0
BRIGHTNESS_RANGE = (60.0, 200.0)
MIN_BRIGHTNESS_STD = 18.0
MAX_CLIPPED_RATIO = 0.12

FILENAME_RE = re.compile(r"^(?P<angle>[a-z]+)_(?P<index>\d+)\.(jpe?g|png)$", re.IGNORECASE)
VALID_SUFFIXES = {".jpg", ".jpeg", ".png"}


@dataclass
class Quality:
    """이미지 1장의 품질 측정 결과."""

    path: Path
    angle: str
    seq: int
    width: int
    height: int
    blur_score: float
    brightness: float
    brightness_std: float
    clipped_ratio: float
    problems: list[str]

    @property
    def passed(self) -> bool:
        return not self.problems

    @property
    def reason(self) -> str:
        return "; ".join(self.problems)


def laplacian_variance(gray: np.ndarray) -> float:
    """라플라시안 분산 = 선명도 지표. 3x3 커널을 슬라이싱으로 직접 적용한다(scipy 의존 없음)."""
    center = gray[1:-1, 1:-1]
    lap = 4.0 * center - gray[:-2, 1:-1] - gray[2:, 1:-1] - gray[1:-1, :-2] - gray[1:-1, 2:]
    return float(lap.var())


def measure(path: Path, angle: str, seq: int) -> Quality:
    """이미지 1장을 측정하고 기준 미달 항목을 모은다."""
    with Image.open(path) as img:
        rgb = img.convert("RGB")
        width, height = rgb.size
        gray = np.asarray(rgb.convert("L"), dtype=np.float64)

    blur = laplacian_variance(gray) if min(gray.shape) > 2 else 0.0
    brightness = float(gray.mean())
    brightness_std = float(gray.std())
    clipped = float((gray > 250).mean())

    problems: list[str] = []
    if min(width, height) < MIN_SHORT_SIDE:
        problems.append(f"해상도 부족 ({width}x{height}, 짧은 변 {MIN_SHORT_SIDE}px 이상 필요)")
    if blur < MIN_BLUR_VAR:
        problems.append(f"흐림 (라플라시안 분산 {blur:.1f} < {MIN_BLUR_VAR})")
    if not BRIGHTNESS_RANGE[0] <= brightness <= BRIGHTNESS_RANGE[1]:
        problems.append(
            f"밝기 이탈 (평균 {brightness:.0f}, 허용 "
            f"{BRIGHTNESS_RANGE[0]:.0f}~{BRIGHTNESS_RANGE[1]:.0f})"
        )
    if brightness_std < MIN_BRIGHTNESS_STD:
        problems.append(f"대비 부족 (표준편차 {brightness_std:.1f} < {MIN_BRIGHTNESS_STD})")
    if clipped > MAX_CLIPPED_RATIO:
        problems.append(f"과노출 (250 초과 픽셀 {clipped:.0%} > {MAX_CLIPPED_RATIO:.0%})")

    return Quality(
        path=path,
        angle=angle,
        seq=seq,
        width=width,
        height=height,
        blur_score=blur,
        brightness=brightness,
        brightness_std=brightness_std,
        clipped_ratio=clipped,
        problems=problems,
    )


def scan_asset_dir(directory: Path) -> tuple[list[Quality], list[str]]:
    """한 개체 디렉토리의 이미지를 검증한다. (측정결과, 규약 위반 메시지)"""
    results: list[Quality] = []
    violations: list[str] = []
    for path in sorted(directory.iterdir()):
        if path.is_dir():
            continue
        if path.suffix.lower() not in VALID_SUFFIXES:
            violations.append(f"{path.name}: 지원하지 않는 확장자 (jpg/jpeg/png 만)")
            continue
        match = FILENAME_RE.match(path.name)
        if match is None:
            violations.append(f"{path.name}: 파일명 규약 위반 ({{angle}}_{{index}}.jpg 형식)")
            continue
        try:
            results.append(measure(path, match.group("angle").lower(), int(match.group("index"))))
        except OSError as exc:
            violations.append(f"{path.name}: 이미지 열기 실패 ({exc})")
    return results, violations


def repo_relative(path: Path) -> str:
    """레포 루트 기준 상대 경로 문자열. 밖에 있으면 절대 경로를 그대로 쓴다."""
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def expected_angles(category: str) -> tuple[str, ...]:
    try:
        return CAPTURE_ANGLES[ProductCategory(category)]
    except ValueError:  # pragma: no cover - 알 수 없는 카테고리
        return ()


def register(directory: Path, dry_run: bool) -> tuple[int, int]:
    """디렉토리 하나를 검증하고 통과분만 DB 에 등록한다. (통과, 실패) 반환."""
    directory = directory.resolve()
    asset_id = directory.name
    with session_scope() as db:
        asset = db.get(AssetRow, asset_id)
        if asset is None:
            print(f"  ! {asset_id}: 등록되지 않은 개체 id (assets 테이블에 없음) → 건너뜀")
            return 0, 0
        category = asset.category
        product_name = asset.product_name

    results, violations = scan_asset_dir(directory)
    angles = expected_angles(category)
    print(f"\n  [{asset_id}] {product_name} ({category}) — 이미지 {len(results)}장")
    for message in violations:
        print(f"    ! {message}")

    passed = [q for q in results if q.passed]
    failed = [q for q in results if not q.passed]

    for q in results:
        mark = "ok  " if q.passed else "재촬영"
        angle_note = "" if not angles or q.angle in angles else f" (권장 부위 아님: {angles})"
        print(
            f"    {mark} {q.path.name:<18} {q.width}x{q.height} "
            f"blur={q.blur_score:6.1f} bright={q.brightness:5.1f}±{q.brightness_std:4.1f}"
            f"{angle_note}"
        )
        if not q.passed:
            print(f"         → {q.reason}")

    missing_angles = [a for a in angles if not any(q.angle == a and q.passed for q in passed)]
    if missing_angles:
        print(f"    ! 부위 누락(통과분 기준): {', '.join(missing_angles)}")

    if dry_run:
        print("    --dry-run → DB 등록 생략")
        return len(passed), len(failed)

    with session_scope() as db:
        for q in results:
            rel = repo_relative(q.path)
            existing = db.query(FingerprintRow).filter(FingerprintRow.path == rel).one_or_none()
            row = existing or FingerprintRow(path=rel)
            row.asset_id = asset_id
            row.angle = q.angle
            row.seq = q.seq
            row.width = q.width
            row.height = q.height
            row.blur_score = round(q.blur_score, 2)
            row.brightness = round(q.brightness, 2)
            row.brightness_std = round(q.brightness_std, 2)
            row.passed = q.passed
            row.reason = q.reason[:200]
            row.registered_at = REFERENCE_NOW
            db.add(row)
        # 통과 이미지가 하나라도 있으면 스캔 시각을 갱신한다.
        if passed:
            asset_row = db.get(AssetRow, asset_id)
            if asset_row is not None:
                asset_row.last_scanned_at = REFERENCE_NOW
    return len(passed), len(failed)


def make_sample(asset_id: str) -> None:
    """규약 확인용 샘플 디렉토리 생성. 실제 촬영 전에 경로/파일명을 눈으로 확인하는 용도."""
    with session_scope() as db:
        asset = db.get(AssetRow, asset_id)
        category = asset.category if asset else ProductCategory.BAG.value
    angles = expected_angles(category) or ("surface",)
    target = FINGERPRINT_DIR / asset_id
    target.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)
    for angle in angles:
        for idx in (1, 2):
            # 미세 텍스처를 흉내낸 노이즈 + 완만한 조명 그라디언트 (선명도 기준을 통과한다)
            base = rng.integers(70, 190, size=(1200, 1200), dtype=np.uint8)
            gradient = np.linspace(-20, 20, 1200, dtype=np.float64)
            arr = np.clip(base + gradient[None, :], 0, 255).astype(np.uint8)
            Image.fromarray(arr, mode="L").convert("RGB").save(
                target / f"{angle}_{idx:02d}.jpg", quality=92
            )
    print(f"  샘플 생성: {target} ({len(angles) * 2}장)")
    print("  → 실제 촬영본으로 교체한 뒤 다시 등록하라. 촬영 가이드: docs/FINGERPRINT_CAPTURE.md")


def main() -> int:
    ap = argparse.ArgumentParser(description="개체 지문 이미지 품질 검증 + 등록")
    ap.add_argument("directory", nargs="?", help="개체 디렉토리 (data/fingerprints/AS-xxxxxx)")
    ap.add_argument("--all", action="store_true", help="data/fingerprints/ 전체 처리")
    ap.add_argument("--dry-run", action="store_true", help="검증만 하고 DB 에 쓰지 않는다")
    ap.add_argument("--make-sample", metavar="ASSET_ID", help="규약 확인용 샘플 이미지 생성")
    args = ap.parse_args()

    banner("개체 지문 등록")
    init_db()

    if args.make_sample:
        make_sample(args.make_sample)
        return 0

    targets: list[Path] = []
    if args.all:
        if not FINGERPRINT_DIR.exists():
            print(f"  {FINGERPRINT_DIR} 가 없다. 촬영 규약: docs/FINGERPRINT_CAPTURE.md")
            print("  샘플로 규약을 확인하려면: --make-sample AS-000001")
            return 0
        targets = sorted(p for p in FINGERPRINT_DIR.iterdir() if p.is_dir())
    elif args.directory:
        targets = [Path(args.directory)]
    else:
        ap.error("디렉토리 또는 --all 이 필요하다")

    if not targets:
        print(f"  처리할 개체 디렉토리가 없다 ({FINGERPRINT_DIR})")
        return 0

    total_pass = total_fail = 0
    for directory in targets:
        if not directory.exists():
            print(f"  ! {directory} 없음")
            continue
        ok, bad = register(directory, dry_run=args.dry_run)
        total_pass += ok
        total_fail += bad

    print(f"\n  합계 — 통과 {total_pass}장 / 재촬영 {total_fail}장")
    if total_fail:
        print("  재촬영 항목은 위 목록의 '재촬영' 표시를 참고하라")
    return 0


if __name__ == "__main__":
    sys.exit(main())
