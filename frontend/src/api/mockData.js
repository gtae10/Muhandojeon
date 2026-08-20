/**
 * 백엔드 없이도 화면을 확인할 수 있도록 만든 오프라인 목업 데이터.
 * fixtures/*.json, data/demo_scenarios.yaml 구조를 그대로 반영했다.
 * D1/D2/D3 응답은 실제 백엔드를 띄워 검증한 응답을 그대로 옮겨온 것이다.
 * 백엔드가 붙으면 api/client.js가 실제 응답을 우선 쓰고, 실패할 때만 이걸 쓴다.
 */

export const MOCK_HEALTH = { status: 'ok', adapter_mode: 'mock', demo_mode: false }

export const MOCK_CUSTOMERS = {
  total: 6,
  items: [
    { customer_id: 'CU-0001', display_name: '한지원', tier: 'VIP', asset_count: 5, care_due: 2, min_condition: 63 },
    { customer_id: 'CU-0002', display_name: '오세린', tier: 'VIP', asset_count: 4, care_due: 2, min_condition: 54 },
    { customer_id: 'CU-0003', display_name: '정민서', tier: 'ESTABLISHED', asset_count: 3, care_due: 0, min_condition: 81 },
    { customer_id: 'CU-0004', display_name: '배도윤', tier: 'ESTABLISHED', asset_count: 3, care_due: 0, min_condition: 82 },
    { customer_id: 'CU-0005', display_name: '서하람', tier: 'NEW', asset_count: 1, care_due: 0, min_condition: 97 },
    { customer_id: 'CU-0006', display_name: '문가율', tier: 'ESTABLISHED', asset_count: 2, care_due: 0, min_condition: 84 },
  ],
}

// 실제 카탈로그는 12종 — 데모 시나리오의 대상 상품 + 인용 자산의 상품만 담았다.
export const MOCK_CATALOG = {
  total: 5,
  items: [
    {
      product_id: 'LX-0001', name: 'Aurelia Top Handle', category: 'BAG',
      material: '그레인 토고 카프스킨 / 팔라듐 하드웨어', color: 'Noir', collection: 'Maison Nord',
      price_krw: 8900000, image_url: null,
    },
    {
      product_id: 'LX-0002', name: 'Solène Shoulder', category: 'BAG',
      material: '박스카프 카프스킨 / 골드 하드웨어', color: 'Cognac', collection: 'Atelier Lumière',
      price_krw: 6400000, image_url: null,
    },
    {
      product_id: 'LX-0005', name: 'Aurelia Derby', category: 'SHOES',
      material: '박스카프 카프스킨 / 굿이어 웰트', color: 'Ebony', collection: 'Maison Nord',
      price_krw: 2400000, image_url: null,
    },
    {
      product_id: 'LX-0006', name: 'Aurelia Oxford', category: 'SHOES',
      material: '패티나 카프 / 굿이어 웰트', color: 'Cognac', collection: 'Maison Nord',
      price_krw: 2700000, image_url: null,
    },
    {
      product_id: 'LX-0011', name: 'Lisière Card Holder', category: 'WALLET',
      material: '그레인 토고 카프스킨', color: 'Noir', collection: 'Atelier Lumière',
      price_krw: 1500000, image_url: null,
    },
  ],
}

export const MOCK_SCENARIOS = {
  total: 3,
  items: [
    {
      id: 'D1',
      title: '사이즈 불확실 — 같은 라스트 보유 고객',
      narrative:
        '신발 사이즈를 정하지 못해 망설이던 고객에게, AI가 예전에 구매하신 같은 라스트 신발 기록을 근거로 정확한 사이즈를 안내해요.',
      customer_id: 'CU-0003',
      target_product_id: 'LX-0006',
    },
    {
      id: 'D2',
      title: '가격 망설임 — 보유 자산의 수명으로 답한다',
      narrative:
        '가격이 부담돼서 망설이던 고객에게, AI가 할인 대신 이미 갖고 계신 제품이 몇 년째 얼마나 잘 관리되고 있는지 보여주며 설득해요.',
      customer_id: 'CU-0004',
      target_product_id: 'LX-0001',
    },
    {
      id: 'D3',
      title: '재고 확인 — 케어 시점이 임박한 VIP',
      narrative:
        '재고가 있는지 확인하던 고객에게, AI가 원하시는 상품의 재고를 안내하면서 예전에 구매하신 제품도 관리가 필요한 시점이라는 걸 함께 짚어드려요.',
      customer_id: 'CU-0001',
      target_product_id: 'LX-0002',
    },
  ],
}

