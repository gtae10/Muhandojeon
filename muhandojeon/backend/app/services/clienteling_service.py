"""
AI2(Clienteling/LLM) 담당 모듈과의 연동 지점.

실제 구현 전까지는 더미 응답으로 프론트/백엔드 통합 테스트가 가능하도록 함.
AI2 담당자는 generate_reply 함수 내부만 실제 LLM/RAG 호출로 교체하면 됨.
"""


def generate_reply(product_id: str, message: str) -> str:
    # TODO(AI2): 실제 RAG + LLM 호출로 교체 (제품 데이터, 헤리티지 스토리, 옴니채널 재고 컨텍스트 주입)
    return (
        f"'{message}'에 대해 확인해볼게요. "
        "(AI2 상담 로직 연동 전 임시 응답입니다)"
    )
