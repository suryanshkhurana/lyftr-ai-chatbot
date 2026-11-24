import json

import pytest

from tests.conftest import MODEL, STATE, message_rows, session_rows

METADATA_FIELDS = {
    "resolution_source",
    "model",
    "latency_ms",
    "input_tokens",
    "output_tokens",
    "key_id",
    "fallback_attempts",
}


def test_first_turn_contract_and_persistence(client, settings):
    r = client.post("/chat", json={"session_id": "s-7f3a", "message": "  What is the capital of France?  "})
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"session_id", "reply", "metadata"}
    assert body["session_id"] == "s-7f3a"
    assert isinstance(body["reply"], str) and body["reply"]
    meta = body["metadata"]
    assert set(meta) == METADATA_FIELDS
    assert meta["resolution_source"] == "LIVE_INFERENCE"
    assert meta["model"] == MODEL
    assert isinstance(meta["latency_ms"], int) and meta["latency_ms"] > 0
    assert isinstance(meta["input_tokens"], int) and meta["input_tokens"] > 0
    assert isinstance(meta["output_tokens"], int) and meta["output_tokens"] > 0
    assert meta["key_id"] == "key_1"
    assert meta["fallback_attempts"] == 0

    rows = message_rows(settings)
    assert [(r[0], r[1], r[2]) for r in rows] == [
        ("s-7f3a", "user", "What is the capital of France?"),
        ("s-7f3a", "assistant", body["reply"]),
    ]
    assert rows[0][3] is None
    assert json.loads(rows[1][3]) == meta


def test_tokens_match_provider_usage_per_request(client):
    r1 = client.post("/chat", json={"session_id": "a", "message": "one two three"}).json()
    # Mock usage: sum(words + 4) over messages; completion = words in reply.
    sent = STATE.calls[-1]["messages"]
    assert r1["metadata"]["input_tokens"] == sum(len(m["content"].split()) + 4 for m in sent)
    assert r1["metadata"]["output_tokens"] == len(r1["reply"].split())
    r2 = client.post("/chat", json={"session_id": "a", "message": "four"}).json()
    sent2 = STATE.calls[-1]["messages"]
    # Second request counts system + full history + new message — once, not a running total.
    assert r2["metadata"]["input_tokens"] == sum(len(m["content"].split()) + 4 for m in sent2)


def test_equal_length_first_messages_have_equal_input_tokens(client):
    a = client.post("/chat", json={"session_id": "x1", "message": "alpha beta"}).json()
    b = client.post("/chat", json={"session_id": "x2", "message": "gamma delta"}).json()
    assert a["metadata"]["input_tokens"] == b["metadata"]["input_tokens"]


def test_multi_turn_context_is_built_server_side(client):
    first = client.post("/chat", json={"session_id": "mt", "message": "My name is Ada."}).json()
    client.post("/chat", json={"session_id": "mt", "message": "What is my name?"})
    sent = STATE.calls[-1]["messages"]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]
    assert sent[1]["content"] == "My name is Ada."
    assert sent[2]["content"] == first["reply"]
    assert sent[3]["content"] == "What is my name?"


def test_session_isolation(client):
    client.post("/chat", json={"session_id": "iso-a", "message": "secret A"})
    client.post("/chat", json={"session_id": "iso-b", "message": "hello B"})
    sent = STATE.calls[-1]["messages"]
    assert [m["role"] for m in sent] == ["system", "user"]
    assert all("secret A" not in m["content"] for m in sent)


def test_session_id_not_sent_to_llm(client):
    client.post("/chat", json={"session_id": "unique-session-xyz", "message": "hi"})
    assert all("unique-session-xyz" not in m["content"] for m in STATE.calls[-1]["messages"])


def test_system_prompt_override_persists_for_session(client, settings):
    client.post("/chat", json={"session_id": "sp", "message": "hi", "system_prompt": "Talk like a pirate."})
    assert STATE.calls[-1]["messages"][0] == {"role": "system", "content": "Talk like a pirate."}
    client.post("/chat", json={"session_id": "sp", "message": "again"})
    assert STATE.calls[-1]["messages"][0]["content"] == "Talk like a pirate."
    client.post("/chat", json={"session_id": "sp", "message": "third", "system_prompt": "Be formal."})
    assert STATE.calls[-1]["messages"][0]["content"] == "Be formal."
    # Other sessions keep the default prompt.
    client.post("/chat", json={"session_id": "other", "message": "hi"})
    assert STATE.calls[-1]["messages"][0]["content"] == settings.default_system_prompt
    assert ("sp", "Be formal.") in session_rows(settings)


@pytest.mark.parametrize(
    "payload",
    [
        {"message": "hi"},
        {"session_id": "s1"},
        {"session_id": "", "message": "hi"},
        {"session_id": "   ", "message": "hi"},
        {"session_id": "s1", "message": ""},
        {"session_id": "s1", "message": "    \n  "},
        {"session_id": "s1", "message": "x" * 4001},
        {"session_id": "s" * 129, "message": "hi"},
        {"session_id": 123, "message": "hi"},
        {"session_id": "s1", "message": None},
    ],
)
def test_validation_errors_are_422_json_and_not_saved(client, settings, payload):
    r = client.post("/chat", json=payload)
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/json")
    assert "detail" in r.json()
    assert message_rows(settings) == []
    assert session_rows(settings) == []
    assert STATE.calls == []


def test_message_length_limits_after_trim(client):
    ok = client.post("/chat", json={"session_id": "len", "message": "  " + "x" * 4000 + "  "})
    assert ok.status_code == 200
    ok128 = client.post("/chat", json={"session_id": "s" * 128, "message": "hi"})
    assert ok128.status_code == 200


def test_malformed_json_is_422(client, settings):
    r = client.post("/chat", content=b'{"session_id": "s1", "message": ', headers={"Content-Type": "application/json"})
    assert r.status_code == 422
    assert "detail" in r.json()
    r = client.post("/chat", content=b"[1,2,3]", headers={"Content-Type": "application/json"})
    assert r.status_code == 422
    assert message_rows(settings) == []


def test_empty_provider_reply_is_not_returned_as_success(client, settings):
    STATE.reply_override = ""
    r = client.post("/chat", json={"session_id": "e", "message": "hi"})
    assert r.status_code == 503
    assert r.json() == {"detail": "all providers unavailable"}
    assert message_rows(settings) == []


def test_unknown_route_and_method_are_json(client):
    r = client.get("/nope")
    assert r.status_code == 404 and "detail" in r.json()
    r = client.get("/chat")
    assert r.status_code == 405 and "detail" in r.json()