const MOCK_ADVISE_BY_SCENARIO = {
  D1: {
    hesitation_type: 'SIZE_UNCERTAIN',
    confidence: 0.95,
    signals: [
      { name: 'size_guide_repeat', weight: 0.8, evidence: 'size_guide 3회 조회 (38.5, 39, 39)' },
      { name: 'cart_without_checkout', weight: 0.2, evidence: '장바구니 담기 후 결제 진입 없음' },
    ],
    message:
      '2023년에 함께하신 Aurelia Derby은 3년 사용에 컨디션 81점으로 잘 관리되고 있습니다(앞창 마모 진행). Aurelia Derby과 Aurelia Oxford은 같은 라스트 계열입니다. 그때 맞춰 드린 치수를 그대로 적용하면 편차가 거의 없습니다. 현재 준비된 사이즈는 38.5, 39, 40입니다. 가까운 부티크에서 피팅 시간을 잡아 드릴까요?',
    cta: 'BOOK_FITTING',
    cited_asset_ids: ['AS-0010', 'AS-0011'],
    citations: [
      {
        asset_id: 'AS-0010', product_name: 'Aurelia Derby', condition_score: 81,
        headline_finding: '앞창 마모 진행', next_service_months: 6,
      },
      {
        asset_id: 'AS-0011', product_name: 'Vesper Ankle Boot', condition_score: 90,
        headline_finding: '볼 부분 주름 자연 발생', next_service_months: 24,
      },
    ],
    owned_assets_used: true,
    no_assets: false,
    degraded: false,
  },
  D2: {
    hesitation_type: 'PRICE_HESITANT',
    confidence: 0.95,
    signals: [
      { name: 'price_sensitivity', weight: 0.74, evidence: '가격 필터 변경 1회 (상한 4000000원), 동일 카테고리 저가 상품 2회 조회' },
      { name: 'cart_without_checkout', weight: 0.2, evidence: '장바구니 담기 후 결제 진입 없음' },
    ],
    message:
      '2023년에 함께하신 Lisière Card Holder은 2년 사용에 컨디션 82점으로 잘 관리되고 있습니다(엣지 코트 상태 양호). Lisière Card Holder을 2년 쓰신 지금도 컨디션 82점입니다. 같은 제법이라 연 단위로 보면 유지 비용이 낮습니다. 가까운 부티크에서 피팅 시간을 잡아 드릴까요?',
    cta: 'BOOK_FITTING',
    cited_asset_ids: ['AS-0013'],
    citations: [
      {
        asset_id: 'AS-0013', product_name: 'Lisière Card Holder', condition_score: 82,
        headline_finding: '엣지 코트 상태 양호', next_service_months: 12,
      },
    ],
    owned_assets_used: true,
    no_assets: false,
    degraded: false,
  },
  D3: {
    hesitation_type: 'STOCK_CONCERN',
    confidence: 0.95,
    signals: [
      { name: 'availability_check', weight: 0.7, evidence: '재고 조회 2회, 배송 정보 1회' },
      { name: 'cart_without_checkout', weight: 0.2, evidence: '장바구니 담기 후 결제 진입 없음' },
    ],
    message:
      '2022년에 함께하신 Aurelia Top Handle은 4년 사용에 컨디션 71점, 약 1개월 뒤 케어 권장 시점입니다(핸들 표면 마모 진행, 케어 임계 근접). Solène Shoulder의 현재 가용 사이즈는 25, 30입니다. 남은 수량이 적어 재입고 일정은 확정되지 않았습니다. 케어 예약을 함께 잡아 드릴까요?',
    cta: 'CARE_BOOKING',
    cited_asset_ids: ['AS-0001', 'AS-0003'],
    citations: [
      {
        asset_id: 'AS-0001', product_name: 'Aurelia Top Handle', condition_score: 71,
        headline_finding: '핸들 표면 마모 진행, 케어 임계 근접', next_service_months: 1,
      },
      {
        asset_id: 'AS-0003', product_name: 'Marée Tote', condition_score: 92,
        headline_finding: '외관 결 유지', next_service_months: 30,
      },
    ],
    owned_assets_used: true,
    no_assets: false,
    degraded: false,
  },
}

