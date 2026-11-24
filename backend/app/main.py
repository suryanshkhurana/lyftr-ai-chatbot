"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import litellm
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.connection import Database
from app.db.repository import ChatRepository
from app.db.schema import create_schema
from app.llm import cache
from app.llm.fallback import FallbackClient
from app.llm.gateway import LLMGateway, ProvidersUnavailable
from app.services.chat_service import ChatService

logger = logging.getLogger("app")

ALL_PROVIDERS_UNAVAILABLE = {"detail": "all providers unavailable"}


def create_app(settings: Settings | None = None, gateway: LLMGateway | None = None) -> FastAPI:
    settings = settings or get_settings()
    secrets = [*settings.api_keys, settings.fallback_llm_api_key.strip()]
    configure_logging(settings.log_level, secrets)
    litellm.suppress_debug_info = True

    db = Database(settings.sqlite_path)
    repo = ChatRepository(db)
    key_error = settings.key_config_error
    fallback = None
    if settings.fallback_enabled:
        fallback = FallbackClient(
            model=settings.fallback_llm_model.strip(),
            api_base=settings.fallback_llm_api_base.strip(),
            api_key=settings.fallback_llm_api_key.strip(),
            timeout_seconds=settings.fallback_llm_timeout_seconds,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
    if gateway is None and key_error is None:
        gateway = LLMGateway(
            api_keys=settings.api_keys,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout_seconds=settings.llm_timeout_seconds,
            api_base=settings.llm_api_base or None,
            fallback=fallback,
        )
    if gateway is None:
        logger.error("key pool not loaded: %s", key_error)
    cache.enable_cache()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        create_schema(db)
        cache.warm_up_cache_path()
        logger.info(
            "started: keys=%d model=%s cache=%s simulation=%s fallback=%s db=%s",
            gateway.keys_configured if gateway else 0,
            settings.llm_model,
            cache.cache_enabled(),
            settings.enable_failure_simulation,
            settings.fallback_llm_model.strip() if fallback else "off",
            settings.sqlite_path,
        )
        yield

    # No docs/redoc/openapi: the public API is exactly the three routes.
    app = FastAPI(title="Lyftr AI", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.settings = settings
    app.state.db = db
    app.state.repo = repo
    app.state.key_config_error = key_error
    app.state.chat_service = ChatService(
        repo=repo,
        gateway=gateway,
        default_system_prompt=settings.default_system_prompt,
        simulation_enabled=settings.enable_failure_simulation,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Simulate-Failure"],
    )

    @app.exception_handler(ProvidersUnavailable)
    async def providers_unavailable(_: Request, __: ProvidersUnavailable):
        return JSONResponse(status_code=503, content=ALL_PROVIDERS_UNAVAILABLE)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        # FastAPI's standard shape, minus echoed input values.
        errors = [{k: v for k, v in e.items() if k in ("type", "loc", "msg")} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        logger.error("unhandled error: %s", type(exc).__name__, exc_info=exc)
        return JSONResponse(status_code=500, content={"detail": "internal server error"})

    app.include_router(router)
    return app
# Run with: uvicorn app.main:create_app --factory
