"""
AI1(고객분석/Intent) 담당 모듈과의 연동 지점.

실제 구현 전까지는 더미 로직으로 응답해 프론트/백엔드 통합 테스트가 가능하도록 함.
AI1 담당자는 analyze_texture 함수 내부만 실제 모델 호출로 교체하면 됨.
"""


def analyze_texture(product_id: str, image_bytes: bytes) -> dict:
    # TODO(AI1): 실제 텍스처 지문 대조 + 마모도 스코어링 로직으로 교체
    return {
        "conditionScore": 71,
        "wearPoints": [{"part": "핸들", "severity": "임계 근접"}],
    }
