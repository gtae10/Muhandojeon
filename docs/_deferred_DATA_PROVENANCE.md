# 데이터 출처 (Provenance)

> 이 문서는 **자동 생성**된다. 필드별 판정은 `scripts/gen_provenance_doc.py` 에, 빌드 결과는
> `data/processed/provenance.json` 에 있다. 재생성: `python -m scripts.gen_provenance_doc`

심사위원 질문 대응용 문서다. **"이 데이터 진짜냐"** 에 대한 답은 한 문장으로:
행동 골격과 구매 이력은 공개 데이터셋에서 왔고, 럭셔리 서사(제품명·가격)와 컨디션 점수·판별
이벤트는 규칙으로 생성했다. 어느 필드가 어디서 왔는지는 아래 표에 전부 적어 두었다.

라이선스는 `docs/DATA_LICENSES.md`, 계약은 `docs/CONTRACTS.md` 참고.

## 재현성 정책

| 항목 | 값 | 이유 |
|---|---|---|
| 시드 | `seed=42` (모든 샘플링·분할) | 데모가 매번 달라지면 발표 대본이 깨진다 |
| 기준시각 | `REFERENCE_NOW = 2026-08-14T12:00:00+09:00` 고정 | 컨디션 점수가 경과 연수 함수라 `now()` 를 쓰면 매일 점수가 흔들린다 |
| 난수 | 사용하지 않음. 모든 "무작위성"은 `sha1(문자열)` 기반 결정적 선택 | 플랫폼·실행 간 동일 결과 보장 (파이썬 `hash()` 는 문자열에 대해 실행마다 달라져서 쓰지 않는다) |
| 카탈로그 | `catalog_luxury.json` 은 `--force` 없이 재생성 금지 | 상품명이 바뀌면 발표 대본이 깨진다 |

`REFERENCE_NOW` 를 바꾸려면 env 로만: `REFERENCE_NOW=2026-09-01T12:00:00+09:00 make data`
(컨디션 점수와 '컨디션 71점' 보정이 함께 이동한다).

## 필드별 출처

판정 기준: 
**원본** = 원본 값 그대로 / **원본 파생** = 원본 값을 변환·매핑 / **합성(규칙)** = 원본에 없어 규칙으로 생성 / **창작(LLM/템플릿)** = 문구를 창작(LLM 또는 결정적 템플릿)

### 상품 (catalog_luxury.json / products)

| 필드 | 출처 | 설명 |
|---|---|---|
| `product_id` | 합성(규칙) | 우리 id 부여 (LX-0001~LX-0040) |
| `category` | 원본 파생 | styles.csv 의 subCategory/articleType 매핑 |
| `name` | 창작(LLM/템플릿) | 럭셔리 톤 리라이팅. 원본명은 source.raw_display_name 에 보존 |
| `collection` | 창작(LLM/템플릿) | 가상의 컬렉션명 (실존 브랜드 미사용) |
| `material` | 창작(LLM/템플릿) | 카테고리별 소재/제법 어휘에서 결정적 선택 |
| `color` | 원본 파생 | 원본 baseColour → 럭셔리 컬러명 매핑 (Black→Noir 등) |
| `price_krw` | 합성(규칙) | 카테고리 가격대 안에서 해시 기반 결정적 선택 (150만~1,200만) |
| `size_system / available_sizes` | 합성(규칙) | 카테고리별 사이즈 체계. 재고는 해시로 축소 |
| `care_notes` | 창작(LLM/템플릿) | 카테고리별 케어 가이드 문구 |
| `image_path` | 원본 | Fashion Product Images 원본 이미지 사본 (60x80, 리사이즈 없음) |
| `source.*` | 원본 | 원본 id·articleType·baseColour·연도·원본 상품명 |

### 고객 (customers.json / customers)

