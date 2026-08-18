"""다중 턴 조건 누적 회귀 테스트

실제 대화에서 발견된 결함 시퀀스를 그대로 재현한다.

통과 기준
  턴3  예산 밖(185만원 Pina)을 아무 언급 없이 권하면 실패.
       Large 카테고리에 예산 내 제품이 없다는 충돌을 밝히면 통과.
  턴4  거절당한 Aren 으로 무언급 회귀하면 실패.
       "처음에 가격이 걸린다고 하셨죠" 처럼 이전 발언을 언급하면 통과.
  전체 "저렴한" 사용, 빈 마무리("추가로 궁금한 점이 있으신가요") 나오면 실패.
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

agent.start_conversation()

turns = [
    "Aren 스쿨 토트 보고 있는데 가격이 너무 비싼 거 같아서요",
    "스쿨 토트처럼 큰 가방을 찾고 있습니다",
    "1,850,000원은 너무 비싼 것 같습니다.",
    "이 스쿨 토트 노트북 같은 전자기기를 넣는 데에도 적합할까요?",
]

for i, q in enumerate(turns, 1):
    print("=" * 74)
    print(f"[턴 {i}]")
    print(f"고객 > {q}")
    print(f"어드바이저 > {agent.ask(q)}")
    print(f"   (누적 조건: {agent.session})\n")
