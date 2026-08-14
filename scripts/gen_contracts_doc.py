"""계약 문서 생성기 — `contracts/` → `docs/CONTRACTS.md` + `contracts/examples/*.json`.

계약을 바꿨으면 문서를 손으로 고치지 말고 이 스크립트를 다시 돌린다(`make contracts`).
예시 페이로드는 **모델로 검증한 뒤** 저장하므로, 예시가 계약과 어긋나면 여기서 바로 실패한다.

사용법:
    python scripts/gen_contracts_doc.py
    python scripts/gen_contracts_doc.py --check   # 재생성 없이 예시 유효성만 검사
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import inspect
import json
import sys
import textwrap
import types
import typing
from enum import Enum
from pathlib import Path
from typing import Any, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from contracts.registry import ENDPOINTS, EndpointSpec

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = ROOT / "contracts" / "examples"
DOC_PATH = ROOT / "docs" / "CONTRACTS.md"

SCALARS: dict[Any, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    dt.datetime: "datetime (ISO 8601)",
    dt.date: "date (YYYY-MM-DD)",
    type(None): "null",
    Any: "any",
}


def anchor(name: str) -> str:
    return name.lower().replace(" ", "-")


def render_type(ann: Any, refs: list[type]) -> str:
    """타입 애노테이션을 문서용 문자열로 만들고, 참조된 모델/열거형을 refs 에 모은다."""
    if ann in SCALARS:
        return SCALARS[ann]
    if isinstance(ann, type) and issubclass(ann, Enum):
        refs.append(ann)
        return f"[`{ann.__name__}`](#{anchor(ann.__name__)})"
    if isinstance(ann, type) and issubclass(ann, BaseModel):
        refs.append(ann)
        return f"[`{ann.__name__}`](#{anchor(ann.__name__)})"

    origin = get_origin(ann)
    args = get_args(ann)
    if origin in (types.UnionType, typing.Union):
        return " \\| ".join(render_type(a, refs) for a in args)
    if origin is list:
        return f"{render_type(args[0], refs)}[]"
    if origin is dict:
        return "object (자유 형식)"
    if origin is typing.Annotated:
        return render_type(args[0], refs)
    return str(ann)


def constraints(field: FieldInfo) -> str:
    """annotated_types 제약을 사람이 읽는 문자열로."""
    out: list[str] = []
    for meta in field.metadata:
        for attr, label in (
            ("ge", "≥"),
            ("gt", ">"),
            ("le", "≤"),
            ("lt", "<"),
            ("min_length", "min_len"),
            ("max_length", "max_len"),
        ):
            val = getattr(meta, attr, None)
            if val is not None:
                out.append(f"{label} {val}")
    return ", ".join(out)


def default_repr(field: FieldInfo) -> str:
    if field.is_required():
        return "**필수**"
    if field.default_factory is not None:
        try:
            made = field.default_factory()  # type: ignore[call-arg]
        except TypeError:  # pragma: no cover - validated_data 를 받는 factory
            return "(생성)"
        return f"`{json.dumps(made, ensure_ascii=False)}`" if made != {} else "`{}`"
    val = field.default
    if isinstance(val, Enum):
        return f"`{val.value}`"
    return f"`{json.dumps(val, ensure_ascii=False)}`" if val is not None else "`null`"


def enum_member_docs(cls: type[Enum]) -> dict[str, str]:
    """열거형 멤버 바로 아래 문자열 리터럴을 설명으로 추출한다(런타임에는 안 남는다)."""
    docs: dict[str, str] = {}
    try:
        src = textwrap.dedent(inspect.getsource(cls))
        tree = ast.parse(src)
    except (OSError, TypeError, SyntaxError):  # pragma: no cover
        return docs
    class_def = tree.body[0]
    if not isinstance(class_def, ast.ClassDef):  # pragma: no cover
        return docs
    last: str | None = None
    for node in class_def.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            last = node.targets[0].id
        elif (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            and last
        ):
            docs[last] = node.value.value.strip()
            last = None
    return docs


def model_section(model: type[BaseModel], refs: list[type]) -> str:
    """모델 하나의 필드 표."""
    lines = [
        f'<a id="{anchor(model.__name__)}"></a>',
        f"#### `{model.__name__}`",
        "",
    ]
    doc = inspect.getdoc(model)
    if doc:
        lines += [doc, ""]
    lines += ["| 필드 | 타입 | 기본값 | 제약 | 설명 |", "|---|---|---|---|---|"]
    for name, field in model.model_fields.items():
        tname = render_type(field.annotation, refs)
        desc = (field.description or "").replace("\n", " ")
        lines.append(
            f"| `{name}` | {tname} | {default_repr(field)} | {constraints(field) or '-'} | {desc} |"
        )
    if model.model_config.get("extra") == "allow":
        lines.append("| _(추가 필드)_ | any | - | - | `extra=allow` — 알 수 없는 키를 보존한다 |")
    lines.append("")
    return "\n".join(lines)


def enum_section(cls: type[Enum]) -> str:
    lines = [f'<a id="{anchor(cls.__name__)}"></a>', f"#### `{cls.__name__}`", ""]
    doc = inspect.getdoc(cls)
    if doc and not doc.startswith("An enumeration"):
        lines += [doc, ""]
    docs = enum_member_docs(cls)
    lines += ["| 값 | 설명 |", "|---|---|"]
    for member in cls:
        lines.append(f"| `{member.value}` | {docs.get(member.name, '')} |")
    lines.append("")
    return "\n".join(lines)


def example_of(model: type[BaseModel]) -> dict[str, Any] | None:
    """json_schema_extra 의 example 을 모델로 검증해 정규화된 dict 로 돌려준다."""
    extra = model.model_config.get("json_schema_extra")
    if not isinstance(extra, dict):
        return None
    ex = extra.get("example")
    if not isinstance(ex, dict):
        return None
    obj = model.model_validate(ex)
    dumped = obj.model_dump(mode="json")
    assert isinstance(dumped, dict)
    return dumped


def write_examples(check_only: bool) -> list[str]:
    """엔드포인트별 예시 payload 저장. 저장/검증한 파일명 목록 반환."""
    EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for ep in ENDPOINTS:
        for kind, model in (("request", ep.request_model), ("response", ep.response_model)):
            if model is None:
                continue
            ex = example_of(model)
            if ex is None:
                print(f"  ! 예시 없음: {ep.key}.{kind} ({model.__name__})")
                continue
            path = EXAMPLES_DIR / f"{ep.key}.{kind}.json"
            if not check_only:
                path.write_text(
                    json.dumps(ex, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
            written.append(path.name)
    return written


def endpoint_doc(ep: EndpointSpec, refs: list[type]) -> str:
    lines = [
        f"### `{ep.method} {ep.path}`",
        "",
        f"- **담당**: {ep.owner}",
        f"- **요약**: {ep.summary}",
    ]
    if ep.notes:
        lines.append(f"- **비고**: {ep.notes}")
    lines.append("")

    if ep.request_model is None:
        lines += ["요청 본문 없음 (경로 파라미터만).", ""]
    else:
        lines += [model_section(ep.request_model, refs)]
        ex = example_of(ep.request_model)
        if ex is not None:
            lines += [
                f"요청 예시 — `contracts/examples/{ep.key}.request.json`",
                "",
                "```json",
                json.dumps(ex, ensure_ascii=False, indent=2),
                "```",
                "",
            ]
    lines += [model_section(ep.response_model, refs)]
    ex = example_of(ep.response_model)
    if ex is not None:
        lines += [
            f"응답 예시 — `contracts/examples/{ep.key}.response.json`",
            "",
            "```json",
            json.dumps(ex, ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    return "\n".join(lines)


HEADER = """# API 계약 (v1)

