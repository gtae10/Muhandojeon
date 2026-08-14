# data/_deferred — 데이터셋 기반 산출물 (보류)

외부 데이터셋이 확정되지 않아 실행 경로에서 분리했다. **런타임은 이 디렉토리를 읽지 않는다.**
현재 시드 데이터는 `fixtures/*.json` 이고 접근은 `app/data/provider.py` 를 경유한다.

| 경로 | 내용 | 만든 스크립트 |
|---|---|---|
| `processed/catalog_luxury.json` | 럭셔리 카탈로그 40개 (Fashion Product Images 파생 + 리라이팅) | `scripts/_deferred/build_catalog.py` |
| `processed/customers.json` | 고객 30명 / 개체 170개 (컨디션 결정적 계산, 71점 보정 포함) | `scripts/_deferred/build_customers.py` |
| `processed/sessions.json` | 이탈 세션 60개 + 망설임 라벨 | `scripts/_deferred/build_sessions.py` |
| `processed/provenance.json` | 빌드별 출처 기록 | 빌더 공용 |
| `processed/images/` | 상품 이미지 사본 60x80 (gitignore) | `build_catalog.py` |
| `exports/intent_trainset.parquet` | AI1 학습셋 60행 (8:2 계층분할) | `scripts/_deferred/export_for_team.py` |
| `exports/catalog_rag.jsonl` | AI2 RAG 문서 40개 | 동일 |
| `exports/customer_context.json` | AI2 고객 컨텍스트 30명 | 동일 |

데이터셋이 확정되면 `scripts/_deferred/README.md` 의 절차대로 되살린다. 그때 이 산출물은
새 데이터셋 기준으로 다시 생성되므로 **참고 자료로만** 본다(스키마 예시로는 여전히 유용하다).
