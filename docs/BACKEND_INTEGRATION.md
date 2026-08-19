# 백엔드 연동 — 이미 만들어진 API 와 계약의 차이

`gtae10/Muhandojeon` 의 `backend/` 는 이미 동작하는 구현이 있고, 필드 이름이 이 레포의 계약
(`docs/CONTRACTS.md`)과 다르다. 통합 레이어의 HTTP 어댑터는 **양쪽을 모두 받아들인다**:
먼저 계약 모델로 검증하고, 실패하면 레거시 매퍼로 필드를 옮겨 다시 검증한다. 이 경로를 타면
`/health/detail` 의 `last_status` 가 `ok(legacy-mapped)` 로 표시된다.

즉 **백엔드를 고치지 않아도 붙는다.** 다만 아래 "반드시 채워야 하는 것" 하나는 예외다.

## 엔드포인트 대응

| 계약 (이 레포) | 팀 백엔드 (현재) | 어댑터 동작 |
|---|---|---|
| `GET /assets/{customer_id}` | `GET /api/users/{user_id}/assets` | 계약 경로 먼저 → 실패 시 레거시 경로 시도 |
| `POST /clienteling/reply` | `POST /api/chat` | 계약 경로 먼저 → 실패 시 `/api/chat` 시도 |
| `POST /condition/score` | `POST /api/fingerprint` 응답에 포함 | 응답 필드 매핑 |
| `POST /fingerprint/match` | `POST /api/fingerprint` | `is_new_registration` → `is_match` 반전 |
| `POST /intent/classify` | `app/services/intent_service.py` (경로 미확정) | `intent`/`label`/`score`/`reasons` 키 흡수 |

## 필드 매핑 (자동 처리됨)

| 계약 필드 | 백엔드 필드 | 변환 |
|---|---|---|
| `customer_id` | `user_id` | 그대로 |
| `purchased_at` | `purchase_date` | 그대로(ISO) |
| `last_scanned_at` | `last_assessed` | 그대로 |
| `findings[]` (part/severity/note) | `wear_details` / `wear_detail` (횟수·불리언) | `scratches`→exterior LOW(3건 이상이면 HIGH), `cracks`→exterior HIGH, `color_fade`→exterior MEDIUM, `hardware_tarnish`→hardware MEDIUM, `lining_damage`→lining MEDIUM, `strap_wear`→handle MEDIUM |
| `condition_score` | `condition_score` | 그대로. 없으면 `condition_grade` 로 근사(Mint 97 / Excellent 88 / Good 76 / Fair 62 / Poor 40) |
| `next_service_months` | (없음) | 컨디션 점수로 계산 (70 도달까지, 연 8점 감소 가정) |
| `tier` | (없음) | 개체 수로 추정 (8+ VIP / 3~7 ESTABLISHED / 그 외 NEW) |
| `message` | `reply` | 그대로 |
| `is_match` | `is_new_registration` | 최초 등록이면 매칭 실패로 본다 |
| `similarity` | (없음) | 없으면 0.9(기존 개체) / 0.0(최초 등록) |
| `price_krw` | `price_usd` | **자동 변환하지 않는다.** 환율을 임의로 박으면 발표 화면 숫자가 틀린다 → 아래 참고 |

### 가격 필드에 대해

계약은 `price_krw`(원, 정수), 백엔드는 `price_usd`(달러, float)다. 임의 환율로 곱하면 화면
숫자와 발표 대본이 어긋나므로 **어댑터에서 변환하지 않는다.** 카탈로그는 통합 레이어의
`fixtures/products.json`(원화 고정, provider 경유)을 단일 출처로 쓰고, 백엔드의 상품 가격은
쓰지 않는 것을 권한다. 굳이 백엔드 값을 쓰려면 `price_krw` 를 백엔드에 추가하는 편이 안전하다.

## 컨디션 채점 — 비전 API 부재(확정)

