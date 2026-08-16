# AI 1 — 고객 분석 / Intent Sensing

담당: AI 1

## 역할
- 고객 망설임 유형 분류 (사이즈 불안 / 가치 확신 부족 / 타이밍·재고 등)
- 고객 페르소나 생성
- Intent Sensing: 온라인 행동 신호(장바구니 체류/이탈) + 오프라인 신호(착장 후 미구매 QR/직원 기록) 처리
- 제품 텍스처 이미지 기반 마모도 스코어링 (8일 스코프: 사진 비교 기반 목업으로 축소 권장)

## 백엔드로 넘길 출력 형식 (초안)
```json
{
  "intentType": "size_concern | value_uncertainty | timing_stock",
  "conditionScore": 71,
  "wearPoints": [{ "part": "핸들", "severity": "임계 근접" }]
}
```
