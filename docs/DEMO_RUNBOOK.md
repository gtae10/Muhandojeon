# 데모 당일 런북

목표는 둘이다. **빨간 에러 화면이 뜨지 않는 것**, 그리고 **크레딧이 발표 전에 바닥나지 않는 것**.
이 서비스는 업스트림이 다 죽어도 200 을 돌려주고 `X-Degraded: true` 로만 표시한다.

## T-30분 — 준비

```bash
cd <repo>
make check          # ruff + mypy + 픽스처 검증 (여기서 실패하면 나머지가 무의미하다)
make demo-check     # 시나리오 3종 기대값 + 문구 전문
make estimate       # 드라이런 비용 추정 (실제 호출 없음)
make demo           # 캐시 워밍업 + 데모 모드 기동 (:8000)
```

`make demo` 는 다음을 한다.

1. 시나리오 3종 예비 실행 + 기대값 검증 (LLM 응답이 있으면 `.cache/llm/` 에 캐시)
2. Persona Bot Lab 45세션 예비 실행 — **과금 상태면 예상 비용을 보여주고 확인을 요구한다**
   (건너뛰려면 `--skip-lab`, 확인 없이 진행하려면 `--yes`)
3. 서버 기동 (reload 없음)

## T-5분 — 5초 점검

```bash
curl -s localhost:8000/health/detail | jq '{status, data, budget, demo,
  adapters: [.adapters[] | {module, mode, last_status}],
  llm: {enabled: .llm.enabled, dry_run: .llm.dry_run, cache: .llm.cache_entries,
        vision: .llm.capabilities.vision}}'
```

체크 포인트

- [ ] `status: "ok"` — `degraded` 면 `data.load_errors` 확인 후 `make fixtures`
- [ ] `data`: `seed_source: "fixture"` / 상품 12 / 고객 6 / 개체 18 / 시나리오 3
- [ ] `data.label_mismatch: []` — 비어 있지 않으면 시나리오 이벤트와 라벨이 어긋난 것
- [ ] `budget.level: "ok"` — `warn` 이면 남은 여유를 확인하고 Lab 재실행을 자제한다
- [ ] `llm.capabilities.vision: false` — 확정값. 이미지 입력 경로는 없다
- [ ] `adapters`: 켜려던 모듈이 의도한 `mode`(mock/http)인지. http 인데 `last_error` 가 있으면
      그 팀원 서버가 죽은 것 → 그 모듈만 `mock` 으로 되돌린다
- [ ] `demo.demo_mode: true`, `demo.scenarios: 3`

브라우저 탭 4개를 미리 열어 둔다.

- `http://localhost:8000/lab` — Persona Bot Lab (결과가 이미 채워져 있어야 한다)
- `http://localhost:8000/ops` — 예산 게이지·세션 원가 (심사위원 질문 대응)
- `http://localhost:8000/docs` — 계약 시연
- 프론트 화면 (별도 레포)

## 시연 순서 (3분)

### 1. 상담 — 소유 자산을 근거로 (60초)

```bash
curl -s -X POST localhost:8000/demo/scenarios/D3/run \
  | jq '.response | {message, cta, citations, owned_assets_used}'
```

말할 것: 재고를 물어본 고객에게 **재고 안내 + 케어 예약**을 함께 제안한다. 근거는 그 고객이
실제로 가진 개체의 컨디션 71점(핸들 마모 임계 근접). 소유 자산 없이는 나올 수 없는 제안이다.

| id | 상황 | 고객 | 대상 | 세션 |
|---|---|---|---|---|
| `D1` | 사이즈 불확실 → 같은 last_code 보유 | CU-0003 | LX-0006 | SC-SIZE |
| `D2` | 가격 망설임 → 보유 자산 수명으로 답 | CU-0004 | LX-0001 | SC-PRICE |
| `D3` | 재고 확인 → 케어 임박 VIP (핵심 대사) | CU-0001 | LX-0002 | SC-STOCK |

### 2. 차별점 증명 — 전략 비교 (60초)

