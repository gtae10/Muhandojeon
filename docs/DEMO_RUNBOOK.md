# 데모 당일 런북

목표는 하나다. **발표 중 빨간 에러 화면이 뜨지 않는 것.**
이 서비스는 업스트림이 다 죽어도 200 을 돌려주고 `X-Degraded: true` 로만 표시한다.
그래도 아래 순서를 지키면 폴백 없이 정상 경로로 돌아간다.

## T-30분 — 준비

```bash
cd <repo>
make check                 # ruff + mypy + 헬스체크 + 시나리오 3종 검증 (전부 통과해야 한다)
make demo                  # DEMO_MODE=true 캐시 워밍업 + 서버 기동 (:8000)
```

`make demo` 는 다음을 한다.

1. SQLite 시드 (`data/processed/*.json` → `data/app.db`)
2. 시나리오 3종 예비 실행 + 기대값 검증 (LLM 응답이 있으면 `.cache/llm/` 에 캐시)
3. Persona Bot Lab 45세션 예비 실행 (캐시 채우기 + 대시보드에 결과 준비)
4. 서버 기동 (reload 없음)

## T-5분 — 5초 점검

```bash
curl -s localhost:8000/health/detail | jq '{status, adapters: [.adapters[] | {module, mode, last_status}], data, demo, llm}'
```

체크 포인트

- [ ] `status: "ok"` — `degraded` 면 `data.load_errors` 를 보고 `make data` 를 다시 돌린다
- [ ] `data`: 상품 40 / 고객 30 / 개체 170 / 세션 60
- [ ] `adapters`: 켜려던 모듈이 의도한 `mode`(mock/http)인지. http 인데 `last_error` 가 있으면
      그 팀원 서버가 죽은 것 → 그 모듈만 `mock` 으로 되돌린다
- [ ] `demo.demo_mode: true`, `demo.scenarios: 3`
- [ ] `llm`: 키를 넣었다면 `enabled: true` 이고 `cache_entries` 가 0 이 아니어야 한다
      (0 이면 워밍업이 안 된 것 → `DEMO_MODE=true python -m scripts.warm_cache`)

브라우저 탭 3개를 미리 열어 둔다.

- `http://localhost:8000/lab` — Persona Bot Lab (결과가 이미 채워져 있어야 한다)
- `http://localhost:8000/docs` — 계약 시연용
- 프론트 화면 (별도 레포)

## 시연 순서 (3분)

### 1. 개체 지문 → 컨디션 (30초)

```bash
curl -s -X POST localhost:8000/fingerprint/match -H 'content-type: application/json' \
  -d '{"image_path":"data/fingerprints/AS-000001/handle_01.jpg","customer_id":"CU-0001"}' | jq
curl -s -X POST localhost:8000/condition/score -H 'content-type: application/json' \
  -d '{"asset_id":"AS-000001"}' | jq '{score, next_service_months, findings}'
```

말할 것: 같은 모델이 아니라 **이 개체**를 식별한다. 컨디션 71점, 핸들 마모가 케어 임계에 근접.

### 2. 상담 — 소유 자산을 근거로 (60초)

```bash
curl -s -X POST localhost:8000/demo/scenarios/D3/run | jq '.response | {message, cta, citations, owned_assets_used}'
```

말할 것: 재고를 물어본 고객에게 **재고 안내 + 케어 예약**을 함께 제안한다. 근거는 그 고객이
실제로 가진 개체의 컨디션 71점. 소유 자산 없이는 나올 수 없는 제안이다.

시나리오 3종:

| id | 상황 | 고객 | 대상 상품 |
|---|---|---|---|
| `D1` | 사이즈 불확실 → 같은 사이즈 체계 보유 | CU-0014 | LX-0005 |
| `D2` | 가격 망설임 → 보유 자산 수명으로 답 | CU-0016 | LX-0019 |
| `D3` | 재고 확인 → 케어 임박 VIP (핵심 대사) | CU-0001 | LX-0025 |

### 3. 차별점 증명 — 전략 비교 (60초)

`/lab` 탭에서 전략별 전환율 막대와 페르소나 × 전략 히트맵을 보여준다.
세션 하나를 클릭해 대화 전문과 신뢰도 변화 근거를 띄운다.

말할 것: 같은 고객·같은 상품에 대해 전략만 바꿔 45세션을 돌렸다. S2(소유 자산 연계형)만
`cited_asset_ids` 를 채운다.

**정직하게 말할 것**: LLM 을 연결하지 않은 상태의 수치는 규칙 모델의 결과다. 규칙 모델에는
"고객이 자기 물건에 대한 근거를 중시한다"는 가정이 들어 있어 S2 우세가 부분적으로 순환이다.
대시보드에도 그 캐비어트가 표시된다. LLM 을 붙이면 같은 하네스로 실제 언어 효과를 측정한다.

### 4. 데이터 질문 대비 (30초)

- "이 데이터 진짜냐" → `docs/DATA_PROVENANCE.md` 필드별 출처 표. 행동 골격·구매 이력은 공개
  데이터셋, 럭셔리 서사(제품명·가격)와 컨디션·판별 이벤트는 규칙 생성. 어느 필드가 어디서
  왔는지 전부 적어 뒀다.
- "라이선스 문제 없냐" → `docs/DATA_LICENSES.md`. MVTec AD 는 비상업 라이선스라 미사용.
- "라벨은 누가 붙였냐" → 규칙 엔진. 그래서 AI1 학습셋의 상한이 규칙 재현이라는 한계까지 문서에 적어 뒀다.

## 사고 대응

| 증상 | 대응 |
|---|---|
| 응답이 느리다 | 업스트림 대기 중. 타임아웃 5초 + 재시도 1회 후 자동 폴백된다. 그대로 기다린다 |
| `X-Degraded: true` | 폴백 중이지만 화면은 정상. 발표 계속. 원인은 응답 `trace` 에 있다 |
| 특정 팀원 서버가 죽음 | 그 모듈만 목으로: 서버 재시작 없이 안 되면 `INTENT_ADAPTER=mock make dev` |
| 네트워크가 끊김 | `DEMO_MODE=true` 캐시로 워밍업된 시나리오는 그대로 돌아간다. LLM 키 없이도 템플릿 폴백으로 완주 |
| 데이터가 비어 보인다 | `make data && make seed` → `/health/detail` 의 `data` 확인 |
| Lab 결과가 없다 | `make lab` (45세션 ~1초) 후 `/lab` 새로고침 |
| 시나리오 문구가 달라졌다 | `make demo-check` 로 기대값 위반 확인. 카탈로그를 `--force` 로 재생성했는지 의심 |
| 포트 충돌 | `make dev PORT=8100` |

## 절대 하지 말 것

- 발표 직전에 `python -m scripts.build_catalog --force` — 상품명이 바뀌면 대본이 깨진다
- 발표 직전에 `REFERENCE_NOW` 변경 — 컨디션 점수가 전부 이동한다("71점" 대사 깨짐)
- `make clean-db` 후 시드 없이 서버 기동 — Lab 결과와 지문 등록이 사라진다
- `ADAPTER_MODE=http` 전역 전환 — 한 모듈만 죽어도 전체가 폴백으로 보인다. 모듈별 전환을 쓴다
