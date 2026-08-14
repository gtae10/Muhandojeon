from pydantic import BaseModel


class WearPoint(BaseModel):
    part: str
    severity: str


class ProductOut(BaseModel):
    id: str
    name: str
    purchasedAt: str
    conditionScore: int
    wearPoints: list[WearPoint]


class FingerprintOut(BaseModel):
    productId: str
    conditionScore: int
    wearPoints: list[WearPoint]


class ChatIn(BaseModel):
    productId: str
    message: str


class ChatOut(BaseModel):
    reply: str
