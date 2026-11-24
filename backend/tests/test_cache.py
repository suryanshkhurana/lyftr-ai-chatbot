from tests.conftest import FAKE_KEYS, STATE, message_rows, wait_for_cache_entries


def test_same_first_message_in_new_session_hits_cache(client, settings):
    live = client.post("/chat", json={"session_id": "c-1", "message": "What is the capital of France?"}).json()
    wait_for_cache_entries(1)
    hit = client.post("/chat", json={"session_id": "c-2", "message": "What is the capital of France?"}).json()

    assert live["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert hit["metadata"]["resolution_source"] == "LLM_CACHE"
    assert hit["reply"] == live["reply"]
    assert hit["metadata"]["input_tokens"] == live["metadata"]["input_tokens"]
    assert hit["metadata"]["output_tokens"] == live["metadata"]["output_tokens"]
    assert hit["metadata"]["key_id"] is None
    assert hit["metadata"]["fallback_attempts"] == 0
    assert hit["metadata"]["model"] == live["metadata"]["model"]
    # Measured, not faked: the hit skipped the (mock) provider round-trip.
    assert hit["metadata"]["latency_ms"] < live["metadata"]["latency_ms"]
    assert len(STATE.calls) == 1
    # Cache hits are real turns of the new session and are stored too.
    hist = client.get("/sessions/c-2/messages").json()["messages"]
    assert hist[1]["metadata"]["resolution_source"] == "LLM_CACHE"
    assert len(message_rows(settings)) == 4


def test_different_message_misses_cache(client):
    client.post("/chat", json={"session_id": "d-1", "message": "Question one"})
    wait_for_cache_entries(1)
    r = client.post("/chat", json={"session_id": "d-2", "message": "Question two"}).json()
    assert r["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert r["metadata"]["key_id"] == "key_1"
    assert len(STATE.calls) == 2


def test_same_message_with_different_history_misses_cache(client):
    client.post("/chat", json={"session_id": "h-1", "message": "hello"})
    wait_for_cache_entries(1)
    # Same new message, but this session has prior history -> different full message list.
    client.post("/chat", json={"session_id": "h-2", "message": "something else"})
    wait_for_cache_entries(2)
    r = client.post("/chat", json={"session_id": "h-2", "message": "hello"}).json()
    assert r["metadata"]["resolution_source"] == "LIVE_INFERENCE"


def test_different_system_prompt_misses_cache(client):
    client.post("/chat", json={"session_id": "p-1", "message": "hello"})
    wait_for_cache_entries(1)
    r = client.post("/chat", json={"session_id": "p-2", "message": "hello", "system_prompt": "Be terse."}).json()
    assert r["metadata"]["resolution_source"] == "LIVE_INFERENCE"


def test_second_turn_can_hit_cache_with_identical_history(client):
    a1 = client.post("/chat", json={"session_id": "m-1", "message": "hi"}).json()
    wait_for_cache_entries(1)
    client.post("/chat", json={"session_id": "m-1", "message": "next"})
    wait_for_cache_entries(2)
    b1 = client.post("/chat", json={"session_id": "m-2", "message": "hi"}).json()
    assert b1["metadata"]["resolution_source"] == "LLM_CACHE" and b1["reply"] == a1["reply"]
    b2 = client.post("/chat", json={"session_id": "m-2", "message": "next"}).json()
    assert b2["metadata"]["resolution_source"] == "LLM_CACHE"


def test_answer_from_fallback_key_is_shared_by_all_keys(client):
    """Regression: the cache must not be partitioned per key/model group.

    With key_1 down, a cache hit must not spend a provider attempt on key_1 first, and an answer produced
    via key_2 must be reusable once key_1 is healthy again.
    """
    STATE.failures[FAKE_KEYS[0]] = 429
    live = client.post("/chat", json={"session_id": "fb-1", "message": "shared?"}).json()
    assert (live["metadata"]["key_id"], live["metadata"]["fallback_attempts"]) == ("key_2", 1)
    wait_for_cache_entries(1)
    calls_before = len(STATE.calls)
    attempts_before = len(STATE.attempts)

    hit = client.post("/chat", json={"session_id": "fb-2", "message": "shared?"}).json()
    assert hit["metadata"]["resolution_source"] == "LLM_CACHE"
    assert hit["reply"] == live["reply"]
    assert len(STATE.attempts) == attempts_before  # no provider attempt at all, not even a failing key_1

    STATE.failures.clear()
    hit2 = client.post("/chat", json={"session_id": "fb-3", "message": "shared?"}).json()
    assert hit2["metadata"]["resolution_source"] == "LLM_CACHE" and hit2["reply"] == live["reply"]
    assert len(STATE.calls) == calls_before


def test_cache_identity_includes_model(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from tests.conftest import make_settings

    with TestClient(create_app(make_settings(tmp_path / "a"))) as c:
        c.post("/chat", json={"session_id": "m1", "message": "same words"})
        wait_for_cache_entries(1)
    # Same prompt, different model id -> must not reuse the first model's answer.
    with TestClient(create_app(make_settings(tmp_path / "b", LLM_MODEL="mockllm/other-model"))) as c:
        r = c.post("/chat", json={"session_id": "m2", "message": "same words"}).json()
    assert r["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert r["metadata"]["model"] == "mockllm/other-model"
