"""경계값 회귀 테스트 — 숫자 비교가 정확한가

백팩 가격:  Aren 노바 1,450,000  /  Stark 1,890,000

기대 결과
  140만 이하 → 없음. 가장 가까운 것이 Aren 노바 145만원, 5만원 초과라고 밝혀야 함
  145만 이하 → Aren 노바 하나 (정확히 경계에 걸림)
  150만 이하 → Aren 노바 하나
  200만 이하 → Aren 노바, Stark 둘 다
"""
import os
import sys
import pathlib

# 이 파일(tests/xxx.py)의 부모의 부모 = 프로젝트 루트
PROJECT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
os.chdir(PROJECT)

import agent

print(f"[모델] {agent.MODEL}\n")

questions = [
    ("140만 이하", "140만원 아래 정도 되는 미디엄 사이즈의 백팩을 찾고 있어요"),
    ("145만 이하", "145만원 이하로 미디엄 백팩 있을까요?"),
    ("150만 이하", "150만원 이하 미디엄 백팩 추천해주세요"),
    ("200만 이하", "200만원 이하 백팩은 어떤 게 있나요?"),
]

for label, q in questions:
    agent.start_conversation()  # 고객 정보 없이 (탐색 단계 신규 방문자)
    print("=" * 74)
    print(f"[{label}]")
    print(f"고객 > {q}")
    print(f"어드바이저 > {agent.ask(q)}\n")