| 필드 | 출처 | 설명 |
|---|---|---|
| `customer_id` | 합성(규칙) | 우리 id 부여 (CU-0001~CU-0030) |
| `purchase_count` | 원본 | H&M 거래 건수 (3~20건 필터 통과) |
| `tier` | 원본 파생 | 등록 개체 수 기준 (NEW 1~2 / ESTABLISHED 3~7 / VIP 8+) |
| `display_name` | 합성(규칙) | **전량 합성.** 원본에 이름 컬럼이 없다 |
| `first/last_purchase_at` | 원본 파생 | 원본 구매 시점을 상대 시점으로 스케일링 |
| `source.raw_customer_id_sha` | 원본 파생 | 원본 customer_id 의 해시(원문 미저장) |

### 소유 개체 (assets)

| 필드 | 출처 | 설명 |
|---|---|---|
| `asset_id` | 합성(규칙) | 우리 id 부여 (AS-000001~) |
| `product_id` | 원본 파생 | 원본 article_id 해시 → 카탈로그 40개 중 결정적 매핑 |
| `purchased_at` | 원본 파생 | 원본 t_dat 을 '가장 오래된 것이 4년 전, 최근이 3개월 전' 으로 선형 스케일링 |
| `condition_score` | 합성(규칙) | 100 - 경과연수 × 카테고리 마모계수 × 사용강도. 난수 없음(해시 기반 결정적) |
| `findings` | 합성(규칙) | 점수 구간 × 카테고리별 부위 순서로 생성한 소견 문장 |
| `next_service_months` | 합성(규칙) | 컨디션 70 도달까지 남은 개월 수 계산값 |
| `last_scanned_at` | 합성(규칙) | 약 75% 개체에 스캔 이력 부여(해시). 실제 스캔은 등록 CLI 가 갱신 |

### 세션 (sessions.json / sessions)

| 필드 | 출처 | 설명 |
|---|---|---|
| `session 단위` | 원본 | **(UserID, SessionID) 조합.** SessionID 단독은 1~10 버킷일 뿐 |
| `abandoned` | 원본 | add_to_cart 있고 purchase 없음 |
| `events[].event_type` | 혼합 | page_view/product_view/click/add_to_cart/purchase 는 원본 파생. size_guide/price_filter_change/stock_check/shipping_info/back_to_category/image_zoom 는 합성 |
| `events[].timestamp` | 합성(규칙) | **전량 합성.** 원본은 한 세션의 시각이 수개월에 흩어져 있어 시간축으로 쓸 수 없다(순서만 사용) |
| `events[].dwell_seconds` | 합성(규칙) | **전량 합성.** 원본에 체류시간 컬럼이 없다 |
| `events[].meta.synthetic` | 합성(규칙) | 이 이벤트가 합성인지 여부를 이벤트마다 표시 |
| `customer_id / target_product_id` | 원본 파생 | 원본 UserID / ProductID 해시 매핑 |
| `hesitation_label` | 합성(규칙) | 최종 이벤트 시퀀스에 `app.intent_rules.classify` 규칙을 적용해 도출 |

## 한계 (먼저 밝힌다)

1. **망설임 라벨은 사람이 붙인 것이 아니다.** 규칙 엔진(`app/intent_rules.py`)이 이벤트
   시퀀스에서 도출한다. 그리고 그 판별 이벤트 자체가 원본 통계에서 파생 합성된 것이므로,
   AI1 학습셋의 상한은 "규칙 재현"이다. 규칙을 외운 모델의 val 정확도 1.0 은 성능이 아니라
   누수다. 이 점을 `exports/README.md` 에도 적어 두었다.
   - 완화책: 프로파일 결정에 **원본에서 살아남은 특성만** 쓴다(상품 다양성, 장바구니 이후 탐색
     횟수, 클릭 수, 고객 보유 자산 평균가 대비 대상 가격). 목표 라벨을 먼저 정하고 근거를
     만드는 방식은 쓰지 않았다.
2. **원본 클릭스트림의 이벤트 어휘가 7종뿐**이다(page_view, product_view, click, add_to_cart,
   purchase, login, logout). 사이즈·가격·재고 관련 판별 이벤트는 존재하지 않아 합성이 불가피했다.
