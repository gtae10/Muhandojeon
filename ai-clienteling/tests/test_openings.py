"""전 고객 오프닝 일괄 출력 — 회귀 테스트용

프롬프트를 고칠 때마다 이걸 돌려서 오프닝이 망가지지 않았는지 훑어본다.

점검 항목
  · 마모·컨디션을 첫 마디에 꺼내지 않는가
  · 추적한 티가 나지 않는가 ("조회하신", "여러 번 보셨던")
  · 두세 문장인가
  · 카탈로그 문구가 아닌가
  · C006 이 '3년 전'을 정확히 계산하는가 (2023-08 → 2026-08)
"""
import os
import sys
import pathlib

# 이 파일(tests/xxx.py)의 부모의 부모 = 프로젝트 루트
PROJECT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
os.chdir(PROJECT)

import agent
from prompts.knowledge import load

customers = load("customers.json")["customers"]

# 인자를 주면 그 고객만 본다.  예: python test_openings.py C002 C005
if len(sys.argv) > 1:
    only = [a.upper() for a in sys.argv[1:]]
    customers = [c for c in customers if c["customer_id"] in only]

print(f"[모델] {agent.MODEL}")
print(f"[고객] {len(customers)}명\n")

for customer in customers:
    cid = customer["customer_id"]
    activity = customer.get("recent_activity", {})
    has_care = any(
        p.get("care_history") for p in customer.get("owned_products", [])
    )

    print("=" * 76)
    print(f"[{cid}] {customer.get('current_location', '?')} · {activity.get('type', '접점 없음')}")
    print(f"       보유 {len(customer.get('owned_products', []))}점 · 케어이력 {'있음' if has_care else '없음'}")
    print("-" * 76)
    print(agent.start_outreach(cid))
    print()