> 이 문서는 `contracts/` 의 Pydantic 모델에서 **자동 생성**된다. 손으로 고치지 말고
> 모델을 고친 뒤 `make contracts` 를 실행한다. 생성기: `scripts/gen_contracts_doc.py`

## 읽는 법

- **담당** 표시가 자기 모듈이면 그 엔드포인트를 그대로 구현하면 된다. 필드명·열거형 값은
  대소문자까지 그대로 맞춘다.
- 모든 요청/응답은 JSON. 시각은 ISO 8601 문자열(가능하면 `+09:00` 오프셋 포함).
- 예시 payload 는 `contracts/examples/*.json` 에 있고, **계약 모델로 검증된 것**이다.
  그대로 `curl -d @파일` 로 쏘면 통과해야 한다.
- 파이썬 구현이면 계약을 그대로 import 해서 쓰는 편이 안전하다:
  `from contracts import IntentClassifyRequest`

## 전체 흐름

```
프론트 ──POST /session/advise──> 오케스트레이터(통합/데모)
                                      │
                    ┌─────────────────┼──────────────────┐
                    ▼                 ▼                  ▼
        POST /intent/classify  GET /assets/{cid}   POST /clienteling/reply
              (AI1)               (백엔드)                (AI2)
                                      │                   ▲
                                POST /condition/score      │ 소유 자산 + 컨디션 주입
                                POST /fingerprint/match ───┘
```