export function mockRunScenario(scenarioId) {
  const scenario = MOCK_SCENARIOS.items.find((s) => s.id === scenarioId)
  const response = MOCK_ADVISE_BY_SCENARIO[scenarioId]
  if (!scenario || !response) {
    throw new Error(`목업 시나리오를 찾을 수 없어요: ${scenarioId}`)
  }
  return { scenario, response, check: { passed: true } }
}

export function mockAdvise() {
  return {
    hesitation_type: 'NONE',
    confidence: 0,
    signals: [],
    message: '(오프라인 목업) 세션 신호가 없어 일반 제안 모드로 응답했어요. 실제 백엔드가 연결되면 진짜 상담 문구가 나와요.',
    cta: 'NONE',
    citations: [],
    owned_assets_used: false,
    no_assets: true,
    degraded: false,
  }
}

// ---- 자유 상담(/chat) 오프라인 목업 — 서버 자체에 연결할 수 없을 때만 쓴다 ----
// (서버가 mock 어댑터로 응답하는 것과는 다르다: 그건 이미 'live' 다.)

// GET /assets/{customer_id} 실제 응답 그대로 (케어 임박 우선 정렬 포함).
const MOCK_ASSETS_BY_CUSTOMER = {
  'CU-0001': [
    {
      asset_id: 'AS-0005', customer_id: 'CU-0001', product_id: 'LX-0010', product_name: 'Lisière Long Wallet',
      category: 'WALLET', purchased_at: '2020-09-14T00:00:00+09:00', condition_score: 63,
      findings: [
        { part: 'edge_coat', severity: 'HIGH', note: '엣지 코트 대부분 손실' },
        { part: 'stitching', severity: 'MEDIUM', note: '접합부 스티치 이완' },
      ],
      next_service_months: 0, last_scanned_at: null,
    },
    {
      asset_id: 'AS-0001', customer_id: 'CU-0001', product_id: 'LX-0001', product_name: 'Aurelia Top Handle',
      category: 'BAG', purchased_at: '2022-04-16T00:00:00+09:00', condition_score: 71,
      findings: [
        { part: 'handle', severity: 'MEDIUM', note: '핸들 표면 마모 진행, 케어 임계 근접' },
        { part: 'corner', severity: 'MEDIUM', note: '코너 4곳 마찰, 각 세우기 필요' },
      ],
      next_service_months: 1, last_scanned_at: '2026-07-03T14:20:00+09:00',
    },
    {
      asset_id: 'AS-0004', customer_id: 'CU-0001', product_id: 'LX-0005', product_name: 'Aurelia Derby',
      category: 'SHOES', purchased_at: '2023-11-08T00:00:00+09:00', condition_score: 76,
      findings: [
        { part: 'sole', severity: 'MEDIUM', note: '앞창 마모 진행' },
        { part: 'upper', severity: 'LOW', note: '볼 부분 주름 자연 발생' },
      ],
      next_service_months: 5, last_scanned_at: '2026-06-30T10:15:00+09:00',
    },
    {
      asset_id: 'AS-0002', customer_id: 'CU-0001', product_id: 'LX-0008', product_name: 'Meridian Chronograph',
      category: 'WATCH', purchased_at: '2021-06-05T00:00:00+09:00', condition_score: 88,
      findings: [{ part: 'bracelet', severity: 'LOW', note: '브레이슬릿 유격 없음' }],
      next_service_months: 22, last_scanned_at: '2026-02-11T11:05:00+09:00',
    },
    {
      asset_id: 'AS-0003', customer_id: 'CU-0001', product_id: 'LX-0003', product_name: 'Marée Tote',
      category: 'BAG', purchased_at: '2024-03-22T00:00:00+09:00', condition_score: 92,
      findings: [{ part: 'exterior', severity: 'LOW', note: '외관 결 유지' }],
      next_service_months: 30, last_scanned_at: '2026-05-20T16:40:00+09:00',
    },
  ],
  'CU-0003': [
    {
      asset_id: 'AS-0010', customer_id: 'CU-0003', product_id: 'LX-0005', product_name: 'Aurelia Derby',
      category: 'SHOES', purchased_at: '2023-04-18T00:00:00+09:00', condition_score: 81,
      findings: [{ part: 'sole', severity: 'MEDIUM', note: '앞창 마모 진행' }],
      next_service_months: 6, last_scanned_at: '2026-06-05T14:00:00+09:00',
    },
    {
      asset_id: 'AS-0011', customer_id: 'CU-0003', product_id: 'LX-0007', product_name: 'Vesper Ankle Boot',
      category: 'SHOES', purchased_at: '2024-10-02T00:00:00+09:00', condition_score: 90,
      findings: [{ part: 'upper', severity: 'LOW', note: '볼 부분 주름 자연 발생' }],
      next_service_months: 24, last_scanned_at: null,
    },
    {
      asset_id: 'AS-0012', customer_id: 'CU-0003', product_id: 'LX-0011', product_name: 'Lisière Card Holder',
      category: 'WALLET', purchased_at: '2025-01-15T00:00:00+09:00', condition_score: 94,
      findings: [], next_service_months: 33, last_scanned_at: '2026-01-30T12:20:00+09:00',
    },
  ],
  'CU-0004': [
    {
      asset_id: 'AS-0013', customer_id: 'CU-0004', product_id: 'LX-0011', product_name: 'Lisière Card Holder',
      category: 'WALLET', purchased_at: '2023-09-09T00:00:00+09:00', condition_score: 82,
      findings: [{ part: 'edge_coat', severity: 'LOW', note: '엣지 코트 상태 양호' }],
      next_service_months: 12, last_scanned_at: null,
    },
    {
      asset_id: 'AS-0014', customer_id: 'CU-0004', product_id: 'LX-0012', product_name: 'Cadence Belt',
      category: 'BELT', purchased_at: '2024-06-21T00:00:00+09:00', condition_score: 87,
      findings: [{ part: 'exterior', severity: 'LOW', note: '외관 결 유지' }],
      next_service_months: 16, last_scanned_at: '2026-02-24T17:45:00+09:00',
    },
    {
      asset_id: 'AS-0015', customer_id: 'CU-0004', product_id: 'LX-0010', product_name: 'Lisière Long Wallet',
      category: 'WALLET', purchased_at: '2025-08-01T00:00:00+09:00', condition_score: 95,
      findings: [], next_service_months: 36, last_scanned_at: null,
    },
  ],
}

