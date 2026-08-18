export const HESITATION_LABELS = {
  SIZE_UNCERTAIN: '사이즈 불확실',
  PRICE_HESITANT: '가격 망설임',
  STYLE_DOUBT: '취향 확신 부족',
  STOCK_CONCERN: '재고 불확실',
  NONE: '망설임 신호 없음',
}

export const CTA_LABELS = {
  BOOK_FITTING: '피팅 예약하기',
  VIEW_STOCK: '재고 확인하기',
  CARE_BOOKING: '케어 예약하기',
  NONE: null,
}

/** CTA 버튼을 누른 뒤 보여줄 접수 확인 문구. 실제 예약·재고 시스템은 데모 범위 밖이라
 * "요청을 접수했다"는 사실까지만 알려준다 — 처리 결과를 지어내지 않는다. */
export const CTA_CONFIRMATIONS = {
  BOOK_FITTING: '피팅 예약을 요청했어요. 담당 부티크에서 곧 연락드려요.',
  VIEW_STOCK: '재고 확인을 요청했어요. 확인되는 대로 안내해드려요.',
  CARE_BOOKING: '케어 예약을 요청했어요. 담당 부티크에서 곧 연락드려요.',
}
