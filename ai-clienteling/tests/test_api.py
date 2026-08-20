"""API 서버 동작 확인

먼저 다른 터미널에서 서버를 띄운 뒤 실행한다.

  uvicorn api:app --reload --port 8102
  python tests/test_api.py
"""

import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8102"


def call(path, payload=None):
    url = BASE + path
    if payload is None:
        request = urllib.request.Request(url)
    else:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def show(title, result):
    print("=" * 74)
    print(f"[{title}]")
    print(f"reply  : {result['reply']}")
    print(f"action : {result.get('suggested_action')}")
    print()


try:
    print(f"서버 상태: {call('/health')}\n")
except urllib.error.URLError:
    print("서버에 연결하지 못했습니다. 먼저 uvicorn api:app --port 8102 를 실행하세요.")
    raise SystemExit(1)

# 1) 팀 합의 스펙 그대로의 요청
show(
    "chat · C001 · fit · 이력 있음",
    call(
        "/chat",
        {
            "customer_id": "C001",
            "message": "노트북이 들어갈지 모르겠어요",
            "conversation_history": [
                {
                    "role": "assistant",
                    "content": "오늘 보신 그 토트, 잘 어울리셨어요. 마음에 걸리는 부분이 있으셨을까요?",
                }
            ],
            "hesitation_type": "fit",
        },
    ),
)

# 2) 먼저 말 걸기 — care_booking 이 나와야 한다
show("outreach · C006 · 케어 시점", call("/outreach", {"customer_id": "C006"}))

# 3) 고객 정보 없이, 예산 조건만 — 조건 충돌을 밝혀야 한다
show(
    "chat · 고객정보 없음 · 예산 조건",
    call("/chat", {"message": "140만원 아래 미디엄 백팩 찾고 있어요"}),
)

# 4) Backend 가 owned_products 를 직접 넘기는 경우
show(
    "chat · owned_products 를 요청으로 전달",
    call(
        "/chat",
        {
            "customer_id": "C999",
            "message": "3년쯤 썼는데 핸들이 좀 상했어요",
            "owned_products": [
                {
                    "product_id": "P003",
                    "name": "Liz 비세토스 리버서블 쇼퍼",
                    "purchased": "2023-05",
                    "condition": {"overall": "fair", "notes": "가죽 핸들 마모 진행"},
                }
            ],
        },
    ),
)
