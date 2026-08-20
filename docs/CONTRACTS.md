# API 계약 (v1)

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
| POST | `/intent/classify` | AI1 (인텐트/망설임 분류) | 세션 이벤트로 구매 망설임 유형을 분류한다 |
| POST | `/clienteling/reply` | AI2 (클라이언텔링 상담) | 망설임 유형과 소유 자산을 근거로 상담 문구를 생성한다 |
| POST | `/clienteling/outreach` | AI2 (클라이언텔링 상담) | 어드바이저가 먼저 건네는 첫 마디 — 케어 임박 자산 등 계기가 있을 때만 |
| GET | `/assets/{customer_id}` | 백엔드 (개체/자산) | 고객이 소유한 개체 목록과 컨디션을 반환한다 |
| POST | `/fingerprint/match` | 백엔드 (개체 지문) | 촬영 이미지를 등록 개체와 대조한다 |
| POST | `/condition/score` | 백엔드 (컨디션) | 개체의 컨디션 점수와 부위별 소견을 반환한다 |
| POST | `/session/advise` | 통합/데모 (이 레포) | 위 모듈을 조합한 최종 상담 응답 — 프론트의 단일 진입점 |

---

### `POST /intent/classify`

- **담당**: AI1 (인텐트/망설임 분류)
- **요약**: 세션 이벤트로 구매 망설임 유형을 분류한다
- **비고**: 학습셋: `exports/intent_trainset.parquet` (split 컬럼으로 train/val 8:2). 라벨 불확실 시 NONE + 낮은 confidence 를 반환하고 예외를 던지지 않는다.

<a id="intentclassifyrequest"></a>
#### `IntentClassifyRequest`

`POST /intent/classify` 요청.

