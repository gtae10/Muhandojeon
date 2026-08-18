"""데모 리허설 — 발표에서 보여줄 대화를 그대로 이어서 돌린다.

낱개 턴 테스트와 다른 점: 대화 기록을 계속 넘긴다.
회귀 테스트는 규칙 하나씩을 보지만, 여기서는 앞뒤가 맞는지를 본다.

  실행:  python tests/test_rehearsal.py
"""
import os
import pathlib
import sys

PROJECT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
os.chdir(PROJECT)

import engine


def run(title, customer_id, turns, watch):
    print("=" * 78)
    print(f" {title}")
    print(f" 볼 것: {watch}")
    print("=" * 78)

    opening = engine.generate_outreach(customer_id)
    print(f"\n어드바이저 ▸ {opening['reply']}")
    print(f"            [action: {opening['suggested_action']}]")

    history = [{"role": "assistant", "content": opening["reply"]}]

    for message, hesitation in turns:
        print(f"\n고객       ▸ {message}")
        result = engine.generate_reply(
            message=message,
            customer_id=customer_id,
            conversation_history=history,
            hesitation_type=hesitation,
        )
        print(f"어드바이저 ▸ {result['reply']}")
        print(f"            [action: {result['suggested_action']}]")
        history += [
            {"role": "user", "content": message},
            {"role": "assistant", "content": result["reply"]},
        ]

    print()


print(f"[모델] {engine.MODEL}\n")

run(
    "① C001 히어로 — 도쿄 출장, 긴자 착장 후 미구매",
    "C001",
    [
        ("노트북도 들어갈까요? 매일 들고 다녀야 해서요.", "fit"),
        # "무겁진 않을까요?" 는 대본에서 뺐다.
        # 무게는 우리 제품 데이터에 없어서 "확인이 필요하다"로 답할 수밖에 없고,
        # 같은 fit 유형이 연속으로 오면 앞 턴 답을 반복하는 문제도 있었다.
        # 노트북 수납만으로 fit 망설임은 충분히 보여진다.
        ("지금 사기엔 짐이 많아서요. 모레 귀국이라.", "timing"),
        ("아뇨 괜찮습니다. 토트백 A/S 서비스는 어떻게 되죠?", None),
        ("제가 Liz 쇼퍼 얘기를 했었나요?", None),
    ],
    "오프닝→망설임 해소→케어 다리→출처 추궁까지 한 흐름으로 이어지는가",
)

run(
    "② C006 케어 — 3년 전 케어 이력이 있는 고객",
    "C006",
    [
        ("네, 한번 봐주세요.", None),
        ("얼마나 걸려요?", None),
        ("보증서를 잃어버렸는데 괜찮을까요?", None),
    ],
    "지난 케어를 관계로 꺼내는가 / 기간을 약속하지 않는가 / 보증서 없어도 된다고 하는가",
)

run(
    "③ C010 케어 — 7년 된 제품, 교체를 먼저 묻는 고객",
    "C010",
    [
        ("7년 썼으면 바꿀 때 되지 않았나요? 그냥 새로 살까요?", None),
        ("매장에서는 이건 수선이 어렵다던데요.", None),
        ("Pina요.", None),
    ],
    "교체보다 케어를 먼저 짚는가 / 제품을 짐작하지 않고 되묻는가 / 되물은 뒤 이어가는가",
)

run(
    # 2026-08-18 설계 변경: 프로필 지역은 근거(매장 접점)가 없으면 쓰지 않는다.
    # C007 은 온라인 접점뿐이라, 부산은 고객이 말한 뒤에야 나와야 한다.
    # 종전 "볼 것"("부산 매장 이름을 대는가")은 이 결정으로 낡아서 바꿨다.
    "④ C007 지역 대비 — 근거 없으면 여쭙고, 말한 지역은 이름을, 모르는 지역은 확인을",
    "C007",
    [
        ("수선 접수하고 싶은데 어디로 가면 되나요?", None),
        ("부산이요", None),
        ("제주 갈 일이 있는데 거기서도 되나요?", None),
    ],
    "첫 턴에 부산을 먼저 꺼내지 않고 어느 지역이 편하신지 여쭙는가 /"
    " '부산이요' 다음 턴부터 롯데백화점 부산본점 이름을 대는가 /"
    " 제주는 지어내지도 없다고도 하지 않는가",
)
