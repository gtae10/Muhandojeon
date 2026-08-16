import {
  MOCK_HEALTH,
  MOCK_CUSTOMERS,
  MOCK_CATALOG,
  MOCK_SCENARIOS,
  mockRunScenario,
  mockAdvise,
} from './mockData.js'

const TIMEOUT_MS = 2500

async function request(path, options = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
  try {
    const res = await fetch(path, {
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      ...options,
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || `요청 실패: ${res.status}`)
    }
    return await res.json()
  } finally {
    clearTimeout(timer)
  }
}

/** true를 반환하면 실서버 응답, false면 목업 폴백이 적용됐다는 뜻. 화면에서 배지로 씀. */
export const isMockMode = { current: false }

async function withFallback(realCall, mockValue) {
  try {
    const result = await realCall()
    isMockMode.current = false
    return result
  } catch {
    isMockMode.current = true
    return typeof mockValue === 'function' ? mockValue() : mockValue
  }
}

// ---- 읽기 전용 편의 엔드포인트 ----

export function getCustomers(tier) {
  const q = tier ? `?tier=${tier}` : ''
  return withFallback(() => request(`/customers${q}`), MOCK_CUSTOMERS)
}

export function getCatalog(category) {
  const q = category ? `?category=${category}` : ''
  return withFallback(() => request(`/catalog${q}`), MOCK_CATALOG)
}

// ---- 데모 시나리오 ----

export function getDemoScenarios() {
  return withFallback(() => request('/demo/scenarios'), MOCK_SCENARIOS)
}

export function runDemoScenario(scenarioId) {
  return withFallback(
    () => request(`/demo/scenarios/${scenarioId}/run`, { method: 'POST' }),
    () => mockRunScenario(scenarioId),
  )
}

// ---- 오케스트레이터 단일 진입점 ----

/**
 * @param {object} payload AdviseRequest — { customer_id, target_product_id, session_events?, strategy_id?, history? }
 */
export function advise(payload) {
  return withFallback(
    () => request('/session/advise', { method: 'POST', body: JSON.stringify(payload) }),
    () => mockAdvise(),
  )
}

// ---- 헬스체크 ----

export function getHealth() {
  return withFallback(() => request('/health'), MOCK_HEALTH)
}