`/lab` 탭에서 전략별 전환율, 페르소나 × 전략 히트맵, 이탈 사유를 보여주고 세션 하나를 클릭해
대화 전문과 신뢰도 변화 근거를 띄운다.

**정직하게 말할 것**: LLM 을 연결하지 않은 상태의 수치는 규칙 모델의 결과다. 규칙 모델에는
"고객이 자기 물건 근거를 중시한다"는 가정이 들어 있어 S2 우세가 부분적으로 순환이다.
대시보드에도 그 캐비어트가 표시된다.

### 3. 운영 신뢰성 — 예산 (30초)

`/ops` 탭: 누적 사용액 게이지, 용도별 비용, **상담 세션 1건당 원가(원화)**, 남은 예산으로
가능한 Lab 잔여 실행 횟수.

말할 것: 상담 1건 원가가 얼마인지 알고 설계했다. 크레딧 100달러 안에서 하드 리밋 85달러를
두고 15달러를 발표 당일 여유분으로 남겼다. 하드 리밋에 닿으면 새 호출을 거부하고 캐시로만
응답하므로 데모는 계속 돌아간다.

### 4. 질문 대비 (30초)

- **"비전 모델 없이 컨디션을 어떻게 보나"** → 대회 API 는 텍스트 전용이라 이미지 채점을 API 에
  기대지 않는다. 컨디션은 백엔드가 **고전 CV(OpenCV)** 로 계산하고, 이 레이어의 계약
  (`POST /condition/score`)은 그대로다. 지금 목은 픽스처 값을 반환하며 이미지를 보지 않는다.
- **"데이터는 진짜냐"** → 외부 데이터셋이 미확정이라 지금은 손으로 쓴 픽스처다. 파일과 검증
  스크립트를 그대로 보여줄 수 있고(`fixtures/`, `make fixtures`), 데이터셋이 확정되면
  provider 한 곳만 바꿔 교체한다.
- **"상담 문구가 LLM 없이도 나오나"** → 결정적 템플릿(`app/clienteling_rules.py`)이 기준선이다.
  LLM 이 붙으면 같은 계약으로 문장 품질만 올라간다.

## 사고 대응

| 증상 | 대응 |
|---|---|
| 응답이 느리다 | 업스트림 대기. 타임아웃 5초 + 재시도 1회 후 자동 폴백된다 |
| `X-Degraded: true` | 폴백 중이지만 화면은 정상. 응답 `trace` 에 원인이 있다 |
| 특정 팀원 서버 죽음 | 그 모듈만 목으로: `INTENT_ADAPTER=mock make dev` |
| 네트워크 끊김 | 워밍업된 시나리오는 캐시로 돌아간다. 키 없이도 템플릿으로 완주 |
| 예산 경고(`warn`) | Lab 재실행을 멈추고 `make cache-stats` 로 히트율 확인. 캐시가 살아 있으면 재실행 비용은 0 |
| 예산 하드(`hard`) | 새 호출은 자동 거부된다. 데모는 캐시·템플릿으로 계속 돌아간다 |
| 시드가 비어 보인다 | `make fixtures` → `data.load_errors` 확인 |
| Lab 결과 없음 | `make lab --yes`(약 1초, 규칙 모델) 후 `/lab` 새로고침 |
| 시나리오 문구가 달라졌다 | `make demo-check` 로 기대값 위반 확인. 픽스처를 고쳤는지 의심 |
| 포트 충돌 | `make dev PORT=8100` |

## 절대 하지 말 것

- 발표 직전에 `fixtures/*.json` 수정 — 상품명·컨디션이 바뀌면 대본이 깨진다
- 발표 직전에 `REFERENCE_NOW` 변경 — 시간 기준이 전부 이동한다
- `make clean-cache` — 캐시를 지우면 같은 시나리오에 다시 과금된다
- 확인 없이 Lab 반복 실행 — `/lab/run` 은 `confirm` 을 요구하고 CLI 는 `--yes` 를 요구한다.
  그 게이트를 우회하지 않는다
- `ADAPTER_MODE=http` 전역 전환 — 한 모듈만 죽어도 전체가 폴백으로 보인다. 모듈별로 켠다
