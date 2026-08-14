# Muhandojeon

프로젝트는 파트별 디렉토리로 나뉘어 있다.

| 파트 | 위치 | 문서 |
|---|---|---|
| 통합/데모 레이어 (오케스트레이터·목 어댑터·LLM 게이트웨이·Persona Bot Lab) | 리포 루트 (`app/`, `contracts/`, `fixtures/`, `config/`, `scripts/`, `tests/`) | [`docs/INTEGRATION.md`](docs/INTEGRATION.md) · [`docs/HANDOFF.md`](docs/HANDOFF.md) |
| 백엔드 | `backend/` | `backend/README.md` |
| AI · 프론트 | `muhandojeon/` | `muhandojeon/README.md` |

## 통합 레이어 빠른 시작

```bash
make setup      # uv venv(3.11) + 의존성 + .env
make check      # ruff + mypy + 시드 픽스처 검증
make dev        # 서버 :8000 (목 모드)
```

- 팀 인터페이스(6개 엔드포인트): [`docs/CONTRACTS.md`](docs/CONTRACTS.md)
- 기존 백엔드 API 와의 필드 매핑: [`docs/BACKEND_INTEGRATION.md`](docs/BACKEND_INTEGRATION.md)
- 발표 당일 절차: [`docs/DEMO_RUNBOOK.md`](docs/DEMO_RUNBOOK.md)
- **이어받아 작업하는 사람은 [`docs/HANDOFF.md`](docs/HANDOFF.md) 를 먼저 읽는다.**

### 알아둘 제약 (확정)

1. **대회 API 는 텍스트 전용이다(비전 모델 없음).** 이미지 입력을 전제한 설계를 하지 않는다.
   컨디션 이미지 채점은 백엔드가 고전 CV 로 구현하며 계약은 그대로다.
2. **크레딧 총액 100달러, 초과 시 복구 불가.** 모든 LLM 호출은 `app/llm/` 게이트웨이를 지나고
   용도 태그를 갖는다. 하드 리밋 85달러를 넘길 호출은 실행 전에 거부된다.
   Lab 실행 전에는 `make estimate` 로 비용을 확인한다.

