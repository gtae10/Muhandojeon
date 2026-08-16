import {
  MOCK_HEALTH,
  MOCK_CUSTOMERS,
  MOCK_CATALOG,
  MOCK_SCENARIOS,
  mockRunScenario,
  mockAdvise,
} from './mockData.js'

const TIMEOUT_MS = 2500

/** fetch 자체가 실패한 경우(백엔드 미기동, 타임아웃, CORS) — 이때만 목업으로 조용히 폴백한다. */
export class NetworkUnavailableError extends Error {
  constructor(message, options) {
    super(message, options)
    this.name = 'NetworkUnavailableError'
  }
}

/** 서버는 응답했지만 4xx/5xx인 경우 — 목업으로 덮지 않고 화면에 그대로 노출한다. */
export class ApiError extends Error {
  constructor(message, { status, detail } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function request(path, options = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
  let res
  try {
    res = await fetch(path, {
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      ...options,
    })
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new NetworkUnavailableError(`요청 시간이 초과됐어요 (${TIMEOUT_MS}ms): ${path}`, {
        cause: err,
      })
    }
    // fetch 가 던지는 TypeError — 서버 미기동, 네트워크 끊김, CORS 등
    throw new NetworkUnavailableError(`서버에 연결할 수 없어요: ${err.message}`, { cause: err })
  } finally {
    clearTimeout(timer)
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new ApiError(body.detail || `요청 실패 (${res.status})`, {
      status: res.status,
      detail: body.detail,
    })
  }
  return await res.json()
}

/** 'live' | 'mock' — 화면 상태 배지에서 그대로 읽는다. */
export const connectionState = { current: 'live' }

async function withFallback(realCall, mockValue) {
  try {
    const result = await realCall()
    connectionState.current = 'live'
    return result
  } catch (err) {
    if (err instanceof NetworkUnavailableError) {
      connectionState.current = 'mock'
      return typeof mockValue === 'function' ? mockValue() : mockValue
    }
    // ApiError: 서버가 실제로 응답했으니 연결 상태는 live 로 두고, 에러는 호출자에게 그대로 넘긴다.
    connectionState.current = 'live'
    throw err
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
