import sqlite3

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings


def test_schema_created_on_startup(client, settings):
    with sqlite3.connect(settings.sqlite_path) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(messages)")]
        assert cols == ["id", "session_id", "role", "content", "metadata", "created_at"]
        assert [r[1] for r in conn.execute("PRAGMA table_info(sessions)")] == [
            "session_id",
            "system_prompt",
            "created_at",
        ]
        indexes = [r[1] for r in conn.execute("PRAGMA index_list(messages)")]
        assert "idx_messages_session_id_id" in indexes


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "keys_configured": 2, "cache_enabled": True}


def test_health_reports_actual_key_count(tmp_path):
    s = make_settings(tmp_path, LLM_API_KEYS="a-key-1, b-key-2 ,c-key-3")
    with TestClient(create_app(s)) as c:
        assert c.get("/health").json()["keys_configured"] == 3


def test_insufficient_keys_fail_readiness_and_chat(tmp_path):
    s = make_settings(tmp_path, LLM_API_KEYS="only-one-key")
    with TestClient(create_app(s)) as c:
        r = c.get("/health")
        assert r.status_code == 503
        assert "at least 2 keys" in r.json()["detail"]
        r = c.post("/chat", json={"session_id": "s1", "message": "hi"})
        assert r.status_code == 503
        assert r.json() == {"detail": "all providers unavailable"}


def test_empty_key_entry_rejected(tmp_path):
    s = make_settings(tmp_path, LLM_API_KEYS="k1,,k2")
    with TestClient(create_app(s)) as c:
        r = c.get("/health")
        assert r.status_code == 503
        assert "empty entry" in r.json()["detail"]


def test_only_three_routes_exposed(client):
    from fastapi.routing import APIRoute

    def walk(routes):
        for r in routes:
            if isinstance(r, APIRoute):
                yield r
            # FastAPI 0.165 wraps included routers in _IncludedRouter(original_router=...).
            nested = getattr(r, "original_router", None) or getattr(r, "router", None) or r
            yield from walk(getattr(nested, "routes", []) if nested is not r else getattr(r, "routes", []))

    paths = sorted({(tuple(sorted(r.methods - {"HEAD"})), r.path) for r in walk(client.app.routes)})
    assert paths == [
        (("GET",), "/health"),
        (("GET",), "/sessions/{session_id}/messages"),
        (("POST",), "/chat"),
    ]
    for p in ("/docs", "/redoc", "/openapi.json"):
        r = client.get(p)
        assert r.status_code == 404
        assert r.headers["content-type"].startswith("application/json")


def test_cors_allows_configured_origin(client):
    r = client.options(
        "/chat",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-simulate-failure",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
    r = client.options(
        "/chat", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"}
    )
    assert "access-control-allow-origin" not in r.headers


def test_unsupported_generation_params_are_dropped_not_fatal(client):
    """Regression: Gemini 3.5 models reject `temperature`; LiteLLM must drop it instead of failing every key."""
    import litellm
    from litellm.utils import get_optional_params

    assert litellm.drop_params is True
    params = get_optional_params(
        model="gemini-3.5-flash-lite", custom_llm_provider="gemini", temperature=0.2, max_tokens=2048
    )
    assert "temperature" not in params
    assert params.get("max_output_tokens") == 2048
