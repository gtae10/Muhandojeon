# 데이터셋 라이선스와 사용 범위

발표 Q&A 방어용 문서. "그 데이터 써도 되는 거냐"는 질문에 이 표로 답한다.
자동 획득 스크립트는 `scripts/fetch_data.py`, 획득 결과는 `data/raw/FETCH_STATUS.json`.

## 요약 표

| 용도 | 데이터셋 | 출처 | 라이선스 | 상업적 사용 | 우리가 사용한 범위 |
|---|---|---|---|---|---|
| 고객·거래 이력 | H&M Personalized Fashion Recommendations | [Kaggle competition](https://www.kaggle.com/competitions/h-and-m-personalized-fashion-recommendations/data) | 대회 규칙(Competition Rules) — 참가자에게 **비상업적 연구·대회 목적**으로 허용 | ❌ (대회 규칙상 상업적 사용 불가) | `transactions_train.csv` 의 `customer_id`, `article_id`, `t_dat` 3개 컬럼만. 고객 30명 샘플의 **구매 건수와 구매 시점 간격**만 사용하고 원본 id 는 저장하지 않는다(해시만 기록) |
| 상품 카탈로그 + 이미지 | Fashion Product Images (Small) | [Kaggle dataset](https://www.kaggle.com/datasets/paramaggarwal/fashion-product-images-small) | 데이터셋 페이지 표기 기준 공개 데이터(원저작자 Param Aggarwal). 재배포 시 출처 표기 | ⚠️ 조건부 — 원본 상품명·브랜드명을 그대로 노출하지 않음 | `styles.csv` 의 카테고리·색상·연도 속성 40행 + 해당 이미지 40장. **상품명은 전량 리라이팅**하여 원본 브랜드명이 화면에 나오지 않게 했다 |
| 세션 클릭스트림 | E-commerce Clickstream and Transaction Dataset | [Kaggle dataset](https://www.kaggle.com/datasets/waqi786/e-commerce-clickstream-and-transaction-dataset) | CC0 / 공개 도메인 표기 | ✅ | 이벤트 종류·개수·순서, 이탈 여부. 60개 세션의 **행동 골격**으로만 사용 |
| 결함 텍스처 (선택) | MVTec AD (leather, carpet) | [MVTec 공식](https://www.mvtec.com/company/research/datasets/mvtec-ad) | **CC BY-NC-SA 4.0** | ❌ **상업적 사용 금지** | 미사용(현재 빌드에 포함되지 않음). 수동 배치 시에만 컨디션 소견의 **시각 참고 자료**로 쓰며 학습·재배포하지 않는다 |

## MVTec AD 취급 규칙 (하드 룰)

- **자동 다운로드하지 않는다.** `scripts/fetch_data.py` 는 `kind="manual"` 로 두고 안내만 출력한다.
- `data/raw/mvtec/` 에 사람이 직접 놓았을 때만 인식하고, 없으면 조용히 건너뛴다.
- CC BY-NC-SA 4.0 이므로 **상업적 사용 금지 / 동일조건 변경허락(ShareAlike)** 이다.
  해커톤 데모·연구 목적 범위를 벗어나 제품에 넣으면 안 된다.
- 사용했다면 발표 자료에 출처와 라이선스를 표기하고, 파생물 재배포는 하지 않는다.

## H&M 데이터 접근에 대해

competition 데이터는 **웹에서 대회 규칙에 동의**해야 API 다운로드가 열린다. 동의 전에는
파일 목록 조회는 되지만 다운로드가 403 으로 막힌다. 동의 후 재실행하면 자동으로 external
경로로 전환된다.

```
https://www.kaggle.com/competitions/h-and-m-personalized-fashion-recommendations/rules
→ "I Understand and Accept" → make data 재실행
```

동의 없이도 파이프라인은 완주한다(합성 거래로 폴백). 어느 슬라이스가 합성인지는
`docs/DATA_PROVENANCE.md` 와 `data/processed/provenance.json` 에 기록된다.

## 개인정보·식별자 취급

- 원본 `customer_id`(64자 해시)는 **저장하지 않는다.** 우리 id(`CU-0001`)로 치환하고
  대조가 필요할 때를 위해 `stable_hash` 값만 남긴다(`customers.json` 의 `source.raw_customer_id_sha`).
- 고객 표시 이름(`display_name`)은 **전부 합성**이다. 원본 데이터셋에는 이름 컬럼이 없다.
- 개체 지문 이미지는 팀원 소지품 직접 촬영분이며 `data/fingerprints/` 는 git 에 올리지 않는다
  (`.gitignore`). 발표 후 폐기 여부는 촬영 당사자가 결정한다.

## 우리 산출물의 라이선스 상태

| 산출물 | 성격 |
|---|---|
| `data/processed/catalog_luxury.json` | 원본 속성에서 파생 + 제품명·소재·가격 전량 창작. 원본 상품명은 `source.raw_display_name` 에만 남아 있다 |
| `data/processed/customers.json` | 구매 건수·간격만 원본 파생, 나머지(컨디션·소견·이름·티어) 전량 규칙 생성 |
| `data/processed/sessions.json` | 이벤트 골격은 원본, 판별 이벤트·시간축은 규칙 합성 |
| `exports/*` | 위 세 파일에서 파생. 팀 내부 배포용 |
| `data/processed/images/*.jpg` | Fashion Product Images 원본 이미지 사본(리사이즈 없음). 외부 재배포 금지 |