오케스트레이터는 AI2 응답의 `cited_asset_ids` 가 비어 있으면 `owned_assets_used=false` 로
표시하고 경고 로그를 남긴다. 소유 자산을 인용하지 않는 상담은 이 제품의 존재 이유가 사라진 것이다.

## 목(mock)으로 먼저 붙이기

팀원 모듈이 없어도 통합 서버는 목으로 완주한다. 자기 모듈이 준비되면 그 모듈만 전환한다.

```bash
ADAPTER_MODE=mock make dev            # 전부 목
INTENT_ADAPTER=http make dev          # 인텐트만 실제 서버(INTENT_BASE_URL)로
```

## 엔드포인트 목록

| 메서드 | 경로 | 담당 | 요약 |
|---|---|---|---|
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="계약 문서/예시 생성")
    ap.add_argument("--check", action="store_true", help="쓰지 않고 예시 유효성만 검사")
    args = ap.parse_args()

    written = write_examples(check_only=args.check)
    print(f"예시 payload {len(written)}건: {', '.join(written)}")
    if args.check:
        print("계약 예시 검증 통과")
        return 0

    refs: list[type] = []
    body = [endpoint_doc(ep, refs) for ep in ENDPOINTS]

    # 참조된 공용 타입을 부록으로. (모델 → 열거형 순, 이름 정렬)
    seen: list[type] = []
    queue = list(refs)
    while queue:
        item = queue.pop(0)
        if item in seen:
            continue
        seen.append(item)
        if isinstance(item, type) and issubclass(item, BaseModel):
            nested: list[type] = []
            model_section(item, nested)
            queue.extend(nested)

    models = sorted(
        (c for c in seen if issubclass(c, BaseModel)),
        key=lambda c: c.__name__,
    )
    enums = sorted((c for c in seen if issubclass(c, Enum)), key=lambda c: c.__name__)

    appendix = ["## 공용 타입", ""]
    sink: list[type] = []
    appendix += [model_section(m, sink) for m in models]
    appendix += ["## 열거형", ""]
    appendix += [enum_section(e) for e in enums]

    table = "\n".join(
        f"| {ep.method} | `{ep.path}` | {ep.owner} | {ep.summary} |" for ep in ENDPOINTS
    )
    doc = (
        HEADER + table + "\n\n---\n\n" + "\n---\n\n".join(body) + "\n---\n\n" + "\n".join(appendix)
    )

    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(doc, encoding="utf-8")
    print(f"문서 생성: {DOC_PATH.relative_to(ROOT)} ({len(doc.splitlines())} 줄)")
    print(f"  모델 {len(models)}종 / 열거형 {len(enums)}종 부록 포함")
    return 0


if __name__ == "__main__":
    sys.exit(main())
