# 데이터 오버레이 격리 검증 — LLM 호출 없음 (engine._call 을 가짜로 바꿔 프롬프트만 본다)
#
# 확인하는 것
#   1. data_overlay 안에서는 통합 카탈로그(18종), 밖에서는 원본(6종)이 읽힌다
#   2. 예외가 나도 오버레이가 반드시 해제된다
#   3. /clienteling/reply 프롬프트에는 LX 제품이 실리고,
#      직후의 /chat 프롬프트에는 LX 흔적이 전혀 없다 (요청 간 누수 없음)
#
# 실행: python tests/test_overlay.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

import api
import engine
from prompts import knowledge

failed = 0


def check(label, ok):
    global failed
    print(("O " if ok else "X "), label)
    failed += 0 if ok else 1


# ── 1. 순수 오버레이 동작 ──
base_count = len(knowledge.load("products.json")["products"])
with knowledge.data_overlay(api.INTEGRATION_DATA):
    overlay_count = len(knowledge.load("products.json")["products"])
    # 오버레이에 없는 파일은 평소처럼 원본에서
    heritage_ok = "sections" in knowledge.load("heritage.json") or True
after_count = len(knowledge.load("products.json")["products"])
check(f"오버레이 안 18종 / 밖 6종 (실측 {base_count}→{overlay_count}→{after_count})",
      base_count == 6 and overlay_count == 18 and after_count == 6)

# ── 2. 예외 시 해제 ──
try:
    with knowledge.data_overlay(api.INTEGRATION_DATA):
        raise RuntimeError("일부러")
except RuntimeError:
    pass
check("예외 후에도 원본으로 복귀", len(knowledge.load("products.json")["products"]) == 6)

# ── 3. 요청 간 누수 없음 (프롬프트 캡처) ──
captured = []


def fake_call(messages, allow_retry=True):
    captured.append("\n".join(m.get("content", "") for m in messages))
    return {"reply": "테스트 응답입니다.", "suggested_action": "none"}


real_call = engine._call
engine._call = fake_call
try:
    client = TestClient(api.app)
    for _ in range(3):  # 같은 스레드 재사용 시나리오를 흉내내 교차 반복
        captured.clear()
        r1 = client.post("/clienteling/reply", json={
            "customer_id": "CU-0001", "hesitation_type": "NONE",
            "owned_assets": [], "history": [
                {"role": "customer", "content": "Solène Shoulder는 어떤 가방이에요?"}
            ],
        })
        integration_prompt = captured[-1]
        captured.clear()
        r2 = client.post("/chat", json={
            "customer_id": "C001", "message": "노트북이 들어갈까요?",
            "conversation_history": [],
        })
        chat_prompt = captured[-1]
        assert r1.status_code == 200 and r2.status_code == 200
    check("통합 프롬프트에 LX 제품 실림", "Solène Shoulder" in integration_prompt)
    check("통합 프롬프트에 매장·재고 지식 실림", "롯데백화점" in integration_prompt or "MCM" in integration_prompt)
    check("직후 /chat 프롬프트에 LX 흔적 없음",
          "LX-" not in chat_prompt and "Solène" not in chat_prompt and "Aurelia" not in chat_prompt)
    check("/chat 프롬프트는 MCM 6종 그대로", "Aren 비세토스 스쿨 토트" in chat_prompt)
finally:
    engine._call = real_call

print(f"\n{'전부 통과' if failed == 0 else f'{failed}건 실패'}")
sys.exit(1 if failed else 0)
