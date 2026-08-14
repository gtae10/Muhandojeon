"""LLM 게이트웨이 — 모든 모델 호출이 지나는 단일 경로.

    from app.llm import get_llm, Message           # 호출
    from app.llm import get_budget, usage_summary   # 예산
    from app.llm import resolve, supports_vision    # 라우팅·능력 플래그

패키지로 나눈 이유: 클라이언트(호출)·예산(게이트)·라우팅(정책)·단가(계산)를 분리해야
크레딧 100달러라는 제약을 코드에서 검증할 수 있기 때문이다. 외부 import 경로는
`app.llm` 하나로 유지해 기존 호출부를 건드리지 않는다.
"""

from app.llm.budget import BudgetExceeded, BudgetGuard, BudgetState, get_budget, usage_summary
from app.llm.client import LLMClient, LLMStats, Message, extract_json, get_llm
from app.llm.pricing import (
    Price,
    estimate_call_cost,
    estimate_prompt_tokens,
    estimate_tokens,
    price_for,
)
from app.llm.routing import (
    PURPOSES,
    Purpose,
    Route,
    load_capabilities,
    resolve,
    routing_report,
    supports_vision,
)

__all__ = [
    "PURPOSES",
    "BudgetExceeded",
    "BudgetGuard",
    "BudgetState",
    "LLMClient",
    "LLMStats",
    "Message",
    "Price",
    "Purpose",
    "Route",
    "estimate_call_cost",
    "estimate_prompt_tokens",
    "estimate_tokens",
    "extract_json",
    "get_budget",
    "get_llm",
    "load_capabilities",
    "price_for",
    "resolve",
    "routing_report",
    "supports_vision",
    "usage_summary",
]
