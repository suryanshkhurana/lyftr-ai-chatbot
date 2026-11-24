"""The three public routes. Handlers stay thin; logic lives in services/repositories."""

from __future__ import annotations

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.llm import cache
from app.llm.failure_simulation import InvalidSimulationHeader
from app.schemas import ChatRequest, ChatResponse, HealthResponse, SessionMessages

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(request: Request):
    state = request.app.state
    db_ok = await run_in_threadpool(state.db.ping)
    gateway = state.chat_service.gateway
    problems = []
    if not db_ok:
        problems.append("database unreachable")
    if gateway is None:
        problems.append(state.key_config_error or "key pool not loaded")
    if not cache.cache_enabled():
        problems.append("cache disabled")
    if problems:
        return JSONResponse(status_code=503, content={"detail": "; ".join(problems)})
    return HealthResponse(status="ok", keys_configured=gateway.keys_configured, cache_enabled=True)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    x_simulate_failure: str | None = Header(default=None, alias="X-Simulate-Failure"),
):
    service = request.app.state.chat_service
    try:
        simulation = service.parse_simulation(x_simulate_failure)
    except InvalidSimulationHeader as exc:
        return JSONResponse(status_code=422, content={"detail": str(exc)})
    return await service.chat(body, simulation)


@router.get("/sessions/{session_id}/messages", response_model=SessionMessages)
async def session_messages(session_id: str, request: Request):
    messages = await run_in_threadpool(request.app.state.repo.get_messages, session_id)
    if messages is None:
        return JSONResponse(status_code=404, content={"detail": "session not found"})
    return SessionMessages(session_id=session_id, messages=messages)
