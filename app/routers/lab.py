"""Persona Bot Lab 라우터 — 대시보드(`/lab`)와 실행/조회 API.

대시보드는 FastAPI 가 서빙하는 단일 HTML + vanilla JS 다(프론트 담당과 충돌 방지를 위한
의도적 선택 — 빌드 툴체인을 도입하지 않는다).

진행률은 폴링(`/lab/runs/{id}/progress`)과 SSE(`/lab/runs/{id}/stream`) 둘 다 제공한다.
SSE 가 막히는 환경(프록시 등)에서도 데모가 죽지 않게 하려는 것이다.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.lab.runner import LabConfig, get_progress, new_run_id, run_lab
from app.lab.summary import latest_run_id, list_runs, session_detail, summarize
from app.personas import load_personas, validate_bindings
from app.strategies import load_strategies

router = APIRouter(tags=["Lab"])

STATIC_DIR = Path(__file__).resolve().parent.parent / "lab" / "static"

_threads: dict[str, threading.Thread] = {}


class RunRequest(BaseModel):
    """시뮬레이션 실행 요청."""

    runs_per_pair: int | None = Field(default=None, ge=1, le=10)
    concurrency: int | None = Field(default=None, ge=1, le=16)
    max_turns: int | None = Field(default=None, ge=2, le=12)
    persona_ids: list[str] | None = None
    strategy_ids: list[str] | None = None


@router.get("/lab", summary="Persona Bot Lab 대시보드", include_in_schema=False)
def lab_page() -> FileResponse:
    path = STATIC_DIR / "lab.html"
    if not path.exists():  # pragma: no cover
        raise HTTPException(status_code=500, detail="lab.html 이 없다")
    return FileResponse(path, media_type="text/html")


@router.get("/lab/config", summary="페르소나·전략 정의와 바인딩 상태")
def lab_config() -> dict[str, Any]:
    personas = load_personas()
    strategies = load_strategies()
    return {
        "personas": [p.as_dict() for p in personas.values()],
        "strategies": [s.as_dict() for s in strategies.values()],
        "defaults": LabConfig.from_settings().as_dict(),
        "binding_problems": validate_bindings(),
    }


@router.post("/lab/run", summary="시뮬레이션 실행 (백그라운드)")
def lab_run(request: RunRequest) -> dict[str, Any]:
    config = LabConfig.from_settings(
        runs_per_pair=request.runs_per_pair,
        concurrency=request.concurrency,
        max_turns=request.max_turns,
        persona_ids=request.persona_ids,
        strategy_ids=request.strategy_ids,
    )
    run_id = new_run_id()
    thread = threading.Thread(
        target=run_lab, kwargs={"config": config, "run_id": run_id}, daemon=True
    )
    _threads[run_id] = thread
    thread.start()
    return {"run_id": run_id, "config": config.as_dict()}


@router.get("/lab/runs", summary="실행 목록")
def lab_runs(limit: int = 20) -> dict[str, Any]:
    return {"runs": list_runs(limit=limit), "latest": latest_run_id()}


@router.get("/lab/runs/{run_id}", summary="실행 결과 집계")
def lab_run_summary(run_id: str) -> dict[str, Any]:
    if run_id == "latest":
        resolved = latest_run_id()
        if resolved is None:
            return {"run": {}, "totals": {"sessions": 0}, "by_strategy": [], "heatmap": []}
        run_id = resolved
    return summarize(run_id)


@router.get("/lab/runs/{run_id}/progress", summary="진행률 (폴링)")
def lab_progress(run_id: str) -> dict[str, Any]:
    progress = get_progress(run_id)
    if not progress:
        # 재시작 이후에는 메모리 진행률이 없다. DB 기록으로 대체한다.
        runs = {r["run_id"]: r for r in list_runs(limit=50)}
        row = runs.get(run_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"실행을 찾을 수 없다: {run_id}")
        return {
            "run_id": run_id,
            "status": row["status"],
            "total": row["total_sessions"],
            "completed": row["completed_sessions"],
            "source": "db",
        }
    return progress


@router.get("/lab/runs/{run_id}/stream", summary="진행률 (SSE)", include_in_schema=False)
def lab_stream(run_id: str) -> StreamingResponse:
    def events() -> Iterator[str]:
        for _ in range(600):  # 최대 5분
            progress = get_progress(run_id)
            yield f"data: {json.dumps(progress, ensure_ascii=False)}\n\n"
            if progress.get("status") == "done":
                break
            time.sleep(0.5)

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/lab/sessions/{session_id}", summary="세션 대화 전문")
def lab_session(session_id: int) -> dict[str, Any]:
    detail = session_detail(session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"세션을 찾을 수 없다: {session_id}")
    return detail
