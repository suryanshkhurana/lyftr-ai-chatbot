"""Optional last-resort fallback: a self-hosted, OpenAI-compatible model (e.g. Qwen3 in LM Studio via ngrok).

It is called only after every key in the LiteLLM key pool has failed for the current request. It never reads
or writes the LiteLLM response cache: LiteLLM stores a response before this module validates it, so a
thinking-only reply would otherwise be cached and served on every retry.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

import litellm

from app.llm import cache

logger = logging.getLogger(__name__)

FALLBACK_KEY_ID = "fallback"
NO_THINK_SUFFIX = " /no_think"
# ngrok's free tier shows an HTML interstitial to API clients unless this header is present.
EXTRA_HEADERS = {"ngrok-skip-browser-warning": "true"}

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)


class FallbackFailed(Exception):
    """The fallback did not produce a usable reply (offline, timeout, HTTP error, thinking-only output...)."""


@dataclass
class FallbackReply:
    reply: str
    model: str
    input_tokens: int
    output_tokens: int


def with_no_think(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Copy of the messages with ' /no_think' appended to the last user message (history keeps the original)."""
    copied = [dict(m) for m in messages]
    for message in reversed(copied):
        if message.get("role") == "user":
            message["content"] = f"{message['content']}{NO_THINK_SUFFIX}"
            break
    return copied


def clean_reply(text: str | None) -> str | None:
    """Strip closed <think>...</think> blocks. Unclosed thinking or an empty result returns None (= failure)."""
    if not isinstance(text, str):
        return None
    cleaned = _THINK_BLOCK.sub("", text)
    lowered = cleaned.lower()
    if "<think>" in lowered:  # opened but never closed: the model was cut off mid-reasoning
        return None
    if "</think>" in lowered:  # some chat templates omit the opening tag; keep only what follows the reasoning
        cleaned = cleaned[lowered.rfind("</think>") + len("</think>") :]
    cleaned = cleaned.strip()
    return cleaned or None


class FallbackClient:
    def __init__(
        self,
        model: str,
        api_base: str,
        api_key: str,
        timeout_seconds: float,
        temperature: float,
        max_tokens: int,
    ) -> None:
        self.model = model
        self.api_base = api_base
        self._api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def complete(self, messages: list[dict[str, str]]) -> FallbackReply:
        prompt = with_no_think(messages)
        try:
            # Async on purpose: a sync call would block the event loop for up to the full timeout.
            response = await litellm.acompletion(
                model=self.model,
                messages=prompt,
                api_base=self.api_base,
                api_key=self._api_key,
                timeout=self.timeout_seconds,
                extra_headers=dict(EXTRA_HEADERS),
                num_retries=0,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                caching=False,
                cache=dict(cache.BYPASS_CACHE),
            )
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            raise FallbackFailed(f"{type(exc).__name__}" + (f" status={status}" if status else "")) from None

        raw = _content(response)
        reply = clean_reply(raw)
        if reply is None:
            reason = "unclosed <think>" if isinstance(raw, str) and "<think>" in raw.lower() else "empty reply"
            raise FallbackFailed(reason)

        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        if not isinstance(prompt_tokens, int) or prompt_tokens <= 0:
            prompt_tokens = litellm.token_counter(model=self.model, messages=prompt)
        if not isinstance(completion_tokens, int) or completion_tokens < 0:
            completion_tokens = litellm.token_counter(model=self.model, text=raw or reply)
        return FallbackReply(reply, self.model, int(prompt_tokens), int(completion_tokens))


def _content(response: Any) -> str | None:
    try:
        return response.choices[0].message.content
    except (AttributeError, IndexError):
        return None
