"""4단계 검증: 망설임 유형별 분기 + 잔여 과제 4개"""
import os
import sys
import pathlib

# 이 파일(tests/xxx.py)의 부모의 부모 = 프로젝트 루트
PROJECT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
os.chdir(PROJECT)

import agent

print(f"[모델] {agent.MODEL}\n")

cases = [
    (
        "C002", "fit",
        "노트북 보호가 중요 → Stark(13인치 슬리브) 대안을 제시하는가",
        "16인치 노트북을 매일 들고 다니는데, 이 토트에 넣어도 괜찮을까요?",
    ),
    (
        "C003", "price",
        "가격을 변호하지 않고 헤리티지로 답하는가 / 할인 언급 없는가",
        "예쁘긴 한데 185만원이면 좀 비싼 것 같아서요.",
    ),
    (
        "C004", "timing",
        "재촉하지 않는가 / 재고 홀드를 단정하지 않는가",
        "내일 귀국인데 원하는 색이 없대요. 지금 다른 걸로 사야 할까요?",
    ),
    (
        "C005", "comparison",
        "타 브랜드 언급 없는가 / 비교 중인 걸 아는 티를 안 내는가 / 비세토스·모빌리티가 나오는가",
        "다른 브랜드 백팩이랑 계속 고민 중이에요. MCM은 뭐가 다른가요?",
    ),
    (
        "C006", None,
        "케어 답변이 짧아졌는가 / 고객센터로 떠넘기지 않는가",
        "핸들이 갈라졌는데 수선이 될까요?",
    ),
]

for customer_id, hesitation, label, question in cases:
    agent.start_conversation(customer_id)
    print("=" * 74)
    print(f"[{customer_id} · {hesitation or '분류없음'}] {label}")
    print(f"고객 > {question}")
    print(f"어드바이저 > {agent.ask(question, hesitation)}\n")
