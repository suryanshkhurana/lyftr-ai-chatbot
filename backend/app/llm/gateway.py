"""LiteLLM Router key pool with automatic, ordered failover."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import litellm
from litellm import Router

from app.llm import cache
from app.llm.failure_simulation import (
    FailureSimulationHook,
    reset_active_simulation,
    set_active_simulation,
)

logger = logging.getLogger(__name__)

_simulation_hook = FailureSimulationHook()


class ProvidersUnavailable(Exception):
    """Every configured key failed (or the pool is not usable)."""


@dataclass
class Completion:
    reply: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_hit: bool
    key_id: str | None
    fallback_attempts: int


def key_ids_for(count: int) -> list[str]:
    return [f"key_{i}" for i in range(1, count + 1)]


class LLMGateway:
    """One Router model group per key: ``key_1`` falls back to ``key_2``, ``key_3`` ... in order.

    Separate groups (instead of one group with N deployments) make the attempt order deterministic and
    let LiteLLM report the answering group/deployment and the number of fallbacks it attempted.
    ``num_retries=0`` makes each key a single attempt; ``disable_cooldowns`` keeps a failure (real or
    simulated) from affecting later requests.
    """

    def __init__(
        self,
        api_keys: list[str],
        model: str,
        temperature: float,
        max_tokens: int,
        timeout_seconds: float,
        api_base: str | None = None,
    ) -> None:
        if len(api_keys) < 2:
            raise ValueError("at least two API keys are required")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.key_ids = key_ids_for(len(api_keys))
        model_list = [
            {
                "model_name": key_id,
                "litellm_params": {
                    "model": model,
                    "api_key": key,
                    "timeout": timeout_seconds,
                    "max_retries": 0,
                    **({"api_base": api_base} if api_base else {}),
                },
                "model_info": {"id": key_id},
            }
            for key_id, key in zip(self.key_ids, api_keys, strict=True)
        ]
        self.router = Router(
            model_list=model_list,
            fallbacks=[{self.key_ids[0]: self.key_ids[1:]}],
            num_retries=0,
            disable_cooldowns=True,
            timeout=timeout_seconds,
            # Router passes caching=<cache_responses> to every call; without this the global cache is skipped.
            cache_responses=True,
            # In Router calls LiteLLM keys the cache on the *model group* (key_1, key_2, ...), so an answer
            # produced through key_2 would be invisible to requests that start at key_1. A caching group
            # (documented "caching across model groups") makes every key share one cache namespace. The
            # real model id is the group's first element, so the cache identity is model + messages.
            caching_groups=[(model, *self.key_ids)],
        )
        cache.enable_cache()
        # Some models reject generation params (e.g. Gemini 3.5 models reject `temperature`); let LiteLLM drop
        # unsupported params for the chosen model instead of failing every request.
        litellm.drop_params = True
        if _simulation_hook not in litellm.callbacks:
            litellm.callbacks.append(_simulation_hook)

    @property
    def keys_configured(self) -> int:
        return len(self.key_ids)

    async def complete(self, messages: list[dict[str, str]], simulation: dict[str, int] | None) -> Completion:
        kwargs: dict[str, Any] = {
            "model": self.key_ids[0],
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if simulation:
            # A cached answer must never short-circuit a failover demonstration.
            kwargs["cache"] = dict(cache.BYPASS_CACHE)

        token = set_active_simulation(simulation or None)
        try:
            response = await self.router.acompletion(**kwargs)
        except Exception as exc:  # provider/Router errors at the gateway boundary
            logger.warning("all keys failed: %s: %s", type(exc).__name__, _short(exc))
            raise ProvidersUnavailable from None
        finally:
            reset_active_simulation(token)

        reply = _reply_text(response)
        if not reply:
            logger.warning("provider returned an empty reply; treating as unavailable")
            raise ProvidersUnavailable

        input_tokens, output_tokens = self._usage(response, messages, reply)
        if cache.is_cache_hit(response):
            return Completion(reply, self.model, input_tokens, output_tokens, True, None, 0)

        hidden = getattr(response, "_hidden_params", None) or {}
        key_id = hidden.get("model_id")
        if key_id not in self.key_ids:
            logger.warning("could not identify answering deployment (model_id=%r)", key_id)
            key_id = None
        fallback_attempts = self._fallback_attempts(key_id)
        if fallback_attempts:
            logger.info("answered by %s after %d failed key(s)", key_id, fallback_attempts)
        return Completion(reply, self.model, input_tokens, output_tokens, False, key_id, fallback_attempts)

    def _fallback_attempts(self, key_id: str | None) -> int:
        # Groups are always tried in key order (key_1 -> key_2 -> ...), so every key before the answering
        # one failed. Note: LiteLLM's "x-litellm-attempted-fallbacks" header is the index of the fallback
        # entry that answered (key_3 after key_1+key_2 failed reports 1), not a count of failed keys.
        return self.key_ids.index(key_id) if key_id in self.key_ids else 0

    def _usage(self, response: Any, messages: list[dict[str, str]], reply: str) -> tuple[int, int]:
        usage = getattr(response, "usage", None)
        prompt = getattr(usage, "prompt_tokens", None)
        completion = getattr(usage, "completion_tokens", None)
        # Fallback only if the provider omitted usage: LiteLLM's tokenizer-based counter.
        if not isinstance(prompt, int) or prompt <= 0:
            prompt = litellm.token_counter(model=self.model, messages=messages)
        if not isinstance(completion, int) or completion < 0:
            completion = litellm.token_counter(model=self.model, text=reply)
        return int(prompt), int(completion)


def _reply_text(response: Any) -> str:
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError):
        return ""
    return content.strip() if isinstance(content, str) else ""


def _short(exc: Exception) -> str:
    # Provider errors are often multi-line JSON; collapse whitespace so the useful part is logged.
    return " ".join(str(exc).split())[:500]