대회 제공 API 에는 **비전 모델이 없다**. 그래서 이미지 기반 컨디션 채점은 API 로 하지 않고
**백엔드 담당이 고전 CV(OpenCV)로 구현**한다. 통합 레이어의 계약은 그대로다.

- 계약: `POST /condition/score` — 입력 `{asset_id, image_paths[]}`, 출력
  `{asset_id, score, findings[], next_service_months, confidence}` (변경 없음)
- 현재 목: 이미지를 **보지 않고** 시드 픽스처의 점수·소견을 반환한다(`image_paths` 가 와도 무시).
- 교체 방법: `CONDITION_ADAPTER=http CONDITION_BASE_URL=... make dev` — 코드 수정 없음.
- `findings[].part` 는 계약 열거형(handle/corner/hardware/stitching/lining/exterior/strap/sole/
  upper/edge_coat/dial/bracelet)을 그대로 쓴다. `wear_details` 형태로 주면 어댑터가 매핑한다.

## 반드시 채워야 하는 것 — `cited_asset_ids`

현재 `POST /api/chat` 응답은 `{session_id, reply, model_used}` 뿐이다. **어떤 소유 개체를 근거로
답했는지가 없다.** 이건 필드 하나가 빠진 문제가 아니라 **제품의 차별점을 측정할 수 없는 상태**다.

- 오케스트레이터는 인용이 없으면 `owned_assets_used=false` + 응답 헤더 `X-Owned-Assets-Used: false`
  로 표시하고 경고 로그를 남긴다.
- Persona Bot Lab 의 전략 S2(소유 자산 연계형)는 인용 여부로 평가되므로, 이 필드가 없으면
  S2 의 효과를 0으로 측정한다.
- 임시 방편으로 어댑터가 **본문에서 `AS-\d{4,6}` 패턴을 회수**하지만, 문장이 "2023년의 오프닝"
  처럼 id 없이 자연어로만 인용하면 잡히지 않는다.

따라서 AI2/백엔드 담당은 응답에 다음 두 필드를 추가해 주면 된다.

```json
{
  "session_id": "...",
  "reply": "...",
  "cited_asset_ids": ["AS-0010"],
  "cta": "BOOK_FITTING"
}
```

`cta` 는 없으면 `NONE` 으로 처리되지만, 프론트 버튼이 이 값으로 렌더되므로 채우는 편이 좋다.

## 전환 방법

모듈별로 하나씩 켠다(전역 `ADAPTER_MODE=http` 는 전부 켜므로 마지막에).

```bash
# 자산 조회만 실제 백엔드로 (백엔드는 :8001 — asset/fingerprint/condition 을 한 프로세스가 서빙)
ASSET_ADAPTER=http ASSET_BASE_URL=http://localhost:8001 make dev

# 상담까지 실제 AI2 로 (AI2 는 :8102)
ASSET_ADAPTER=http CLIENTELING_ADAPTER=http CLIENTELING_BASE_URL=http://localhost:8102 make dev
```

확인:

```bash
curl -s localhost:8000/health/detail | jq '.adapters'
# mode 가 http 이고 last_status 가 ok 또는 ok(legacy-mapped) 인지 본다.

curl -s -D- -o/dev/null -X POST localhost:8000/session/advise \
  -H 'content-type: application/json' -d @contracts/examples/session_advise.request.json | grep -i x-
# X-Degraded: false / X-Owned-Assets-Used: true 여야 정상이다.
```

업스트림이 죽어 있어도 `/session/advise` 는 200 을 돌려주고 `X-Degraded: true` 로만 표시한다
(화면에 에러를 노출하지 않는 것이 데모 요구사항). 어느 단계가 폴백됐는지는 응답 `trace` 에 있다.

## 매핑 테스트

레거시 응답 모양은 테스트로 고정돼 있다. 백엔드 응답이 바뀌면 여기서 먼저 깨진다.

```bash
uv run pytest tests/test_legacy_mapping.py -q
```
