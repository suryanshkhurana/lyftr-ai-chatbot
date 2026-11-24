"""Request-scoped X-Simulate-Failure support.

The parsed simulation is stored in a ContextVar for the duration of one gateway call. A LiteLLM
CustomLogger hook (``async_pre_call_check``, awaited by the Router before each deployment attempt)
raises the same exception class LiteLLM raises for a real provider status, so the Router's normal
fallback logic handles it. Nothing about the real deployments/credentials is modified.
"""

from __future__ import annotations

from contextvars import ContextVar

import litellm
from litellm.integrations.custom_logger import CustomLogger

SUPPORTED_STATUSES = (429, 500, 502, 503)
WILDCARD = "*"

_active_simulation: ContextVar[dict[str, int] | None] = ContextVar("active_simulation", default=None)


class InvalidSimulationHeader(ValueError):
    pass


FALLBACK_TARGET = "fallback"
POOL_TARGET = "keys"


def parse_simulation_header(value: str, key_ids: list[str]) -> dict[str, int]:
    """Parse ``key_1=429,key_2=500`` / ``keys=429`` / ``fallback=503`` / ``*=429`` into {target: status}.

    Targets: ``key_N`` (one pool key), ``keys`` (every pool key), ``fallback`` (only the self-hosted
    fallback) and ``*`` (every pool key AND the fallback, so ``*`` still yields the assignment's 503).
    """
    result: dict[str, int] = {}
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if not parts:
        raise InvalidSimulationHeader("X-Simulate-Failure is empty")
    for part in parts:
        target, sep, raw_status = part.partition("=")
        target, raw_status = target.strip(), raw_status.strip()
        if not sep or not target or not raw_status.isdigit():
            raise InvalidSimulationHeader(f"invalid X-Simulate-Failure entry '{part}', expected <key_id>=<status>")
        status = int(raw_status)
        if status not in SUPPORTED_STATUSES:
            raise InvalidSimulationHeader(
                f"unsupported simulated status {status}; use one of {', '.join(map(str, SUPPORTED_STATUSES))}"
            )
        if target == WILDCARD:
            for kid in key_ids:
                result[kid] = status
            result[FALLBACK_TARGET] = status
        elif target == POOL_TARGET:
            for kid in key_ids:
                result[kid] = status
        elif target == FALLBACK_TARGET or target in key_ids:
            result[target] = status
        else:
            raise InvalidSimulationHeader(
                f"unknown target '{target}'; use one of: {', '.join(key_ids)}, {POOL_TARGET}, {FALLBACK_TARGET}, *"
            )
    return result


def simulated_exception(status: int, key_id: str, model: str) -> Exception:
    message = f"simulated HTTP {status} for {key_id}"
    provider = model.split("/", 1)[0] if "/" in model else "simulated"
    if status == 429:
        return litellm.RateLimitError(message=message, llm_provider=provider, model=model)
    if status == 502:
        return litellm.BadGatewayError(message=message, llm_provider=provider, model=model)
    if status == 503:
        return litellm.ServiceUnavailableError(message=message, llm_provider=provider, model=model)
    return litellm.InternalServerError(message=message, llm_provider=provider, model=model)


def set_active_simulation(simulation: dict[str, int] | None):
    return _active_simulation.set(simulation)


def reset_active_simulation(token) -> None:
    _active_simulation.reset(token)


class FailureSimulationHook(CustomLogger):
    """Raises the simulated provider error for targeted deployments during the current request only."""

    async def async_pre_call_check(self, deployment: dict, parent_otel_span=None) -> dict | None:  # type: ignore[override]
        simulation = _active_simulation.get()
        if not simulation:
            return None
        key_id = (deployment.get("model_info") or {}).get("id")
        if key_id in simulation:
            model = (deployment.get("litellm_params") or {}).get("model", "unknown")
            raise simulated_exception(simulation[key_id], key_id, model)
        return None
