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
    { customer_id: 'CU-0001', display_name: '한지원', tier: 'VIP', asset_count: 5, care_due: 1, min_condition: 71 },
    { customer_id: 'CU-0002', display_name: '오세린', tier: 'VIP', asset_count: 4, care_due: 0, min_condition: 78 },
    { customer_id: 'CU-0003', display_name: '박도현', tier: 'ESTABLISHED', asset_count: 3, care_due: 0, min_condition: 81 },
    { customer_id: 'CU-0004', display_name: '윤소이', tier: 'ESTABLISHED', asset_count: 2, care_due: 0, min_condition: 85 },
    { customer_id: 'CU-0005', display_name: '정하늘', tier: 'NEW', asset_count: 1, care_due: 0, min_condition: 90 },
    { customer_id: 'CU-0006', display_name: '강민준', tier: 'NEW', asset_count: 0, care_due: 0, min_condition: null },
  ],
}

export const MOCK_CATALOG = {
  total: 4,
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
      product_id: 'LX-0006', name: 'Aurelia Derby', category: 'SHOES',
      material: '박스카프 / 가죽 밑창', color: 'Noir', collection: 'Maison Nord',
      price_krw: 2100000, image_url: null,
    },
    {
      product_id: 'LX-0010', name: 'Lisière Card Holder', category: 'SLG',
      material: '에피 카프스킨', color: 'Cognac', collection: 'Maison Nord',
      price_krw: 890000, image_url: null,
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
        '사이즈표를 세 번 열고 38.5와 39를 왕복한 뒤 이탈한 고객(CU-0003). 같은 라스트 신발(AS-0010)을 이미 갖고 있어 "그때 맞춰 드린 치수"를 근거로 쓴다.',
      customer_id: 'CU-0003',
      target_product_id: 'LX-0006',
    },
    {
      id: 'D2',
      title: '가격 망설임 — 보유 자산의 수명으로 답한다',
      narrative:
        '가격 상한을 낮추고 저가 대안을 조회한 뒤 장바구니에서 뺀 고객(CU-0004). 할인 대신 "N년 쓴 개체가 아직 몇 점"이라는 실제 컨디션 기록으로 답한다.',
      customer_id: 'CU-0004',
      target_product_id: 'LX-0001',
    },
    {
      id: 'D3',
      title: '재고 확인 — 케어 시점이 임박한 VIP',
      narrative:
        '재고와 배송을 확인한 장기 VIP(CU-0001). 컨디션 71점(핸들 마모 임계 근접) 개체가 있어 재고 안내와 케어 예약을 함께 제안한다.',
      customer_id: 'CU-0001',
      target_product_id: 'LX-0002',
    },
  ],
}

const MOCK_ADVISE_BY_SCENARIO = {
  D1: {
    hesitation_type: 'SIZE_UNCERTAIN',
    confidence: 0.95,
    signals: [{ evidence: '사이즈표 3회 열람, 38.5·39 왕복 조회' }],
    message:
      '2022년에 맞춰드린 Aurelia Derby(AS-0010)와 같은 라스트라, 그때 사이즈 39가 잘 맞으셨던 기록이 남아있어요. 지금 컨디션도 81점으로 관리가 잘 되어 있으니 이번에도 같은 사이즈로 편하게 진행하셔도 좋을 것 같아요.',
    cta: 'BOOK_FITTING',
    citations: [
      {
        asset_id: 'AS-0010', product_name: 'Aurelia Derby', condition_score: 81,
        headline_finding: '전반적으로 양호, 밑창 교체 이력 없음', next_service_months: 8,
      },
    ],
    owned_assets_used: true,
    no_assets: false,
    degraded: false,
  },
  D2: {
    hesitation_type: 'PRICE_HESITANT',
    confidence: 0.95,
    signals: [{ evidence: '가격 필터 하향 조정, 저가 대안 2회 조회 후 장바구니 이탈' }],
    message:
      '2023년에 함께하신 Lisière Card Holder는 2년 사용에 컨디션 82점으로 잘 관리되고 있습니다(엣지 코트 상태 양호). Lisière 라인 특유의 내구성을 이미 직접 경험하고 계신 만큼, 이번 Aurelia Top Handle도 비슷한 관리로 오래 곁에 두실 수 있을 거예요.',
    cta: 'BOOK_FITTING',
    citations: [
      {
        asset_id: 'AS-0013', product_name: 'Lisière Card Holder', condition_score: 82,
        headline_finding: '엣지 코트 상태 양호', next_service_months: 6,
      },
    ],
    owned_assets_used: true,
    no_assets: false,
    degraded: false,
  },
  D3: {
    hesitation_type: 'STOCK_CONCERN',
    confidence: 0.9,
    signals: [{ evidence: '재고 조회 2회, 배송 조회 1회' }],
    message:
      '지금 보시는 Solène Shoulder 25 사이즈는 재고가 있어 바로 안내드릴 수 있어요. 다만 8년째 함께하신 개체(AS-0001)의 핸들 마모가 임계에 가까워, 이번 방문에 케어 예약도 같이 잡아드리면 어떨까 해요.',
    cta: 'VIEW_STOCK',
    citations: [
      {
        asset_id: 'AS-0001', product_name: 'Aurelia Top Handle', condition_score: 71,
        headline_finding: '핸들 마모 임계 근접', next_service_months: 0,
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