3. **원본 세션의 타임스탬프는 세션 시간축으로 쓸 수 없다.** 한 (UserID, SessionID) 안에서
   시각이 수개월에 걸쳐 흩어져 있다. 순서만 살리고 시각/체류시간은 규칙 합성했다.
4. **동일 상품 반복 조회 신호가 원본에 없다.** 모든 세션의 `repeat_max` 가 1이라 사이즈 고민의
   직접 증거로 쓸 수 없었고, 대신 "사이즈 체계가 있는 카테고리 + 소수 상품 집중"으로 대체했다.
5. **상품 이미지가 60x80** 이다(Fashion Product Images "Small" 버전). 인위적 업스케일은 오히려
   흐려 보여서 원본 해상도를 유지하고 `source.image_px` 에 실제 크기를 기록했다. 발표 화면에서는
   작게 렌더하는 편이 낫다.
6. **컨디션 점수는 시간 기반 추정치**다. 실제 이미지 기반 컨디션 판정은 백엔드 담당의
   `POST /condition/score` 실구현 몫이며, 목 어댑터는 이 추정치를 그대로 반환한다.
7. **H&M 거래가 없으면 합성 거래로 대체**된다(대회 규칙 미동의 시 403). 어느 슬라이스가 합성인지는
   아래 '최근 빌드 결과' 에 그대로 나온다.

## 최근 빌드 결과

빌드마다 자동 기록된다(`data/processed/provenance.json`).

### `catalog`

| 항목 | 값 |
|---|---|
| reference_now | `2026-08-14T12:00:00+09:00` |
| seed | `42` |
| source | `external` |
| reason | `원본 사용 (4.3 MB)` |
| candidate_rows | `12665` |
| styles_csv_rows | `44446` |
| selected | `40` |
| rewriter | `["template"]` |
| images_dir | `data/processed/images` |

### `customers`

| 항목 | 값 |
|---|---|
| reference_now | `2026-08-14T12:00:00+09:00` |
| seed | `42` |
| reason | `원본 없음 → 합성 폴백 (transactions_train.csv)` |
| synth_rows | `1908` |
| source | `synth` |
| customers | `30` |
| assets | `170` |
| tier_counts | `{"VIP": 10, "ESTABLISHED": 14, "NEW": 6}` |
| condition_min | `61` |
| condition_max | `99` |
| care_due_now | `5` |
| pinned_demo_asset | `{"customer_id": "CU-0001", "asset_id": "AS-000001", "product_name": "Nocturne Shoulder", "condition_score": "71", "next_service_months": "1", "headline": "핸들 표면 마모 진행, 케어 임계 근접"}` |

### `sessions`

| 항목 | 값 |
|---|---|
| reference_now | `2026-08-14T12:00:00+09:00` |
| seed | `42` |
| source | `external` |
| reason | `원본 사용 (3.9 MB)` |
| raw_rows | `74817` |
| raw_sessions | `10000` |
| session_unit | `(UserID, SessionID)` |
| selected_sessions | `60` |
| label_counts | `{"PRICE_HESITANT": 14, "STOCK_CONCERN": 17, "SIZE_UNCERTAIN": 15, "STYLE_DOUBT": 9, "NONE": 5}` |
| profile_counts | `{"price": 14, "stock": 17, "size": 15, "style": 9, "none": 5}` |
| synthetic_events | `150` |
| total_events | `458` |

### `exports`

| 항목 | 값 |
|---|---|
| reference_now | `2026-08-14T12:00:00+09:00` |
| seed | `42` |
| intent_trainset | `{"rows": 60, "columns": ["session_id", "customer_id", "customer_tier", "target_product_id", "label", "label_rule", "label_confidence", "split", "n_events", "n_synthetic_events", "dwell_total_seconds", "distinct_products", "event_types", "event_product_ids", "event_dwell_seconds", "event_timestam…` |
| catalog_rag | `{"documents": 40, "path": "catalog_rag.jsonl"}` |
| customer_context | `{"customers": 30, "assets": 170}` |
