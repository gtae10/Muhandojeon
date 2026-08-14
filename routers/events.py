"""
routers/events.py - 행동 이벤트 로깅 API
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models import SessionEvent, EventType
from schemas import EventLogRequest, EventLogResponse

router = APIRouter(prefix="/api/events", tags=["Events"])


@router.post("/log", response_model=EventLogResponse, status_code=201)
async def log_event(payload: EventLogRequest, db: AsyncSession = Depends(get_db)):
    """
    프론트엔드 → 고객 행동 이벤트 저장.
    AI 1(망설임 분류) 데이터 파이프라인 인풋.
    """
    try:
        event_type_enum = EventType(payload.event_type)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid event_type: {payload.event_type}")

    event = SessionEvent(
        event_id     = str(uuid.uuid4()),
        user_id      = payload.user_id,
        session_id   = payload.session_id,
        product_id   = payload.product_id,
        event_type   = event_type_enum,
        duration_sec = payload.duration_sec,
        device       = payload.device,
        referrer     = payload.referrer,
        extra_data   = payload.extra_data or {},
    )
    db.add(event)
    await db.flush()

    return EventLogResponse(event_id=event.event_id)
