# scripts/_deferred — 외부 데이터셋 확정 전까지 보류

**외부 데이터셋이 확정되지 않아 실행 경로에서 분리했다.** 삭제하지 않고 그대로 두었으니
데이터셋이 정해지면 되살려 쓴다. 지금 시드 데이터는 `fixtures/*.json`(손으로 작성) 이며
접근은 전부 `app/data/provider.py` 의 `SeedDataProvider` 를 경유한다.

| 파일 | 하던 일 | 되살릴 때 |
|---|---|---|
| `fetch_data.py` | Kaggle 데이터셋 획득(H&M / Fashion Product Images / 클릭스트림), 실패 시 안내 | 확정 데이터셋을 `SOURCES` 에 등록 |
| `build_catalog.py` | styles.csv → 럭셔리 카탈로그 40개(LLM/템플릿 리라이팅) | `fixtures/products.json` 을 대체할 산출물 생성기 |
| `build_customers.py` | H&M transactions lazy scan → 고객 30명 + 개체 170개(컨디션 결정적 계산) | `fixtures/customers.json`·`assets.json` 대체 |
| `build_sessions.py` | 클릭스트림 → 이탈 세션 60개 + 망설임 라벨 | `fixtures/session_events.json` 대체 |
| `export_for_team.py` | AI1 학습셋(parquet) / AI2 RAG·컨텍스트 export | 데이터셋 확정 후 재실행 |
| `synth_fallback.py` | 외부 데이터 0개일 때 원시 입력 합성 | 그대로 |
| `gen_provenance_doc.py` | 필드별 출처 문서 생성 | 그대로 |
| `seed_db.py` | 정규화 산출물 → SQLite 적재 | SQLite 는 이제 런타임 산출물(Lab 결과·LLM 사용량)만 담는다. 시드 데이터를 DB 에 넣던 전제가 바뀌었으므로 재작성 필요 |
| `register_fingerprint.py` | 개체 지문 촬영 품질 검증 + 경로 등록(`fingerprints` 테이블) | 개체 지문은 백엔드 담당 범위. 테이블도 제거됐으므로 provider 기반으로 재작성 |

## 되살리는 절차

1. 확정된 데이터셋을 `fetch_data.py` 의 `SOURCES` 에 등록하고 획득
2. `app/data/provider.py` 의 `DatasetProvider` 를 구현(현재 `NotImplementedError` 스텁)
3. `SEED_SOURCE=dataset` 으로 전환 — 오케스트레이터·목 어댑터는 수정하지 않는다
4. `python -m scripts.validate_fixtures --provider dataset` 로 계약·참조 정합성 확인

## 주의

이 디렉토리는 ruff / mypy 검사 대상에서 제외돼 있다(`pyproject.toml` 의 `extend-exclude`).
보류 코드가 현재 앱 구조(제거된 DB 테이블, 슬림해진 `scripts/common.py`)와 어긋나 있어도
`make check` 를 막지 않게 하려는 의도다. 되살릴 때 제외 목록에서 빼고 다시 통과시킨다.

관련 문서도 함께 보류: `docs/_deferred_DATA_PROVENANCE.md`, `docs/_deferred_DATA_LICENSES.md`,
데이터 산출물은 `data/_deferred/`.
