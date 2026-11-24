"""Self-hosted last-resort fallback (runs only after the whole key pool failed)."""

import logging

import pytest
from fastapi.testclient import TestClient

from app.llm.fallback import clean_reply, with_no_think
from app.main import create_app
from tests.conftest import FAKE_KEYS, STATE, make_settings, message_rows, wait_for_cache_entries

FB_KEY = "fake-FALLBACK-key-9999"
FB_MODEL = "mockllm/qwen3-14b"
UNAVAILABLE = {"detail": "all providers unavailable"}


def fb_settings(tmp_path, **overrides):
    values = {
        "FALLBACK_LLM_MODEL": FB_MODEL,
        "FALLBACK_LLM_API_BASE": "https://example-ngrok.app/v1",
        "FALLBACK_LLM_API_KEY": FB_KEY,
        "FALLBACK_LLM_TIMEOUT_SECONDS": 120,
    }
    values.update(overrides)
    return make_settings(tmp_path, **values)


@pytest.fixture
def fb_client(tmp_path):
    with TestClient(create_app(fb_settings(tmp_path))) as c:
        yield c


def chat(c, sid, msg, header=None):
    headers = {"X-Simulate-Failure": header} if header else {}
    return c.post("/chat", json={"session_id": sid, "message": msg}, headers=headers)


def fallback_requests():
    return [r for r in STATE.requests if r["api_key"] == FB_KEY]


# ---- disabled / unchanged behaviour -------------------------------------------------------------------


def test_fallback_disabled_keys_429_is_503(client, settings):
    assert not settings.fallback_enabled
    r = chat(client, "d1", "hi", "keys=429")
    assert r.status_code == 503 and r.json() == UNAVAILABLE
    assert message_rows(settings) == []


@pytest.mark.parametrize("missing", ["FALLBACK_LLM_MODEL", "FALLBACK_LLM_API_BASE", "FALLBACK_LLM_API_KEY"])
def test_any_empty_setting_disables_fallback(tmp_path, missing):
    s = fb_settings(tmp_path, **{missing: ""})
    assert not s.fallback_enabled
    with TestClient(create_app(s)) as c:
        assert chat(c, "d2", "hi", "keys=429").status_code == 503
    assert fallback_requests() == []


def test_pool_failover_unchanged_with_fallback_enabled(fb_client):
    for status in (429, 500):
        m = chat(fb_client, f"k{status}", "hello", f"key_1={status}").json()["metadata"]
        assert (m["key_id"], m["fallback_attempts"]) == ("key_2", 1)
    assert fallback_requests() == []


def test_health_unchanged_by_fallback(fb_client):
    assert fb_client.get("/health").json() == {"status": "ok", "keys_configured": 2, "cache_enabled": True}


# ---- fallback answers ---------------------------------------------------------------------------------


def test_keys_429_served_by_fallback(fb_client, tmp_path):
    r = chat(fb_client, "fb1", "What is 2+2?", "keys=429")
    assert r.status_code == 200
    body = r.json()
    meta = body["metadata"]
    assert meta["key_id"] == "fallback"
    assert meta["model"] == FB_MODEL
    assert meta["resolution_source"] == "LIVE_INFERENCE"
    assert meta["fallback_attempts"] == 2  # both pool keys failed first
    assert meta["input_tokens"] > 0 and meta["output_tokens"] > 0

    (req,) = fallback_requests()
    assert req["messages"][-1]["content"] == "What is 2+2? /no_think"
    assert req["headers"]["ngrok-skip-browser-warning"] == "true"
    assert req["timeout"] == 120

    hist = fb_client.get("/sessions/fb1/messages").json()["messages"]
    assert hist[0] == {"role": "user", "content": "What is 2+2?"}  # original text, no /no_think
    assert hist[1]["content"] == body["reply"] and hist[1]["metadata"]["key_id"] == "fallback"


def test_fallback_keeps_history_context(fb_client):
    first = chat(fb_client, "ctx", "My name is Ada.").json()
    chat(fb_client, "ctx", "What is my name?", "keys=500")
    sent = fallback_requests()[-1]["messages"]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]
    assert sent[1]["content"] == "My name is Ada."  # only the last user message gets /no_think
    assert sent[2]["content"] == first["reply"]
    assert sent[3]["content"] == "What is my name? /no_think"


def test_wildcard_still_503_and_fallback_never_called(fb_client, tmp_path):
    r = chat(fb_client, "w1", "hi", "*=429")
    assert r.status_code == 503 and r.json() == UNAVAILABLE
    assert fallback_requests() == []
    assert fb_client.get("/sessions/w1/messages").status_code == 404


def test_fallback_target_alone_only_affects_fallback(fb_client):
    m = chat(fb_client, "t1", "hi", "fallback=503").json()["metadata"]
    assert m["key_id"] == "key_1"
    r = chat(fb_client, "t2", "hi", "keys=429,fallback=500")
    assert r.status_code == 503 and r.json() == UNAVAILABLE
    assert fallback_requests() == []


