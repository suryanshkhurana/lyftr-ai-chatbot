"""Test fixtures.

Tests never touch a real provider. A LiteLLM ``CustomLLM`` registered as provider ``mockllm`` stands in
for the model API, so the real LiteLLM Router, fallback, cache and usage code paths are exercised.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

import litellm
import pytest
from fastapi.testclient import TestClient
from litellm import CustomLLM
from litellm.caching.caching import Cache
from litellm.types.utils import Choices, Message, ModelResponse, Usage

from app.core.config import Settings
from app.main import create_app

FAKE_KEYS = ["fake-key-ALPHA-0001", "fake-key-BRAVO-0002"]
MODEL = "mockllm/test-model"
LIVE_DELAY_S = 0.15  # simulated provider round-trip, so live calls are measurably slower than cache hits


@dataclass
class MockProviderState:
    calls: list[dict] = field(default_factory=list)  # successful calls: {"api_key", "messages"}
    attempts: list[str] = field(default_factory=list)  # every provider attempt (api_key), including failures
    failures: dict[str, int] = field(default_factory=dict)  # api_key -> real provider status to raise
    reply_override: str | None = None

    def reset(self) -> None:
        self.calls.clear()
        self.attempts.clear()
        self.failures.clear()
        self.reply_override = None


STATE = MockProviderState()


def _provider_error(status: int):
    kw = {"message": f"mock provider HTTP {status}", "llm_provider": "mockllm", "model": MODEL}
    return {
        429: litellm.RateLimitError,
        500: litellm.InternalServerError,
        502: litellm.BadGatewayError,
        503: litellm.ServiceUnavailableError,
    }[status](**kw)


class MockLLM(CustomLLM):
    async def acompletion(self, model, messages, api_key=None, **kwargs):  # type: ignore[override]
        STATE.attempts.append(api_key)
        await asyncio.sleep(LIVE_DELAY_S)
        if api_key in STATE.failures:
            raise _provider_error(STATE.failures[api_key])
        STATE.calls.append({"api_key": api_key, "messages": [dict(m) for m in messages]})
        last_user = next(m["content"] for m in reversed(messages) if m["role"] == "user")
        reply = STATE.reply_override if STATE.reply_override is not None else (
            f"reply #{len(STATE.calls)} to: {last_user}"
        )
        prompt_tokens = sum(len(m["content"].split()) + 4 for m in messages)
        completion_tokens = len(reply.split()) if reply else 0
        return ModelResponse(
            model="test-model",
            choices=[Choices(index=0, finish_reason="stop", message=Message(role="assistant", content=reply))],
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )


litellm.custom_provider_map = [{"provider": "mockllm", "custom_handler": MockLLM()}]


def make_settings(tmp_path, **overrides) -> Settings:
    values = {
        "LLM_API_KEYS": ",".join(FAKE_KEYS),
        "DATABASE_URL": f"sqlite:///{tmp_path / 'app.db'}",
        "ALLOWED_ORIGINS": "http://localhost:3000",
        "ENABLE_FAILURE_SIMULATION": True,
        "LLM_MODEL": MODEL,
        "LOG_LEVEL": "INFO",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture(autouse=True)
def fresh_state():
    STATE.reset()
    litellm.cache = Cache(type="local")  # isolate LiteLLM's in-memory cache per test
    yield
    STATE.reset()


@pytest.fixture
def settings(tmp_path):
    return make_settings(tmp_path)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def cache_entries() -> int:
    return len(litellm.cache.cache.cache_dict)


def wait_for_cache_entries(n: int, timeout: float = 5.0) -> None:
    """LiteLLM writes cache entries in a background task; wait until it has landed."""
    deadline = time.monotonic() + timeout
    while cache_entries() < n:
        if time.monotonic() > deadline:
            raise AssertionError(f"cache has {cache_entries()} entries, expected >= {n}")
        time.sleep(0.02)


def message_rows(settings: Settings) -> list[tuple]:
    import sqlite3

    with sqlite3.connect(settings.sqlite_path) as conn:
        return conn.execute("SELECT session_id, role, content, metadata FROM messages ORDER BY id").fetchall()


def session_rows(settings: Settings) -> list[tuple]:
    import sqlite3

    with sqlite3.connect(settings.sqlite_path) as conn:
        return conn.execute("SELECT session_id, system_prompt FROM sessions").fetchall()
