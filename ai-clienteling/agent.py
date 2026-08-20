"""
콘솔에서 에이전트와 대화하기

실제 응답 생성은 engine.py 가 한다. 이 파일은 대화 기록을 들고 있다가
engine 에 넘겨주고 결과를 화면에 뿌리는 역할만 한다.

  python agent.py           개발용 — 액션 값과 개발 메모까지 보인다
  python agent.py --demo    시연용 — 고객이 실제로 보는 것만 남긴다
"""

import sys

import engine
from engine import MODEL  # 테스트 스크립트가 agent.MODEL 로 모델명을 확인한다

# 시연 모드.
#
# 콘솔은 개발 도구라 액션 값(`[action: care_booking]`)과 개발 메모를 함께 찍는다.
# 값이 맞게 나오는지 보려고 넣은 것이지 고객에게 보일 것은 아니다.
# 실서비스에서 suggested_action 은 글자가 아니라 카드나 버튼으로 바뀌어 나타난다.
#
# 시연에서 콘솔을 띄워야 한다면 이 값을 켜서 개발용 표시를 숨긴다.
DEMO = "--demo" in sys.argv


def dev(line):
    """개발자에게만 보이는 줄. 시연 모드에서는 찍지 않는다."""
    if not DEMO:
        print(line)

# 지금 대화의 상태. 콘솔은 한 번에 한 명과만 이야기하므로 전역으로 둬도 된다.
# (API 서버는 여러 명을 동시에 상대하므로 engine 이 상태를 갖지 않는 것이다)
history = []
customer_id = None
session = {"budget_max": None, "concerns": []}

# 개발 단계 6 — 응대 전략 버전. 콘솔에서 /storytelling 처럼 바꿀 수 있다.
variant = "default"
VARIANTS = ("default", "storytelling", "practical", "control")


def start_conversation(new_customer_id=None, outreach=False):
    """대화를 새로 시작한다. 기록과 누적 조건을 비운다."""
    global history, customer_id, session

    history = []
    customer_id = new_customer_id
    session = {"budget_max": None, "concerns": []}


def ask(message, hesitation_type=None):
    """고객 발화 하나를 보내고 답변 텍스트를 돌려준다."""
    global session

    result = engine.generate_reply(
        message=message,
        customer_id=customer_id,
        conversation_history=history,
        hesitation_type=hesitation_type,
        variant=variant,
    )

    # 대화 기록에 이번 왕복을 남긴다.
    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": result["reply"]})

    # 화면에 보여주기 위한 누적 조건 (engine 이 매번 다시 계산한 것과 같은 값)
    user_texts = [m["content"] for m in history if m["role"] == "user"]
    session = engine.derive_constraints(user_texts)

    ask.last_action = result["suggested_action"]
    return result["reply"]


ask.last_action = "none"


# 아는 것이 없을 때 건네는 첫 마디.
#
# 지어내지 않으면서도 사람의 말이어야 한다.
# 제품도, 접점도, 케어도 꺼내지 않는다. 문을 열어두기만 한다.
GREETING = "안녕하세요, MCM입니다. 무엇을 도와드릴까요?"


def start_outreach(target_customer_id):
    """에이전트가 먼저 말을 건다."""
    global customer_id

    start_conversation(target_customer_id)

    result = engine.generate_outreach(target_customer_id)
    history.append({"role": "assistant", "content": result["reply"]})

    start_outreach.last_action = result["suggested_action"]
    return result["reply"]


start_outreach.last_action = "none"


