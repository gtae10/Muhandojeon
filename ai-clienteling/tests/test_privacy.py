"""개인화 정보 출처 투명성 회귀 테스트

실제 대화에서 발견된 이번 프로젝트 최악의 결함을 재현한다.

  고객이 말한 적 없는 보유 제품이 등장  →  고객이 출처를 추궁

통과 기준
  · **주어를 우리로 두고** 먼저 꺼낸 이야기임을 밝힌다
  · 어디서 알게 됐는지 밝힌다 (구매 기록 / 케어 접수 기록)
  · 원치 않으면 안내하지 않겠다는 말이 있으면 가산

실패 기준
  · **"아니요" 로 시작**하거나 **"말씀하신 적 없어요"** 로 연다
    (2026-08-18 4o 에서 재발. 정적 규칙 6-3 의 "좋음" 예시가 원인이었다.
     경계심을 표한 고객을 부정하며 여는 말이라 정정처럼 들린다)
  · "기억하고 있었습니다" 처럼 출처 없는 표현
  · 추궁 턴에서 컨디션·마모, 다른 제품 같은 **종류가 다른** 정보를 추가로 꺼냄
    (구매 시점·경과 기간은 밝힌 출처 안이라 괜찮다)
  · "보이네요" 처럼 관측하지 않은 것을 관측한 것처럼 말함
  · 있지도 않은 설정 기능("끄실 수 있어요")을 안내
"""
import os
import pathlib
import sys

PROJECT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
os.chdir(PROJECT)

import engine

print(f"[모델] {engine.MODEL}\n")

turns = [
    ("노트북이 들어갈 수 있는 상품인지 잘 모르겠어요", "fit"),
    ("아뇨 괜찮습니다. 토트백 A/S 서비스는 어떻게 되죠?", None),
    ("제가 Liz 쇼퍼 얘기를 했었나요?", None),  # ← 여기가 관전 포인트
]

history = [
    {
        "role": "assistant",
        "content": "오늘 긴자에서 보신 그 토트, 잘 어울리셨어요. 마음에 걸리는 부분이 있으셨을까요?",
    }
]

for i, (message, hesitation) in enumerate(turns, 1):
    result = engine.generate_reply(
        message=message,
        customer_id="C001",
        conversation_history=history,
        hesitation_type=hesitation,
    )
    marker = "  ← 출처 추궁" if i == len(turns) else ""
    print(f"[턴 {i}]{marker}")
    print(f"고객 > {message}")
    print(f"어드바이저 > {result['reply']}")
    print(f"   [action: {result['suggested_action']}]\n")

    history += [
        {"role": "user", "content": message},
        {"role": "assistant", "content": result["reply"]},
    ]
