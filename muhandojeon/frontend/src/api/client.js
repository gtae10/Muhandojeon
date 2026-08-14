const BASE_URL = '/api' // 백엔드 팀원과 베이스 URL 확정되면 교체

/**
 * 제품 + 컨디션 정보 조회
 * GET /api/products/:productId
 * TODO(풀스택2 Backend): 응답 스키마 확정 필요
 *   { id, name, purchasedAt, conditionScore, wearPoints: [{part, severity}] }
 */
export async function fetchProduct(productId) {
  const res = await fetch(`${BASE_URL}/products/${productId}`)
  if (!res.ok) throw new Error('제품 정보를 불러오지 못했습니다')
  return res.json()
}

/**
 * 촬영한 텍스처 이미지 업로드 → 지문 등록 / 상태 비교
 * POST /api/fingerprint  (multipart/form-data)
 * TODO(AI1 담당): 응답에 마모도 스코어 포함 여부 확인
 */
export async function registerFingerprint(productId, imageBlob) {
  const formData = new FormData()
  formData.append('productId', productId)
  formData.append('image', imageBlob)

  const res = await fetch(`${BASE_URL}/fingerprint`, {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) throw new Error('지문 등록에 실패했습니다')
  return res.json()
}

/**
 * 상담 메시지 전송
 * POST /api/chat
 * TODO(AI2 담당): 일반 JSON 응답인지 스트리밍(SSE)인지 확정 후
 *   스트리밍이면 이 함수를 EventSource/ReadableStream 처리로 교체
 */
export async function sendChatMessage(productId, message) {
  const res = await fetch(`${BASE_URL}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ productId, message }),
  })
  if (!res.ok) throw new Error('상담 응답을 받지 못했습니다')
  return res.json() // 예상: { reply: string }
}
