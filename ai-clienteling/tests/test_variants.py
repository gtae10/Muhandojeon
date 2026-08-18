"""6단계 검증 — 응대 전략 변형 비교 (Persona Bot Lab 실험용)

같은 질문을 네 가지 버전에 던져서 답이 어떻게 갈리는지 본다.

  default       지금까지 튜닝한 균형형
  storytelling  헤리티지·서사 중심
  practical     수치·실행 중심
  control       대조군 — 우리 설계를 뺀 일반 상담 챗봇

대조군에서 무엇이 무너지는지가 이 실험의 핵심이다.
케어 우선 원칙, 감시감 없는 개인화, 할인 화법 금지가 실제로 우리 설계 덕분인지 확인한다.
"""
import os
import pathlib
import sys

# 이 파일(tests/xxx.py)의 부모의 부모 = 프로젝트 루트
PROJECT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
os.chdir(PROJECT)

import engine

VARIANTS = ["default", "storytelling", "practical", "control"]

print(f"[모델] {engine.MODEL}\n")

scenarios = [
    {
        "label": "케어 우선 최대 시험 — 5년 쓴 제품, 고객이 먼저 교체를 꺼냄",
        "customer_id": "C006",
        "message": "5년 썼으면 바꿀 때 되지 않았나요? 그냥 새로 살까요?",
        "hesitation_type": None,
        "watch": "대조군이 신제품을 권하는가 / 나머지가 수선을 먼저 짚는가",
    },
    {
        "label": "가격 부담",
        "customer_id": "C003",
        "message": "이 가격이면 좀 부담스러운데요",
        "hesitation_type": "price",
        "watch": "대조군이 할인·세일을 언급하는가 / 서사와 정보의 비중 차이",
    },
    {
        "label": "먼저 말 걸기 — 케어 시점",
        "customer_id": "C006",
        "message": None,  # outreach
        "hesitation_type": None,
        "watch": "대조군이 마모를 지적하거나 제품을 권하는가",
    },
]

# 인자를 주면 그 시나리오만 본다.  예: python tests/test_variants.py 1
only = int(sys.argv[1]) if len(sys.argv) > 1 else None

for i, s in enumerate(scenarios, 1):
    if only and i != only:
        continue

    print("=" * 78)
    print(f"[시나리오 {i}] {s['label']}")
    print(f"  볼 것: {s['watch']}")
    if s["message"]:
        print(f"  고객 > {s['message']}")
    else:
        print("  (고객 발화 없음 — 에이전트가 먼저 말을 거는 상황)")
    print("=" * 78)

    for variant in VARIANTS:
        if s["message"]:
            result = engine.generate_reply(
                message=s["message"],
                customer_id=s["customer_id"],
                hesitation_type=s["hesitation_type"],
                variant=variant,
            )
        else:
            result = engine.generate_outreach(s["customer_id"], variant=variant)

        print(f"\n── {variant} ──")
        print(result["reply"])
        print(f"   [action: {result['suggested_action']}]")

    print()
