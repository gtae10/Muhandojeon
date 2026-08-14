# exports — 팀원용 데이터

통합/데모 담당이 만든다. 데이터 준비 때문에 모델 작업이 막히지 않게 하는 것이 목적이다.
전부 시드 고정(seed=42)이라 재실행해도 같은 결과가 나온다. 재생성: `make data` 또는
`python -m scripts.export_for_team`.

---

## `intent_trainset.parquet` — AI1 (인텐트/망설임 분류)

세션 1건 = 1행. `split` 컬럼으로 train/val 이 나뉘어 있다(8:2, 라벨 계층 분할).

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `session_id` | str | 세션 id |
| `customer_id` | str | 고객 id (`customer_context.json` 과 조인 가능) |
| `customer_tier` | str | NEW / ESTABLISHED / VIP |
| `target_product_id` | str | 상담 대상 상품 |
| `label` | str | **정답 라벨** — SIZE_UNCERTAIN / PRICE_HESITANT / STYLE_DOUBT / STOCK_CONCERN / NONE |
| `label_rule` | str | 이 라벨을 만든 규칙 이름 |
| `label_confidence` | f64 | 규칙 엔진의 확신도(참고용, 학습 타깃 아님) |
| `split` | str | `train` / `val` |
| `n_events` | i64 | 이벤트 수 |
| `n_synthetic_events` | i64 | 그중 규칙 합성된 이벤트 수 |
| `dwell_total_seconds` | f64 | 총 체류 시간 |
| `distinct_products` | i64 | 조회한 서로 다른 상품 수 |
| `event_types` | list[str] | 이벤트 종류 시퀀스 (시간순) |
| `event_product_ids` | list[str] | 이벤트별 상품 id (없으면 "") |
| `event_dwell_seconds` | list[f64] | 이벤트별 체류 시간 |
| `event_timestamps` | list[str] | ISO 8601 시각 |
| `event_meta_json` | list[str] | 이벤트별 meta(JSON 문자열). size, max_price_krw 등이 들어있다 |
| `events_json` | str | 이벤트 전체(계약 `SessionEvent[]` 그대로). 이걸 그대로 `/intent/classify` 입력으로 쓸 수 있다 |
| `signals_json` | str | 규칙 엔진이 남긴 근거. 오차 분석에 쓰라 |

```python
import polars as pl, json
df = pl.read_parquet("exports/intent_trainset.parquet")
train = df.filter(pl.col("split") == "train")
events = json.loads(train["events_json"][0])   # 계약 SessionEvent[] 그대로
```

**주의 (반드시 읽기)**
- 라벨은 사람이 붙인 것이 아니라 `app/intent_rules.py` 의 규칙이 만든 것이다. 즉 이 셋으로
  학습한 모델의 상한은 "규칙 재현"이다. 규칙을 그대로 외우면 val 정확도가 1.0 에 가까워지는데,
  그건 성능이 아니라 누수다. **규칙이 쓰지 않는 신호(체류 분포, 순서 패턴)로 일반화하는지**를
  같이 보고하라.
- `n_synthetic_events` 가 0 이 아닌 행은 판별 이벤트가 합성된 것이다. 원본 클릭스트림의
  이벤트 어휘가 7종뿐이라 불가피했다. 자세한 내용은 `docs/DATA_PROVENANCE.md`.
- 60행은 학습에 적은 양이다. 규칙 엔진(`app.intent_rules.classify`)으로 원하는 만큼 증강해도
  된다. 증강 시 `build_sessions.py --force` 로 세션 수를 늘리는 편이 스키마 안전하다.

---

## `catalog_rag.jsonl` — AI2 (클라이언텔링 상담)

한 줄 = 한 상품(40개). `{"id", "text", "metadata"}` 구조로 대부분의 벡터 스토어에 바로 넣을 수 있다.

```python
import json
docs = [json.loads(l) for l in open("exports/catalog_rag.jsonl")]
texts = [d["text"] for d in docs]          # 임베딩 대상
metas = [d["metadata"] for d in docs]      # 필터링용 (category, price_krw, available_sizes ...)
```

`text` 에는 소재·제법·사이즈 체계·현재 재고 사이즈·케어 가이드가 들어 있다. 상담 답변에서
사이즈나 재고를 말할 때 이 문서를 근거로 인용하라.

---

## `customer_context.json` — AI2 (상담 프롬프트 주입용)

고객 30명 × 소유 개체 + 컨디션. **`priority_asset_ids` 순서가 인용 우선순위**다
(컨디션이 낮거나 케어 시점이 임박한 개체가 앞).

```python
ctx = json.load(open("exports/customer_context.json"))
cust = {c["customer_id"]: c for c in ctx["customers"]}["CU-0007"]
top = cust["assets"][0]        # 가장 먼저 인용해야 하는 개체
top["condition_score"], top["headline_finding"], top["next_service_months"]
```

| 필드 | 설명 |
|---|---|
| `tier` | NEW(개체 1~2) / ESTABLISHED(3~7) / VIP(8+) |
| `owned_categories` | 보유 카테고리 목록 |
| `avg_owned_price_krw` | 보유 개체 평균 정가 — 가격 민감도 판단 근거 |
| `care_due_asset_ids` | 3개월 내 케어 권장 개체 |
| `priority_asset_ids` | 인용 우선순위 (앞이 더 중요) |
| `assets[].condition_score` | 0~100 (100=신품). 70 이하면 즉시 케어 권장 |
| `assets[].findings` | 부위별 소견 (part/severity/note) — **이 문장을 그대로 인용하면 된다** |
| `assets[].headline_finding` | 가장 심각한 소견 1문장 |
| `assets[].next_service_months` | 컨디션 70 도달까지 남은 개월 수 |

**하드 요구사항**: 상담 응답(`/clienteling/reply`)은 `owned_assets` 가 비어 있지 않으면
`cited_asset_ids` 를 반드시 채워야 한다. 오케스트레이터가 인용 없음을 감지하면
`owned_assets_used=false` 로 표시하고 경고 로그를 남긴다. 그게 이 제품의 존재 이유다.

---

## 계약과의 관계

이 파일들의 필드명은 `contracts/` 의 Pydantic 모델과 맞춰져 있다. 파이썬이면 그대로 import 해서
검증하는 편이 안전하다.

```python
from contracts import OwnedAsset, SessionEvent
assets = [OwnedAsset.model_validate(a) for a in cust["assets"]]   # 여분 필드는 무시된다
```

전체 계약: `docs/CONTRACTS.md`. 데이터 출처/합성 범위: `docs/DATA_PROVENANCE.md`.