def main():
    if DEMO:
        print("=" * 60)
        print("  MCM 퍼스널 어드바이저")
        print("=" * 60)
        # 시연자에게 주는 안내. 대화가 시작되기 전이므로 화면에 남아도 괜찮다.
        # 처음에는 이 줄까지 지웠더니 무엇을 입력해야 하는지 알 수 없었다.
        print("  [시연 준비]  고객 ID 를 입력하세요.  C001 ~ C010")
    else:
        print("=" * 60)
        print("  MCM 퍼스널 어드바이저 (콘솔 테스트)")
        print("=" * 60)
        print("  고객 ID를 넣으면 그 고객으로 대화합니다 (C001 ~ C010)")
        print("  그냥 Enter 를 누르면 고객 정보 없이 시작합니다")
        print("  대화 중 /fit /price /timing /comparison 으로 망설임 유형 지정")
        print("  /storytelling /practical /control 로 응대 전략 변경 (기본 default)")
        print("  종료하려면 'quit' 또는 '종료' 입력")
        print("  시연용으로 띄우려면  python agent.py --demo")
        print("=" * 60)

    # 실제 서비스에서는 사건(착장 기록 생성, 케어 시점 도래)이 발생하면
    # 시스템이 알아서 첫 메시지를 보낸다. 고객에게 물어보지 않는다.
    # 콘솔의 ID 입력은 그 사건을 사람이 대신 일으키는 개발용 장치다.
    raw = input("\n고객 ID > ").strip()

    # 시연에서는 준비 단계와 대화를 눈으로 구분해 준다.
    # 아래부터가 고객이 보는 화면이다.
    if DEMO:
        print("\n" + "─" * 60)

    # 개발용 옵션: 뒤에 '-' 를 붙이면(C006-) 먼저 말 걸기를 건너뛴다.
    skip_outreach = raw.endswith("-")
    target = raw.rstrip("-").strip().upper()

    if target:
        if skip_outreach:
            start_conversation(target)
            print(f"\n[{target} · 먼저 말 걸기 생략]")
        else:
            try:
                reply = start_outreach(target)
                print(f"\n어드바이저 > {reply}")
                dev(f"   [action: {start_outreach.last_action}]")
            except ValueError:
                # 말을 걸 계기가 없다. 그렇다고 화면에 내부 사정을 늘어놓지 않는다.
                #
                # 처음에는 "recent_activity 가 없습니다" 를 그대로 찍었는데,
                # 부티크에서 손님에게 레코드 상태를 설명하는 꼴이었다.
                # 계기가 없다는 것은 **먼저 꺼낼 이야기가 없다**는 뜻이지
                # 인사도 못 한다는 뜻이 아니다. 인사는 지어내는 것이 아니다.
                #
                # 개발용 설명은 개발자에게만, 대화는 사람의 말로.
                start_conversation(target)
                dev(f"\n[개발 메모] {target} 은 더미 데이터에 없는 고객입니다. "
                    "먼저 건넬 이야기가 없어 인사만 합니다.")
                print(f"\n어드바이저 > {GREETING}")
                history.append({"role": "assistant", "content": GREETING})
    else:
        start_conversation()
        dev("\n[고객 정보 없이 시작합니다]")

    # 실제 서비스에서는 AI 1이 매 발화마다 분류해서 넘겨준다.
    hesitation = None

    while True:
        # 시연에서는 망설임 유형 표시를 숨긴다. AI 1 이 넘겨주는 내부 값이다.
        label = f" [{hesitation}]" if hesitation and not DEMO else ""
        message = input(f"\n고객{label} > ").strip()

        if not message:
            continue

        if message.lower() in ("quit", "exit", "종료"):
            print("\n대화를 종료합니다.")
            break

        # /fit, /price, /timing, /comparison 으로 망설임 유형을 바꾼다.
        if message.startswith("/"):
            global variant
            value = message[1:].strip().lower()
            if value in ("fit", "price", "timing", "comparison"):
                hesitation = value
                dev(f"[망설임 유형: {value}]")
            elif value in ("none", "off"):
                hesitation = None
                dev("[망설임 유형 해제]")
            elif value in VARIANTS:
                variant = value
                dev(f"[응대 전략: {value}]")
            else:
                dev("[망설임] /fit  /price  /timing  /comparison  /none")
                dev(f"[전략]   {'  '.join('/' + v for v in VARIANTS)}")
            continue

        try:
            reply = ask(message, hesitation)
            print(f"\n어드바이저 > {reply}")
            dev(f"   [action: {ask.last_action}]")
        except Exception as e:
            # 시연 중이라면 오류 원문을 손님 앞에 띄우지 않는다.
            if DEMO:
                print("\n어드바이저 > 잠시 연결이 고르지 않네요. 한 번만 다시 말씀해 주시겠어요?")
            else:
                print(f"\n[에러] 응답을 받지 못했습니다: {e}")


if __name__ == "__main__":
    main()