export function mockCustomerAssets(customerId) {
  const customer = MOCK_CUSTOMERS.items.find((c) => c.customer_id === customerId)
  return {
    customer_id: customerId,
    tier: customer?.tier ?? 'NEW',
    assets: MOCK_ASSETS_BY_CUSTOMER[customerId] ?? [],
  }
}

export function mockClassifyIntent() {
  return { hesitation_type: 'NONE', confidence: 0, signals: [] }
}

export function mockClientelingReply() {
  return {
    message: '(오프라인 목업) 서버에 연결할 수 없어 실제 상담을 생성하지 못했어요. 서버가 켜지면 다시 시도해주세요.',
    cited_asset_ids: [],
    cta: 'NONE',
    reasoning: '',
  }
}

// ---- 개체 지문(/identify 화면) 오프라인 목업 ----
// GET /demo/fingerprint-samples 실제 응답 그대로. 오프라인에서는 이미지 url 이
// 로드되지 않으므로 화면이 라벨 타일로 대체해 그린다.

export const MOCK_FINGERPRINT_SAMPLES = {
  total: 1,
  items: [
    {
      asset_id: 'AS-0001',
      product_name: 'Aurelia Top Handle',
      category: 'BAG',
      condition_score: 71,
      next_service_months: 1,
      headline_finding: '핸들 표면 마모 진행, 케어 임계 근접',
      customer_id: 'CU-0001',
      customer_name: '한지원',
      tier: 'VIP',
      images: ['corner_01', 'corner_02', 'handle_01', 'handle_02', 'hardware_01', 'hardware_02', 'stitching_01', 'stitching_02'].map(
        (label) => ({
          path: `data/fingerprints/AS-0001/${label}.jpg`,
          url: `/static/fingerprints/AS-0001/${label}.jpg`,
          label,
        }),
      ),
    },
  ],
}

/** 목 어댑터와 같은 판정 원칙: 경로 규약에 등록 개체 id 가 있으면 매칭, 아니면 미매칭. */
export function mockFingerprintMatch(payload = {}) {
  const found = /AS-\d{4,6}/.exec(payload.image_path ?? '')
  const knownId = found?.[0]
  const registered =
    knownId && MOCK_FINGERPRINT_SAMPLES.items.some((s) => s.asset_id === knownId)
  if (registered) {
    return {
      matched_asset_id: knownId,
      similarity: 0.94,
      is_match: true,
      candidates: [{ asset_id: knownId, similarity: 0.94 }],
      threshold: 0.75,
    }
  }
  return { matched_asset_id: null, similarity: 0.31, is_match: false, candidates: [], threshold: 0.75 }
}

