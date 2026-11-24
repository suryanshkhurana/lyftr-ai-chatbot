"""Logging setup that redacts configured API keys from every log record."""

from __future__ import annotations

import logging
from collections.abc import Iterable

_LITELLM_LOGGERS = ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy", "litellm", "httpx", "httpcore")


class SecretRedactingFilter(logging.Filter):
    def __init__(self, secrets: Iterable[str]) -> None:
        super().__init__()
        # Longest first so a key that contains another key is fully masked.
        self._secrets = sorted({s for s in secrets if s}, key=len, reverse=True)

    def _redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, "***")
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        if not self._secrets:
            return True
        try:
            message = record.getMessage()
        except Exception:  # malformed format args: fall back to the raw template
            message = str(record.msg)
        record.msg = self._redact(message)
        record.args = None
        if record.exc_info and record.exc_info[1] is not None:
            # Pre-render the traceback redacted, then drop exc_info so it is not rendered raw.
            record.exc_text = self._redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        return True


def configure_logging(level: str, secrets: Iterable[str]) -> None:
    redactor = SecretRedactingFilter(secrets)
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(handler)
    root.setLevel(level.upper())
    for handler in root.handlers:
        handler.filters = [f for f in handler.filters if not isinstance(f, SecretRedactingFilter)]
        handler.addFilter(redactor)
    for name in _LITELLM_LOGGERS:
        lg = logging.getLogger(name)
        lg.filters = [f for f in lg.filters if not isinstance(f, SecretRedactingFilter)]
        lg.addFilter(redactor)
        for handler in lg.handlers:
            handler.filters = [f for f in handler.filters if not isinstance(f, SecretRedactingFilter)]
            handler.addFilter(redactor)
        # LiteLLM logs every fallback at ERROR with provider text; we log our own concise line instead.
        lg.setLevel(logging.CRITICAL if name.startswith("LiteLLM") else logging.WARNING)
