"""팀 전체가 공유하는 API 계약 (Pydantic v2).

이 패키지가 **인터페이스 단일 출처**다. 사람이 읽는 문서는 `docs/CONTRACTS.md`,
예시 페이로드는 `contracts/examples/*.json` 이며 둘 다 여기서 생성된다.

    from contracts import IntentClassifyRequest, AdviseResponse
"""

from contracts.assets import CustomerAssetsResponse
from contracts.clienteling import ClientelingReplyRequest, ClientelingReplyResponse
from contracts.common import (
    CTA,
    AssetPart,
    ChatTurn,
    CustomerTier,
    EventType,
    Finding,
    HesitationType,
    OwnedAsset,
    Product,
    ProductCategory,
    Role,
    SessionEvent,
    Severity,
)
from contracts.condition import ConditionScoreRequest, ConditionScoreResponse
from contracts.fingerprint import (
    FingerprintCandidate,
    FingerprintMatchRequest,
    FingerprintMatchResponse,
)
from contracts.intent import IntentClassifyRequest, IntentClassifyResponse, IntentSignal
from contracts.orchestrator import (
    AdviseRequest,
    AdviseResponse,
    AdviseTraceStep,
    AssetCitation,
    OwnedAssetRanked,
)
from contracts.registry import ENDPOINTS, EndpointSpec

__all__ = [
    "CTA",
    "ENDPOINTS",
    "AdviseRequest",
    "AdviseResponse",
    "AdviseTraceStep",
    "AssetCitation",
    "AssetPart",
    "ChatTurn",
    "ClientelingReplyRequest",
    "ClientelingReplyResponse",
    "ConditionScoreRequest",
    "ConditionScoreResponse",
    "CustomerAssetsResponse",
    "CustomerTier",
    "EndpointSpec",
    "EventType",
    "Finding",
    "FingerprintCandidate",
    "FingerprintMatchRequest",
    "FingerprintMatchResponse",
    "HesitationType",
    "IntentClassifyRequest",
    "IntentClassifyResponse",
    "IntentSignal",
    "OwnedAsset",
    "OwnedAssetRanked",
    "Product",
    "ProductCategory",
    "Role",
    "SessionEvent",
    "Severity",
]
