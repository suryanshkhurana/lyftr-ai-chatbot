import logging

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import FAKE_KEYS, STATE, make_settings, message_rows, session_rows, wait_for_cache_entries

UNAVAILABLE = {"detail": "all providers unavailable"}


@pytest.mark.parametrize("status", [429, 500, 502, 503])
def test_simulated_key_1_failure_falls_back_to_key_2(client, settings, status):
    r = client.post(
        "/chat",
        json={"session_id": f"f{status}", "message": "hello"},
        headers={"X-Simulate-Failure": f"key_1={status}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["metadata"]["key_id"] == "key_2"
    assert body["metadata"]["fallback_attempts"] == 1
    assert body["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    # A real completion came from key_2's deployment; key_1 was never actually called.
    assert [c["api_key"] for c in STATE.calls] == [FAKE_KEYS[1]]
    assert body["reply"] == f"reply #1 to: hello"
    assert len(message_rows(settings)) == 2


def test_all_keys_simulated_failure_returns_503_and_saves_nothing(client, settings):
    client.post("/chat", json={"session_id": "keep", "message": "before"})
    before = message_rows(settings)
    for header in ("*=429", "key_1=429,key_2=500"):
        for sid in ("keep", "brand-new"):
            r = client.post("/chat", json={"session_id": sid, "message": "x"}, headers={"X-Simulate-Failure": header})
            assert r.status_code == 503
            assert r.json() == UNAVAILABLE
    assert message_rows(settings) == before
    assert [s[0] for s in session_rows(settings)] == ["keep"]
    assert client.get("/sessions/brand-new/messages").status_code == 404


def test_simulation_is_request_scoped(client):
    client.post("/chat", json={"session_id": "rs", "message": "a"}, headers={"X-Simulate-Failure": "key_1=429"})
    r = client.post("/chat", json={"session_id": "rs", "message": "b"})
    assert r.json()["metadata"]["key_id"] == "key_1"
    assert r.json()["metadata"]["fallback_attempts"] == 0


def test_simulation_bypasses_cache(client):
    first = client.post("/chat", json={"session_id": "c1", "message": "cached?"}).json()
    wait_for_cache_entries(1)
    r = client.post(
        "/chat", json={"session_id": "c2", "message": "cached?"}, headers={"X-Simulate-Failure": "key_1=429"}
    ).json()
    assert r["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert r["metadata"]["key_id"] == "key_2"
    assert r["reply"] != first["reply"]  # a fresh provider call, not the cached text
    r = client.post("/chat", json={"session_id": "c3", "message": "cached?"}, headers={"X-Simulate-Failure": "*=503"})
    assert r.status_code == 503


def test_simulation_disabled_ignores_header(tmp_path):
    s = make_settings(tmp_path, ENABLE_FAILURE_SIMULATION=False)
    with TestClient(create_app(s)) as c:
        r = c.post("/chat", json={"session_id": "d", "message": "hi"}, headers={"X-Simulate-Failure": "*=429"})
        assert r.status_code == 200
        assert r.json()["metadata"]["key_id"] == "key_1"
        r = c.post("/chat", json={"session_id": "d", "message": "hi2"}, headers={"X-Simulate-Failure": "garbage"})
        assert r.status_code == 200


@pytest.mark.parametrize("header", ["garbage", "key_1=404", "key_9=429", "key_1=", "=429", "key_1=abc"])
def test_invalid_simulation_header_is_422_and_not_saved(client, settings, header):
    r = client.post("/chat", json={"session_id": "bad", "message": "hi"}, headers={"X-Simulate-Failure": header})
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str)
    assert message_rows(settings) == []


def test_real_provider_429_and_5xx_fail_over(client):
    STATE.failures[FAKE_KEYS[0]] = 429
    r = client.post("/chat", json={"session_id": "real", "message": "hi"}).json()
    assert (r["metadata"]["key_id"], r["metadata"]["fallback_attempts"]) == ("key_2", 1)
    STATE.failures[FAKE_KEYS[0]] = 500
    r = client.post("/chat", json={"session_id": "real", "message": "again"}).json()
    assert (r["metadata"]["key_id"], r["metadata"]["fallback_attempts"]) == ("key_2", 1)


def test_real_provider_all_keys_failing_is_503(client, settings):
    STATE.failures.update({FAKE_KEYS[0]: 429, FAKE_KEYS[1]: 503})
    r = client.post("/chat", json={"session_id": "down", "message": "hi"})
    assert r.status_code == 503 and r.json() == UNAVAILABLE
    assert message_rows(settings) == []


def test_three_keys_fallback_count(tmp_path):
    s = make_settings(tmp_path, LLM_API_KEYS="kA-111,kB-222,kC-333")
    with TestClient(create_app(s)) as c:
        r = c.post(
            "/chat", json={"session_id": "t", "message": "hi"}, headers={"X-Simulate-Failure": "key_1=429,key_2=502"}
        ).json()
        assert r["metadata"]["key_id"] == "key_3"
        assert r["metadata"]["fallback_attempts"] == 2
        r = c.post("/chat", json={"session_id": "t2", "message": "hi"}, headers={"X-Simulate-Failure": "key_2=500"}).json()
        assert (r["metadata"]["key_id"], r["metadata"]["fallback_attempts"]) == ("key_1", 0)


def test_keys_never_exposed_in_responses_or_logs(client, caplog):
    caplog.set_level(logging.DEBUG)
    responses = [
        client.post("/chat", json={"session_id": "sec", "message": "hi"}, headers={"X-Simulate-Failure": "key_1=429"}),
        client.post("/chat", json={"session_id": "sec", "message": "hi"}, headers={"X-Simulate-Failure": "*=500"}),
        client.get("/sessions/sec/messages"),
        client.get("/health"),
    ]
    STATE.failures[FAKE_KEYS[0]] = 429
    STATE.failures[FAKE_KEYS[1]] = 429
    responses.append(client.post("/chat", json={"session_id": "sec2", "message": "hi"}))
    blob = "".join(r.text for r in responses) + caplog.text
    for key in FAKE_KEYS:
        assert key not in blob
