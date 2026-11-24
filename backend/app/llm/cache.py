"""LiteLLM built-in response cache configuration and hit detection.

LiteLLM 1.110.3 behavior verified by tests/test_cache.py:
- the cache key is built from model + messages + generation params (temperature, max_tokens, ...);
  api_key and metadata are not part of it, so identical prompts hit across sessions and keys;
- ``response._hidden_params["cache_hit"] is True`` marks a hit, and the original usage is preserved;
- writes happen in a background task, so an immediately repeated request may still miss.
"""

from __future__ import annotations

from typing import Any

import litellm
from litellm.caching.caching import Cache

CACHE_TYPE = "local"  # LiteLLM in-memory cache

# Per-call override that skips both lookup and store (used for failure-simulation requests).
BYPASS_CACHE: dict[str, bool] = {"no-cache": True, "no-store": True}


def enable_cache() -> None:
    if not isinstance(litellm.cache, Cache):
        litellm.cache = Cache(type=CACHE_TYPE)


def warm_up_cache_path() -> None:
    """Import LiteLLM's lazily-loaded cache-hit modules at startup.

    Otherwise the first cache hit after boot pays a one-off import cost (~100 ms+, more on a cold disk) and
    can look slower than a live call.
    """
    import importlib

    for module in (
        "litellm.caching.caching_handler",
        "litellm.llms.anthropic.messages.native.response_cache",
    ):
        try:
            importlib.import_module(module)
        except Exception:  # best effort: a missing optional module only costs latency, not correctness
            pass


def cache_enabled() -> bool:
    return isinstance(litellm.cache, Cache)


def is_cache_hit(response: Any) -> bool:
    hidden = getattr(response, "_hidden_params", None) or {}
    return hidden.get("cache_hit") is True