def test_real_pool_outage_without_header_uses_fallback(fb_client):
    STATE.failures.update({FAKE_KEYS[0]: 429, FAKE_KEYS[1]: 503})
    m = chat(fb_client, "real", "hi").json()["metadata"]
    assert (m["key_id"], m["fallback_attempts"], m["resolution_source"]) == ("fallback", 2, "LIVE_INFERENCE")


# ---- fallback failures --------------------------------------------------------------------------------


@pytest.mark.parametrize("status", [0, 429, 500, 503])  # 0 = offline / connection refused
def test_fallback_offline_then_back_online(fb_client, tmp_path, status):
    STATE.failures[FB_KEY] = status
    r = chat(fb_client, "off", "hello there", "keys=429")
    assert r.status_code == 503 and r.json() == UNAVAILABLE
    assert fb_client.get("/sessions/off/messages").status_code == 404

    STATE.failures.pop(FB_KEY)  # laptop/ngrok back online
    r = chat(fb_client, "off", "hello there", "keys=429")
    assert r.status_code == 200
    assert r.json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert r.json()["metadata"]["key_id"] == "fallback"


def test_thinking_only_reply_is_503_and_not_cached(fb_client):
    STATE.replies[FB_KEY] = "<think>still reasoning about this"
    r = chat(fb_client, "th", "Explain gravity", "keys=429")
    assert r.status_code == 503 and r.json() == UNAVAILABLE

    STATE.replies[FB_KEY] = "<think>ok</think>Gravity pulls masses together."
    r = chat(fb_client, "th", "Explain gravity", "keys=429")
    assert r.status_code == 200
    assert r.json()["reply"] == "Gravity pulls masses together."
    assert r.json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert len(fallback_requests()) == 2  # second attempt really called the fallback again


def test_fallback_never_reads_or_writes_cache(fb_client):
    import litellm

    chat(fb_client, "nc1", "same question", "keys=429")
    chat(fb_client, "nc2", "same question", "keys=429")
    assert len(fallback_requests()) == 2
    assert len(litellm.cache.cache.cache_dict) == 0


def test_pool_answers_still_cached_with_fallback_enabled(fb_client):
    live = chat(fb_client, "pc1", "cache me").json()
    wait_for_cache_entries(1)
    hit = chat(fb_client, "pc2", "cache me").json()
    assert hit["metadata"]["resolution_source"] == "LLM_CACHE"
    assert hit["reply"] == live["reply"]
    assert (hit["metadata"]["key_id"], hit["metadata"]["fallback_attempts"]) == (None, 0)


@pytest.mark.parametrize(
    "reply", ["<think>only thinking</think>", "   ", "<think>never closed", "<THINK>x</THINK>  "]
)
def test_unusable_fallback_replies_are_503(fb_client, settings, reply):
    STATE.replies[FB_KEY] = reply
    r = chat(fb_client, "bad", "hi", "keys=429")
    assert r.status_code == 503 and r.json() == UNAVAILABLE


def test_failed_requests_store_nothing(fb_client, tmp_path):
    STATE.failures[FB_KEY] = 0
    chat(fb_client, "nothing", "hi", "keys=429")
    chat(fb_client, "nothing", "hi", "*=500")
    assert fb_client.get("/sessions/nothing/messages").status_code == 404


# ---- header parsing -----------------------------------------------------------------------------------


@pytest.mark.parametrize("header", ["fallbacks=429", "all=429", "keys=404", "fallback=", "key_9=429"])
def test_invalid_targets_still_422(fb_client, header):
    r = chat(fb_client, "inv", "hi", header)
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)


# ---- logging ------------------------------------------------------------------------------------------


def test_served_by_logged_and_fallback_key_redacted(fb_client, caplog):
    caplog.set_level(logging.INFO)
    chat(fb_client, "log1", "hi")
    chat(fb_client, "log2", "hi there", "keys=429")
    STATE.failures[FB_KEY] = 500
    chat(fb_client, "log3", "hi again", "keys=429")
    text = caplog.text
    assert "served_by=key_1" in text
    assert "served_by=fallback" in text
    assert "fallback failed: InternalServerError status=500" in text
    for secret in (FB_KEY, *FAKE_KEYS):
        assert secret not in text


# ---- helpers ------------------------------------------------------------------------------------------


def test_clean_reply():
    assert clean_reply("<think>a\nb</think>\n\nAnswer.") == "Answer."
    assert clean_reply("No thinking here.") == "No thinking here."
    assert clean_reply("reasoning only</think>Final") == "Final"
    assert clean_reply("<think>cut off") is None
    assert clean_reply("<think></think>") is None
    assert clean_reply(None) is None


def test_with_no_think_copies():
    original = [{"role": "system", "content": "s"}, {"role": "user", "content": "q"}]
    copied = with_no_think(original)
    assert copied[-1]["content"] == "q /no_think"
    assert original[-1]["content"] == "q"