| 필드 | 타입 | 기본값 | 제약 | 설명 |
|---|---|---|---|---|
| `customer_id` | string | **필수** | - | 고객 id |
| `session_events` | [`SessionEvent`](#sessionevent)[] | **필수** | min_len 1 | 세션 이벤트 시퀀스 (시간순 정렬 보장 없음) |

요청 예시 — `contracts/examples/intent_classify.request.json`

```json
{
  "customer_id": "CU-0003",
  "session_events": [
    {
      "event_type": "view_product",
      "product_id": "LX-0006",
      "timestamp": "2026-08-14T10:02:11+09:00",
      "dwell_seconds": 42.0,
      "meta": {}
    },
    {
      "event_type": "size_guide",
      "product_id": "LX-0006",
      "timestamp": "2026-08-14T10:03:20+09:00",
      "dwell_seconds": 88.5,
      "meta": {
        "size": "38.5"
      }
    },
    {
      "event_type": "size_guide",
      "product_id": "LX-0006",
      "timestamp": "2026-08-14T10:05:02+09:00",
      "dwell_seconds": 61.0,
      "meta": {
        "size": "39"
      }
    },
    {
      "event_type": "add_to_cart",
      "product_id": "LX-0006",
      "timestamp": "2026-08-14T10:06:40+09:00",
      "dwell_seconds": 5.0,
      "meta": {}
    }
  ]
}
```

<a id="intentclassifyresponse"></a>
#### `IntentClassifyResponse`

`POST /intent/classify` 응답.

| 필드 | 타입 | 기본값 | 제약 | 설명 |
|---|---|---|---|---|
| `hesitation_type` | [`HesitationType`](#hesitationtype) | **필수** | - |  |
| `confidence` | number | **필수** | ≥ 0.0, ≤ 1.0 | 0.0~1.0 신뢰도 |
| `signals` | [`IntentSignal`](#intentsignal)[] | `[]` | - | 분류 근거. 최소 1건을 권장(대시보드 표시용) |

응답 예시 — `contracts/examples/intent_classify.response.json`

```json
{
  "hesitation_type": "SIZE_UNCERTAIN",
  "confidence": 0.82,
  "signals": [
    {
      "name": "size_guide_repeat",
      "weight": 0.62,
      "evidence": "size_guide 2회 조회 (38.5, 39)"
    },
    {
      "name": "cart_without_checkout",
      "weight": 0.2,
      "evidence": "장바구니 담기 후 결제 진입 없음"
    }
  ]
}
```

---

### `POST /clienteling/reply`

- **담당**: AI2 (클라이언텔링 상담)
- **요약**: 망설임 유형과 소유 자산을 근거로 상담 문구를 생성한다
- **비고**: RAG 문서: `exports/catalog_rag.jsonl`, 고객 컨텍스트: `exports/customer_context.json`. **owned_assets 가 비어 있지 않으면 cited_asset_ids 를 반드시 채운다.**

<a id="clientelingreplyrequest"></a>
#### `ClientelingReplyRequest`

`POST /clienteling/reply` 요청.

| 필드 | 타입 | 기본값 | 제약 | 설명 |
|---|---|---|---|---|
| `customer_id` | string | **필수** | - |  |
| `hesitation_type` | [`HesitationType`](#hesitationtype) | **필수** | - | AI1 이 분류한 망설임 유형 |
| `target_product` | [`Product`](#product) | **필수** | - | 상담 대상 상품 |
| `owned_assets` | [`OwnedAsset`](#ownedasset)[] | `[]` | - | 고객 소유 개체 목록. 컨디션 우선순위로 정렬되어 전달된다(앞쪽이 더 중요) |
| `strategy_id` | string | `"S2"` | - | 상담 전략 id. `data/strategies.yaml` 참조 (S1 정보제공/S2 자산연계/S3 희소성) |
| `history` | [`ChatTurn`](#chatturn)[] | `[]` | - | 직전까지의 대화 |

요청 예시 — `contracts/examples/clienteling_reply.request.json`

```json
{
  "customer_id": "CU-0003",
  "hesitation_type": "SIZE_UNCERTAIN",
  "target_product": {
    "product_id": "LX-0006",
    "name": "Aurelia Oxford",
    "category": "SHOES",
    "collection": "Maison Nord",
    "material": "패티나 카프 / 굿이어 웰트",
    "color": "Cognac",
    "price_krw": 2700000,
    "size_system": "EU 35-42 / Last: LAST-AURELIA",
    "available_sizes": [
      "38.5",
      "39",
      "40"
    ],
    "care_notes": "패티나 유지 위해 왁스는 3개월 간격. 우천 착화 지양",
    "image_path": "images/placeholder/LX-0006.jpg"
  },
  "owned_assets": [
    {
      "asset_id": "AS-0010",
      "customer_id": "CU-0003",
      "product_id": "LX-0005",
      "product_name": "Aurelia Derby",
      "category": "SHOES",
      "purchased_at": "2023-04-18T00:00:00+09:00",
      "condition_score": 81,
      "findings": [
        {
          "part": "sole",
          "severity": "MEDIUM",
          "note": "앞창 마모 진행"
        }
      ],
      "next_service_months": 6,
      "last_scanned_at": "2026-06-05T14:00:00+09:00"
    }
  ],
  "strategy_id": "S2",
  "history": [
    {
      "role": "customer",
      "content": "38.5가 맞을지 39가 맞을지 모르겠어요."
    }
  ]
}
```

<a id="clientelingreplyresponse"></a>
#### `ClientelingReplyResponse`

`POST /clienteling/reply` 응답.

| 필드 | 타입 | 기본값 | 제약 | 설명 |
|---|---|---|---|---|
| `message` | string | **필수** | - | 고객에게 보여지는 상담 문구 (한국어, 2~4문장) |
| `cited_asset_ids` | string[] | `[]` | - | message 가 실제로 근거로 삼은 개체 id. 소유 자산이 있으면 비워두지 않는다 |
| `cta` | [`CTA`](#cta) | `NONE` | - |  |
| `reasoning` | string | `""` | - | 내부 로그용 판단 근거. 고객에게 노출하지 않는다 |

응답 예시 — `contracts/examples/clienteling_reply.response.json`

```json
{
  "message": "2023년에 함께하신 Aurelia Derby와 같은 LAST-AURELIA 라스트입니다. 그때 38.5로 맞춰 드렸고 현재 컨디션 81점(앞창 마모 진행)이라, 같은 38.5가 가장 안정적입니다. 재밑창 예약과 함께 피팅을 잡아드릴까요?",
  "cited_asset_ids": [
    "AS-0010"
  ],
  "cta": "BOOK_FITTING",
  "reasoning": "동일 라스트 보유 → 사이즈 불확실 해소. 컨디션 81점 → 케어 동시 제안."
}
```

---

### `POST /clienteling/outreach`

- **담당**: AI2 (클라이언텔링 상담)
- **요약**: 어드바이저가 먼저 건네는 첫 마디 — 케어 임박 자산 등 계기가 있을 때만
- **비고**: 계기가 없으면 `message: null` 로 응답한다 — 화면은 아무것도 띄우지 않는다. AI2 실서버는 계기 없음을 400 으로 주며, 통합 레이어 HTTP 어댑터가 `message: null` 로 흡수한다(에러 아님).

<a id="clientelingoutreachrequest"></a>
#### `ClientelingOutreachRequest`

`POST /clienteling/outreach` 요청 — 어드바이저가 먼저 건네는 첫 마디.

고객이 물어야만 답하는 구조는 헬프봇이다. 케어 임박 자산 같은 **계기**가
있을 때만 열리고, 계기가 없으면 응답 `message` 가 null 이다 — 화면은 그때
아무것도 띄우지 않는 것이 맞다.

| 필드 | 타입 | 기본값 | 제약 | 설명 |
|---|---|---|---|---|
| `customer_id` | string | **필수** | - |  |
| `owned_assets` | [`OwnedAsset`](#ownedasset)[] | `[]` | - | 고객 소유 개체 목록. 컨디션 우선순위로 정렬되어 전달된다(앞쪽이 더 중요) |
| `hesitation_type` | [`HesitationType`](#hesitationtype) \| null | `null` | - | 세션에서 이미 분류된 망설임 유형이 있으면 함께 전달 |

요청 예시 — `contracts/examples/clienteling_outreach.request.json`

```json
{
  "customer_id": "CU-0001",
  "owned_assets": [
    {
      "asset_id": "AS-0001",
      "customer_id": "CU-0001",
      "product_id": "LX-0001",
      "product_name": "Aurelia Top Handle",
      "category": "BAG",
      "purchased_at": "2022-04-16T00:00:00+09:00",
      "condition_score": 71,
      "findings": [
        {
          "part": "handle",
          "severity": "MEDIUM",
          "note": "핸들 표면 마모 진행, 케어 임계 근접"
        }
      ],
      "next_service_months": 1,
      "last_scanned_at": "2026-07-03T14:20:00+09:00"
    }
  ],
  "hesitation_type": "NONE"
}
```

<a id="clientelingoutreachresponse"></a>
#### `ClientelingOutreachResponse`

`POST /clienteling/outreach` 응답.

| 필드 | 타입 | 기본값 | 제약 | 설명 |
|---|---|---|---|---|
| `message` | string \| null | `null` | - | 첫 인사 문구. null 이면 계기 없음 — 오프닝을 띄우지 않는다 (에러가 아니다) |
| `cited_asset_ids` | string[] | `[]` | - | message 가 실제로 근거로 삼은 개체 id (케어 오프닝일 때 채워진다) |
| `cta` | [`CTA`](#cta) | `NONE` | - |  |
| `reasoning` | string | `""` | - | 내부 로그용 판단 근거. 고객에게 노출하지 않는다 |

응답 예시 — `contracts/examples/clienteling_outreach.response.json`

```json
{
  "message": "2022년에 함께하신 Aurelia Top Handle, 컨디션 71점으로 약 1개월 뒤가 케어 권장 시점이에요(핸들 표면 마모 진행, 케어 임계 근접). 다음 방문 때 케어 예약을 함께 잡아 드릴까요?",
  "cited_asset_ids": [
    "AS-0001"
  ],
  "cta": "CARE_BOOKING",
  "reasoning": "케어 임박 자산 AS-0001(1개월) → 선제 케어 제안"
}
```

---

### `GET /assets/{customer_id}`

- **담당**: 백엔드 (개체/자산)
- **요약**: 고객이 소유한 개체 목록과 컨디션을 반환한다
- **비고**: 정렬은 오케스트레이터가 한다. 백엔드는 정렬하지 않아도 된다.

요청 본문 없음 (경로 파라미터만).

<a id="customerassetsresponse"></a>
#### `CustomerAssetsResponse`

`GET /assets/{customer_id}` 응답.

| 필드 | 타입 | 기본값 | 제약 | 설명 |
|---|---|---|---|---|
| `customer_id` | string | **필수** | - |  |
| `tier` | [`CustomerTier`](#customertier) | **필수** | - | 구매 이력 건수 기반 티어 |
| `assets` | [`OwnedAsset`](#ownedasset)[] | `[]` | - | 소유 개체 목록 |

응답 예시 — `contracts/examples/assets_list.response.json`

```json
{
  "customer_id": "CU-0003",
  "tier": "ESTABLISHED",
  "assets": [
    {
      "asset_id": "AS-0010",
      "customer_id": "CU-0003",
      "product_id": "LX-0005",
      "product_name": "Aurelia Derby",
      "category": "SHOES",
      "purchased_at": "2023-04-18T00:00:00+09:00",
      "condition_score": 81,
      "findings": [
        {
          "part": "sole",
          "severity": "MEDIUM",
          "note": "앞창 마모 진행"
        }
      ],
      "next_service_months": 6,
      "last_scanned_at": "2026-06-05T14:00:00+09:00"
    }
  ]
}
```

---

### `POST /fingerprint/match`

- **담당**: 백엔드 (개체 지문)
- **요약**: 촬영 이미지를 등록 개체와 대조한다
- **비고**: 등록 경로 규약: `data/fingerprints/{asset_id}/{angle}_{index}.jpg`. 품질 검증과 경로 등록은 `scripts/register_fingerprint.py` 가 이미 처리한다.

<a id="fingerprintmatchrequest"></a>
#### `FingerprintMatchRequest`

`POST /fingerprint/match` 요청.

| 필드 | 타입 | 기본값 | 제약 | 설명 |
|---|---|---|---|---|
| `image_path` | string \| null | `null` | - | `data/fingerprints/...` 형태의 질의 이미지 경로 |
| `image_base64` | string \| null | `null` | - | 경로를 못 쓰는 경우의 대안 |
| `customer_id` | string \| null | `null` | - | 주어지면 해당 고객 소유 개체로 후보를 한정한다 |
| `top_k` | integer | `3` | ≥ 1, ≤ 20 | 반환할 후보 수 |

요청 예시 — `contracts/examples/fingerprint_match.request.json`

```json
{
  "image_path": "data/fingerprints/AS-0001/handle_01.jpg",
  "image_base64": null,
  "customer_id": "CU-0001",
  "top_k": 3
}
```

<a id="fingerprintmatchresponse"></a>
#### `FingerprintMatchResponse`

`POST /fingerprint/match` 응답.

| 필드 | 타입 | 기본값 | 제약 | 설명 |
|---|---|---|---|---|
| `matched_asset_id` | string \| null | **필수** | - | 1위 후보. 임계 미달이면 null |
| `similarity` | number | **필수** | ≥ 0.0, ≤ 1.0 | 1위 후보 유사도 |
| `is_match` | boolean | **필수** | - | similarity >= threshold 여부 |
| `candidates` | [`FingerprintCandidate`](#fingerprintcandidate)[] | `[]` | - | 상위 top_k 후보 (내림차순) |
| `threshold` | number | `0.75` | - | 판정에 사용한 임계값 |

응답 예시 — `contracts/examples/fingerprint_match.response.json`

```json
{
  "matched_asset_id": "AS-0001",
  "similarity": 0.94,
  "is_match": true,
  "candidates": [
    {
      "asset_id": "AS-0001",
      "similarity": 0.94
    },
    {
      "asset_id": "AS-0003",
      "similarity": 0.41
    }
  ],
  "threshold": 0.75
}
```

---

### `POST /condition/score`

- **담당**: 백엔드 (컨디션)
- **요약**: 개체의 컨디션 점수와 부위별 소견을 반환한다
- **비고**: 컨디션 70 이 케어 권장 임계값. next_service_months=0 이면 즉시 권장.

<a id="conditionscorerequest"></a>
#### `ConditionScoreRequest`

`POST /condition/score` 요청.

| 필드 | 타입 | 기본값 | 제약 | 설명 |
|---|---|---|---|---|
| `asset_id` | string | **필수** | - | 대상 개체 id |
| `image_paths` | string[] | `[]` | - | 스캔 이미지 경로. 비어 있으면 마지막 스캔 결과를 반환한다 |

요청 예시 — `contracts/examples/condition_score.request.json`

```json
{
  "asset_id": "AS-0001",
  "image_paths": [
    "data/fingerprints/AS-0001/handle_01.jpg",
    "data/fingerprints/AS-0001/corner_01.jpg"
  ]
}
```

<a id="conditionscoreresponse"></a>
#### `ConditionScoreResponse`

`POST /condition/score` 응답.

| 필드 | 타입 | 기본값 | 제약 | 설명 |
|---|---|---|---|---|
| `asset_id` | string | **필수** | - |  |
| `score` | integer | **필수** | ≥ 0, ≤ 100 | 0~100 컨디션 점수 (100=신품) |
| `findings` | [`Finding`](#finding)[] | `[]` | - |  |
| `next_service_months` | integer | **필수** | ≥ 0 | 컨디션 70 도달까지 남은 개월 수. 0 이면 즉시 케어 권장 |
| `confidence` | number | `0.8` | ≥ 0.0, ≤ 1.0 | 추정 신뢰도 |

응답 예시 — `contracts/examples/condition_score.response.json`

```json
{
  "asset_id": "AS-0001",
  "score": 71,
  "findings": [
    {
      "part": "handle",
      "severity": "MEDIUM",
      "note": "핸들 표면 마모 진행, 케어 임계 근접"
    },
    {
      "part": "corner",
      "severity": "MEDIUM",
      "note": "코너 4곳 마찰, 각 세우기 필요"
    }
  ],
  "next_service_months": 1,
  "confidence": 0.8
}
```

---

### `POST /session/advise`

- **담당**: 통합/데모 (이 레포)
- **요약**: 위 모듈을 조합한 최종 상담 응답 — 프론트의 단일 진입점
- **비고**: 인텐트 → 자산 조회 → 컨디션 우선 정렬 → 상담 → 인용 검증. 인용이 비면 `owned_assets_used=false` + 경고 로그.

<a id="adviserequest"></a>
#### `AdviseRequest`

`POST /session/advise` 요청.

| 필드 | 타입 | 기본값 | 제약 | 설명 |
|---|---|---|---|---|
| `customer_id` | string | **필수** | - |  |
| `target_product_id` | string | **필수** | - | 상담 대상 상품 id |
| `session_events` | [`SessionEvent`](#sessionevent)[] | `[]` | - | 세션 이벤트. 비우면 인텐트는 NONE 으로 간주하고 일반 제안 모드로 간다 |
| `strategy_id` | string | `"S2"` | - | 상담 전략 id (S1/S2/S3) |
| `history` | [`ChatTurn`](#chatturn)[] | `[]` | - |  |
| `scenario_id` | string \| null | `null` | - | 데모 시나리오 id. 주어지면 고정 시드/캐시 키로 사용한다 |

요청 예시 — `contracts/examples/session_advise.request.json`

```json
{
  "customer_id": "CU-0003",
  "target_product_id": "LX-0006",
  "session_events": [
    {
      "event_type": "size_guide",
      "product_id": "LX-0006",
      "timestamp": "2026-08-14T10:03:20+09:00",
      "dwell_seconds": 88.5,
      "meta": {
        "size": "38.5"
      }
    },
    {
      "event_type": "size_guide",
      "product_id": "LX-0006",
      "timestamp": "2026-08-14T10:05:02+09:00",
      "dwell_seconds": 61.0,
      "meta": {
        "size": "39"
      }
    }
  ],
  "strategy_id": "S2",
  "history": [],
  "scenario_id": null
}
```

<a id="adviseresponse"></a>
#### `AdviseResponse`

`POST /session/advise` 응답. 프론트는 이 하나만 렌더하면 된다.

| 필드 | 타입 | 기본값 | 제약 | 설명 |
|---|---|---|---|---|
| `request_id` | string | **필수** | - | 요청 식별자. 로그 대조용 |
| `customer_id` | string | **필수** | - |  |
| `tier` | [`CustomerTier`](#customertier) | **필수** | - |  |
| `hesitation_type` | [`HesitationType`](#hesitationtype) | **필수** | - |  |
| `confidence` | number | **필수** | ≥ 0.0, ≤ 1.0 | 0.0~1.0 신뢰도 |
| `signals` | [`IntentSignal`](#intentsignal)[] | `[]` | - |  |
| `message` | string | **필수** | - | 고객에게 보여줄 상담 문구 |
| `cta` | [`CTA`](#cta) | `NONE` | - |  |
| `cited_asset_ids` | string[] | `[]` | - |  |
| `citations` | [`AssetCitation`](#assetcitation)[] | `[]` | - | 인용 개체의 요약. cited_asset_ids 와 순서가 같다 |
| `owned_assets_used` | boolean | **필수** | - | 소유 자산을 실제로 인용했는지. **false 면 제품 실패 신호**이며 경고 로그가 남는다. 소유 자산이 아예 없는 신규 고객도 false 가 된다(그때는 no_assets=true) |
| `no_assets` | boolean | `false` | - | 고객에게 등록된 개체가 없어서 인용 불가 |
| `ranked_asset_ids` | string[] | `[]` | - | 컨디션 우선순위로 정렬된 전체 개체 id |
| `strategy_id` | string | `"S2"` | - |  |
| `degraded` | boolean | `false` | - | 어느 단계든 폴백이 발생했는지. 헤더 X-Degraded 와 동일 |
| `reasoning` | string | `""` | - |  |
| `trace` | [`AdviseTraceStep`](#advisetracestep)[] | `[]` | - |  |

응답 예시 — `contracts/examples/session_advise.response.json`

```json
{
  "request_id": "adv-CU-0003-LX-0006-S2",
  "customer_id": "CU-0003",
  "tier": "ESTABLISHED",
  "hesitation_type": "SIZE_UNCERTAIN",
  "confidence": 0.82,
  "signals": [
    {
      "name": "size_guide_repeat",
      "weight": 0.62,
      "evidence": "size_guide 2회 조회 (38.5, 39)"
    }
  ],
  "message": "2023년에 함께하신 Aurelia Derby와 같은 LAST-AURELIA 라스트입니다. 현재 컨디션 81점(앞창 마모 진행)이라 재밑창과 함께 피팅을 잡아드릴까요?",
  "cta": "BOOK_FITTING",
  "cited_asset_ids": [
    "AS-0010"
  ],
  "citations": [
    {
      "asset_id": "AS-0010",
      "product_name": "Aurelia Derby",
      "condition_score": 81,
      "next_service_months": 6,
      "headline_finding": "앞창 마모 진행"
    }
  ],
  "owned_assets_used": true,
  "no_assets": false,
  "ranked_asset_ids": [
    "AS-0010",
    "AS-0011"
  ],
  "strategy_id": "S2",
  "degraded": false,
  "reasoning": "동일 라스트 보유 → 사이즈 불확실 해소.",
  "trace": [
    {
      "step": "intent",
      "adapter": "MockIntentAdapter",
      "mode": "mock",
      "elapsed_ms": 1.2,
      "degraded": false,
      "detail": "SIZE_UNCERTAIN (0.82)"
    }
  ]
}
```

---

## 공용 타입

<a id="advisetracestep"></a>
#### `AdviseTraceStep`

단계별 실행 기록. `/health/detail` 과 디버깅에 쓴다.

| 필드 | 타입 | 기본값 | 제약 | 설명 |
|---|---|---|---|---|
| `step` | string | **필수** | - | 단계 이름 (intent/assets/rank/clienteling/validate) |
| `adapter` | string | **필수** | - | 사용한 어댑터 (예: 'MockIntentAdapter') |
| `mode` | string | **필수** | - | mock | http | fallback |
| `elapsed_ms` | number | **필수** | - |  |
| `degraded` | boolean | `false` | - | 타임아웃/실패로 폴백했는지 |
| `detail` | string | `""` | - |  |

<a id="assetcitation"></a>
#### `AssetCitation`

상담이 인용한 개체의 요약. 화면에 근거 카드로 렌더한다.

| 필드 | 타입 | 기본값 | 제약 | 설명 |
|---|---|---|---|---|
| `asset_id` | string | **필수** | - |  |
| `product_name` | string | **필수** | - |  |
| `condition_score` | integer | **필수** | - |  |
| `next_service_months` | integer | **필수** | - |  |
| `headline_finding` | string \| null | `null` | - | 가장 심각한 소견 문장 (없으면 null) |

<a id="chatturn"></a>
#### `ChatTurn`

상담 대화 1턴.

| 필드 | 타입 | 기본값 | 제약 | 설명 |
|---|---|---|---|---|
| `role` | [`Role`](#role) | **필수** | - |  |
| `content` | string | **필수** | - |  |

<a id="finding"></a>
#### `Finding`

컨디션 소견 1건. 상담 문구가 인용하는 최소 단위 근거.

| 필드 | 타입 | 기본값 | 제약 | 설명 |
|---|---|---|---|---|
| `part` | [`AssetPart`](#assetpart) | **필수** | - | 부위 |
| `severity` | [`Severity`](#severity) | **필수** | - | 심각도 |
| `note` | string | **필수** | - | 사람이 읽는 소견 문장 (예: '핸들 코팅 미세 균열') |

<a id="fingerprintcandidate"></a>
#### `FingerprintCandidate`

매칭 후보 1건.

| 필드 | 타입 | 기본값 | 제약 | 설명 |
|---|---|---|---|---|
| `asset_id` | string | **필수** | - |  |
| `similarity` | number | **필수** | ≥ 0.0, ≤ 1.0 | 0~1 유사도 |

<a id="intentsignal"></a>
#### `IntentSignal`

분류 근거 1건.

| 필드 | 타입 | 기본값 | 제약 | 설명 |
|---|---|---|---|---|
| `name` | string | **필수** | - | 신호 이름 (예: 'size_guide_repeat') |
| `weight` | number | **필수** | - | 기여도. 양수=해당 라벨 지지, 음수=반대 |
| `evidence` | string | **필수** | - | 사람이 읽는 근거 문장 (예: 'size_guide 3회 조회') |

<a id="ownedasset"></a>
#### `OwnedAsset`

고객이 소유한 **개체**. 개체 지문으로 식별되며 컨디션 점수를 가진다.

이 모델이 우리 제품의 차별점이다. 상담 응답은 여기 있는 `asset_id` 를
`cited_asset_ids` 로 인용해야 한다.

| 필드 | 타입 | 기본값 | 제약 | 설명 |
|---|---|---|---|---|
| `asset_id` | string | **필수** | - | 개체 id (예: 'AS-0001') |
| `customer_id` | string | **필수** | - |  |
| `product_id` | string | **필수** | - |  |
| `product_name` | string | **필수** | - | 조회 편의를 위한 비정규화 필드 |
| `category` | [`ProductCategory`](#productcategory) | **필수** | - |  |
| `purchased_at` | datetime (ISO 8601) | **필수** | - | 구매 시각 |
| `condition_score` | integer | **필수** | ≥ 0, ≤ 100 | 0~100 컨디션 점수 (100=신품) |
| `findings` | [`Finding`](#finding)[] | `[]` | - |  |
| `next_service_months` | integer | **필수** | ≥ 0 | 권장 케어까지 남은 개월 수. 0 이면 즉시 권장 |
| `last_scanned_at` | datetime (ISO 8601) \| null | `null` | - | 마지막 개체 지문 스캔 시각. null 이면 미등록 개체 |

<a id="product"></a>
#### `Product`

카탈로그 상품(모델 단위). 개체(asset)와 구분한다.

`data/processed/catalog_luxury.json` 의 레코드와 1:1 대응한다.

| 필드 | 타입 | 기본값 | 제약 | 설명 |
|---|---|---|---|---|
| `product_id` | string | **필수** | - | 상품 id (예: 'LX-0007') |
| `name` | string | **필수** | - | 럭셔리 톤으로 리라이팅된 제품명 |
| `category` | [`ProductCategory`](#productcategory) | **필수** | - |  |
| `collection` | string | **필수** | - | 컬렉션명 |
| `material` | string | **필수** | - | 소재 설명 |
| `color` | string | **필수** | - | 컬러명 |
| `price_krw` | integer | **필수** | ≥ 0 | 정가(원). 1,500,000~12,000,000 범위 |
| `size_system` | string | **필수** | - | 사이즈 체계 (예: 'EU 35-42 / Last: Aurelia') |
| `available_sizes` | string[] | `[]` | - | 현재 재고 사이즈 |
| `care_notes` | string | `""` | - | 케어 가이드 요약 |
| `image_path` | string \| null | `null` | - | `data/processed/` 기준 상대 경로 (예: 'images/LX-0007.jpg') |

<a id="sessionevent"></a>
#### `SessionEvent`

고객 세션의 단일 이벤트. AI1 입력의 기본 단위.

| 필드 | 타입 | 기본값 | 제약 | 설명 |
|---|---|---|---|---|
| `event_type` | [`EventType`](#eventtype) | **필수** | - | 이벤트 종류 |
| `product_id` | string \| null | `null` | - | 대상 상품 id. 검색·카테고리 이벤트는 null |
| `timestamp` | datetime (ISO 8601) | **필수** | - | 이벤트 발생 시각 (ISO 8601, tz-aware 권장) |
| `dwell_seconds` | number | `0.0` | ≥ 0.0 | 해당 화면 체류 시간(초) |
| `meta` | object (자유 형식) | `{}` | - | 이벤트별 부가 정보. 예: size_guide→{'size':'38'}, price_filter_change→{'max_price_krw':3000000}, search→{'query':'...'} |
| _(추가 필드)_ | any | - | - | `extra=allow` — 알 수 없는 키를 보존한다 |

## 열거형

<a id="assetpart"></a>
#### `AssetPart`

컨디션 소견이 가리키는 부위.

| 값 | 설명 |
|---|---|
| `handle` |  |
| `stitching` |  |
| `corner` |  |
| `hardware` |  |
| `lining` |  |
| `exterior` |  |
| `strap` |  |
| `sole` |  |
| `upper` |  |
| `edge_coat` |  |
| `dial` |  |
| `bracelet` |  |

<a id="cta"></a>
#### `CTA`

상담 응답이 유도하는 다음 행동. 프론트가 버튼으로 렌더한다.

| 값 | 설명 |
|---|---|
| `BOOK_FITTING` | 오프라인 피팅/방문 예약. |
| `VIEW_STOCK` | 재고·입고 예정 확인. |
| `CARE_BOOKING` | 케어(수선·클리닝) 예약 — 소유 자산 컨디션 근거일 때. |
| `NONE` | 행동 유도 없음(정보 제공만). |

<a id="customertier"></a>
#### `CustomerTier`

구매 이력 건수 기반 티어. NEW 1~2건 / ESTABLISHED 3~7건 / VIP 8건 이상.

| 값 | 설명 |
|---|---|
| `NEW` |  |
| `ESTABLISHED` |  |
| `VIP` |  |

<a id="eventtype"></a>
#### `EventType`

세션 이벤트 종류.

클릭스트림 원본에 없는 타입은 규칙 기반으로 합성한다. 어떤 필드가 원본이고
어떤 필드가 합성인지는 `docs/DATA_PROVENANCE.md`에 명시되어 있다.

| 값 | 설명 |
|---|---|
| `view_product` |  |
| `image_zoom` |  |
| `size_guide` |  |
| `price_filter_change` |  |
| `stock_check` |  |
| `shipping_info` |  |
| `care_info` |  |
| `review_read` |  |
| `search` |  |
| `back_to_category` |  |
| `wishlist_add` |  |
| `add_to_cart` |  |
| `remove_from_cart` |  |
| `checkout_start` |  |
| `purchase` |  |
| `other` |  |

<a id="hesitationtype"></a>
#### `HesitationType`

구매 망설임 유형. AI1 의 출력 라벨이자 AI2 의 입력 조건.

NONE 은 "망설임 신호 없음"이며, 오케스트레이터는 이 경우에도 상담을 생성한다
(일반 제안 모드). 라벨을 늘리면 AI1 학습셋(`exports/intent_trainset.parquet`)도
같이 갱신해야 한다.

| 값 | 설명 |
|---|---|
| `SIZE_UNCERTAIN` | 사이즈/핏 확신 부족. size_guide 반복 조회, 동일 상품 사이즈 왕복. |
| `PRICE_HESITANT` | 가격 부담. 가격 필터 하향, 동일 카테고리 저가 상품 반복 조회. |
| `STYLE_DOUBT` | 취향/스타일 확신 부족. 여러 상품 왕복, 장시간 체류, 결정 없음. |
| `STOCK_CONCERN` | 재고/배송 불확실. 재고·배송 페이지 조회. |
| `NONE` | 유의미한 망설임 신호 없음. |

<a id="productcategory"></a>
#### `ProductCategory`

카탈로그 카테고리. 컨디션 마모 계수와 촬영 부위가 카테고리별로 다르다.

| 값 | 설명 |
|---|---|
| `BAG` |  |
| `SHOES` |  |
| `WATCH` |  |
| `BELT` |  |
| `WALLET` |  |
| `OUTERWEAR` |  |
| `ACCESSORY` |  |

<a id="role"></a>
#### `Role`

대화 턴의 발화자.

| 값 | 설명 |
|---|---|
| `customer` |  |
| `advisor` |  |

<a id="severity"></a>
#### `Severity`

소견 심각도. HIGH 가 하나라도 있으면 케어 예약을 우선 제안한다.

| 값 | 설명 |
|---|---|
| `LOW` |  |
| `MEDIUM` |  |
| `HIGH` |  |
