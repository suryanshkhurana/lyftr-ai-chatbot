"""Chat orchestration: build prompt from SQLite history, call the gateway, persist on success."""

from __future__ import annotations

import time

from starlette.concurrency import run_in_threadpool

from app.db.repository import ChatRepository
from app.llm.failure_simulation import parse_simulation_header
from app.llm.gateway import LLMGateway, ProvidersUnavailable
from app.schemas import ChatMetadata, ChatRequest, ChatResponse


class ChatService:
    def __init__(
        self,
        repo: ChatRepository,
        gateway: LLMGateway | None,
        default_system_prompt: str,
        simulation_enabled: bool,
    ) -> None:
        self.repo = repo
        self.gateway = gateway
        self.default_system_prompt = default_system_prompt
        self.simulation_enabled = simulation_enabled

    def parse_simulation(self, header: str | None) -> dict[str, int] | None:
        """Raises InvalidSimulationHeader for a malformed header when the hook is enabled."""
        if not self.simulation_enabled or header is None or self.gateway is None:
            return None
        return parse_simulation_header(header, self.gateway.key_ids)

    async def chat(self, request: ChatRequest, simulation: dict[str, int] | None) -> ChatResponse:
        started = time.perf_counter()
        if self.gateway is None:
            raise ProvidersUnavailable

        stored = await run_in_threadpool(self.repo.load_session, request.session_id)
        system_prompt = request.system_prompt or stored.system_prompt or self.default_system_prompt
        # session_id is deliberately NOT sent to the LLM: the cache key must be model + messages only.
        messages = [
            {"role": "system", "content": system_prompt},
            *stored.history,
            {"role": "user", "content": request.message},
        ]

        completion = await self.gateway.complete(messages, simulation)
        latency_ms = int(round((time.perf_counter() - started) * 1000))

        metadata = ChatMetadata(
            resolution_source="LLM_CACHE" if completion.cache_hit else "LIVE_INFERENCE",
            model=completion.model,
            latency_ms=latency_ms,
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
            key_id=completion.key_id,
            fallback_attempts=completion.fallback_attempts,
        )
        await run_in_threadpool(
            self.repo.save_turn,
            request.session_id,
            request.system_prompt,
            request.message,
            completion.reply,
            metadata.model_dump(),
        )
        return ChatResponse(session_id=request.session_id, reply=completion.reply, metadata=metadata)
