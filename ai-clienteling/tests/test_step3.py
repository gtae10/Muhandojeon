"""3단계 검증: 보유 제품·컨디션이 답변에 반영되는가"""
import os
import sys
import pathlib

# 이 파일(tests/xxx.py)의 부모의 부모 = 프로젝트 루트
PROJECT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
os.chdir(PROJECT)

import agent

print(f"[모델] {agent.MODEL}\n")

scenarios = [
    (
        "C001",
        "히어로 — 보유 백 케어로 자연스럽게 연결되는가",
        "아까 긴자에서 본 그 토트가 계속 생각나긴 하는데, 노트북이 들어갈지 모르겠어요.",
    ),
    (
        "C006",
        "케어 우선 최대 시험대 — 같은 모델 보유 + needs_care 상태에서 교체를 권하는가",
        "Pina 토트를 하나 더 살까 고민 중이에요.",
    ),
    (
        "C002",
        "보유 이력 없음 — 개인화할 게 없을 때 억지로 지어내는가",
        "16인치 노트북 쓰는데 Aren 토트에 들어갈까요?",
    ),
]

# 인자를 주면 그 고객만 테스트한다.  예: python test_step3.py C001
if len(sys.argv) > 1:
    only = [a.upper() for a in sys.argv[1:]]
    scenarios = [s for s in scenarios if s[0] in only]

for customer_id, label, question in scenarios:
    agent.start_conversation(customer_id)  # 고객마다 대화를 새로 시작
    print("=" * 70)
    print(f"[{customer_id}] {label}")
    print(f"고객 > {question}")
    print(f"어드바이저 > {agent.ask(question)}\n")
