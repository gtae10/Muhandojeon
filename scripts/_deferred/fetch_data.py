"""외부 데이터셋 획득 스크립트.

`data/raw/` 아래에 원본을 내려받는다. Kaggle API(`kaggle` CLI + `~/.kaggle/kaggle.json`)를 쓰고,
인증/권한/네트워크 실패 시에는 **수동 다운로드 안내를 출력한 뒤 합성 폴백으로 넘긴다.**
어떤 경우에도 크래시하지 않는다(항상 exit 0). 결과는 `data/raw/FETCH_STATUS.json`에 기록된다.

사용법:
    python scripts/fetch_data.py                 # 전체 (필수 3종)
    python scripts/fetch_data.py --only fashion  # 하나만
    python scripts/fetch_data.py --skip-large    # H&M transactions(3.5GB) 건너뛰기

MVTec AD는 CC BY-NC-SA 4.0(비상업)이므로 자동 다운로드하지 않는다. `data/raw/mvtec/`에
수동으로 놓였을 때만 인식한다. 자세한 내용은 docs/DATA_LICENSES.md 참고.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
STATUS_PATH = RAW / "FETCH_STATUS.json"

Kind = Literal["competition", "dataset", "manual"]


@dataclass
class Source:
    """하나의 외부 데이터셋 정의."""

    key: str
    kind: Kind
    identifier: str
    purpose: str
    required: bool
    #: 이 파일들이 data/raw/<key>/ 아래에 (재귀적으로) 존재하면 획득 완료로 본다.
    sentinels: list[str]
    #: competition 전용. 지정하면 해당 파일만 내려받는다(전체 25GB 회피).
    files: list[str] = field(default_factory=list)
    large: bool = False
    manual_url: str = ""
    note: str = ""

    @property
    def dest(self) -> Path:
        return RAW / self.key


SOURCES: list[Source] = [
    Source(
        key="hm",
        kind="competition",
        identifier="h-and-m-personalized-fashion-recommendations",
        purpose="고객·거래 이력 (3천만 행 트랜잭션)",
        required=True,
        sentinels=["transactions_train.csv"],
        files=["transactions_train.csv", "articles.csv"],
        large=True,
        manual_url=(
            "https://www.kaggle.com/competitions/h-and-m-personalized-fashion-recommendations/data"
        ),
        note="competition 데이터는 웹에서 대회 규칙(Rules) 수락이 먼저 필요하다.",
    ),
    Source(
        key="fashion",
        kind="dataset",
        identifier="paramaggarwal/fashion-product-images-small",
        purpose="상품 카탈로그 + 이미지",
        required=True,
        sentinels=["styles.csv"],
        manual_url="https://www.kaggle.com/datasets/paramaggarwal/fashion-product-images-small",
    ),
    Source(
        key="clickstream",
        kind="dataset",
        identifier="waqi786/e-commerce-clickstream-and-transaction-dataset",
        purpose="세션 클릭스트림",
        required=True,
        sentinels=["ecommerce_clickstream_transactions.csv"],
        manual_url=(
            "https://www.kaggle.com/datasets/waqi786/e-commerce-clickstream-and-transaction-dataset"
        ),
    ),
    Source(
        key="mvtec",
        kind="manual",
        identifier="MVTec AD (leather, carpet)",
        purpose="결함 텍스처 참고 (컨디션 소견 시각 자료)",
        required=False,
        sentinels=["leather", "carpet"],
        manual_url="https://www.mvtec.com/company/research/datasets/mvtec-ad",
        note="CC BY-NC-SA 4.0 — 상업적 사용 금지. 연구/데모 목적으로만, 수동 배치 시에만 사용.",
    ),
]


def log(msg: str) -> None:
    print(msg, flush=True)


def found_sentinels(src: Source) -> list[str]:
    """dest 아래에서 sentinel 이름을 재귀 탐색해 실제 존재하는 것만 반환."""
    if not src.dest.exists():
        return []
    hits: list[str] = []
    for name in src.sentinels:
        matches = list(src.dest.rglob(name))
        if matches:
            hits.append(str(matches[0].relative_to(RAW)))
    return hits


def kaggle_available() -> tuple[bool, str]:
    exe = shutil.which("kaggle")
    if exe is None:
        return False, "`kaggle` CLI 를 찾을 수 없음 (pip install kaggle)"
    cred = Path.home() / ".kaggle" / "kaggle.json"
    if (
        not cred.exists() and not (Path.cwd() / "kaggle.json").exists()
    ):  # pragma: no cover - 환경 의존
        return False, f"{cred} 자격증명 파일이 없음"
    return True, exe


def run_kaggle(args: list[str], timeout: float) -> tuple[bool, str]:
    """kaggle CLI 호출. (성공여부, 출력) 반환. 예외를 밖으로 던지지 않는다."""
    try:
        proc = subprocess.run(  # noqa: S603 - 고정 커맨드
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"타임아웃({timeout:.0f}s) — {' '.join(args)}"
    except OSError as exc:  # pragma: no cover
        return False, f"실행 실패: {exc}"
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, out.strip()


def unzip_all(dest: Path) -> list[str]:
    """dest 안의 zip 을 모두 풀고 원본 zip 을 지운다. 풀린 zip 이름 목록 반환."""
    done: list[str] = []
    for zp in sorted(dest.glob("*.zip")):
        try:
            with zipfile.ZipFile(zp) as zf:
                zf.extractall(dest)
            zp.unlink()
            done.append(zp.name)
        except (zipfile.BadZipFile, OSError) as exc:
            log(f"  ! zip 해제 실패 {zp.name}: {exc}")
    return done


def manual_instructions(src: Source) -> str:
    lines = [
        f"  수동 다운로드 안내 [{src.key}]",
        f"    URL   : {src.manual_url}",
        f"    배치  : {src.dest.relative_to(ROOT)}/ 아래에 압축 해제",
        f"    확인  : {', '.join(src.sentinels)} 파일/폴더가 보이면 완료",
    ]
    if src.note:
        lines.append(f"    주의  : {src.note}")
    return "\n".join(lines)


def fetch_one(src: Source, timeout: float) -> dict[str, object]:
    """한 소스를 획득한다. 결과 dict 를 반환하며 예외를 던지지 않는다."""
    result: dict[str, object] = {
        "key": src.key,
        "identifier": src.identifier,
        "purpose": src.purpose,
        "required": src.required,
        "kind": src.kind,
    }
    src.dest.mkdir(parents=True, exist_ok=True)

    hits = found_sentinels(src)
    if hits:
        log(f"[{src.key}] 이미 존재 → 건너뜀 ({', '.join(hits)})")
        result |= {"status": "present", "files": hits}
        return result

    if src.kind == "manual":
        log(f"[{src.key}] 선택 데이터셋 없음 → 건너뜀 (수동 배치 시에만 사용)")
        log(manual_instructions(src))
        result |= {"status": "absent-optional", "files": []}
        return result

    ok, exe_or_msg = kaggle_available()
    if not ok:
        log(f"[{src.key}] Kaggle 사용 불가: {exe_or_msg}")
        log(manual_instructions(src))
        result |= {"status": "auth-failed", "error": exe_or_msg, "files": []}
        return result

    exe = exe_or_msg
    if src.kind == "competition" and src.files:
        cmds = [
            [exe, "competitions", "download", "-c", src.identifier, "-f", f, "-p", str(src.dest)]
            for f in src.files
        ]
    elif src.kind == "competition":
        cmds = [[exe, "competitions", "download", "-c", src.identifier, "-p", str(src.dest)]]
    else:
        cmds = [[exe, "datasets", "download", "-d", src.identifier, "-p", str(src.dest)]]

    errors: list[str] = []
    for cmd in cmds:
        log(f"[{src.key}] $ {' '.join(cmd)}")
        succeeded, out = run_kaggle(cmd, timeout=timeout)
        tail = "\n".join(out.splitlines()[-4:])
        if not succeeded:
            errors.append(tail)
            log(f"  ! 실패: {tail}")
        else:
            log(f"  ok: {tail or '(출력 없음)'}")
        unzip_all(src.dest)

    unzip_all(src.dest)
    hits = found_sentinels(src)
    if hits:
        size_mb = sum(p.stat().st_size for p in src.dest.rglob("*") if p.is_file()) / 1e6
        log(f"[{src.key}] 완료 — {len(hits)}개 sentinel, {size_mb:,.0f} MB")
        result |= {"status": "downloaded", "files": hits, "size_mb": round(size_mb, 1)}
        return result

    log(f"[{src.key}] 획득 실패 → 합성 폴백 대상")
    log(manual_instructions(src))
    result |= {"status": "failed", "files": [], "error": "; ".join(errors)[:2000]}
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="외부 데이터셋 획득 (실패 시 합성 폴백 안내)")
    ap.add_argument("--only", action="append", default=[], help="지정한 key 만 처리")
    ap.add_argument("--skip-large", action="store_true", help="대용량(H&M transactions) 건너뛰기")
    ap.add_argument("--timeout", type=float, default=3600.0, help="소스별 다운로드 타임아웃(초)")
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    targets = [s for s in SOURCES if not args.only or s.key in args.only]
    if args.skip_large:
        targets = [s for s in targets if not s.large]

    results = [fetch_one(s, timeout=args.timeout) for s in targets]

    # 소스별 가용성을 개별로 본다. 하나가 없더라도 나머지는 원본으로 만들고,
    # 없는 슬라이스만 합성으로 채운다(빌더가 각자 판단하며 PROVENANCE 에 기록된다).
    required = [r for r in results if r["required"] is True]
    ok_keys = [str(r["key"]) for r in required if r["status"] in {"present", "downloaded"}]
    if required and len(ok_keys) == len(required):
        data_source = "external"
    elif ok_keys:
        data_source = "partial-external"
    else:
        data_source = "synth"

    status = {
        "data_source_recommendation": data_source,
        "available": ok_keys,
        "sources": results,
    }
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    log("")
    log("─" * 60)
    for r in results:
        log(f"  {r['key']:<12} {r['status']:<16} {r['purpose']}")
    log(f"  → 권장 DATA_SOURCE = {data_source} (확보: {', '.join(ok_keys) or '없음'})")
    if data_source == "synth":
        log("    필수 데이터셋이 없어 합성 폴백을 사용한다: python scripts/synth_fallback.py")
    elif data_source == "partial-external":
        missing = [str(r["key"]) for r in required if str(r["key"]) not in ok_keys]
        log(f"    없는 슬라이스({', '.join(missing)})만 합성으로 채운다. 빌더가 자동 처리한다.")
    log(f"  상태 기록: {STATUS_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
