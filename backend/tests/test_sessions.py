from fastapi.testclient import TestClient

from app.main import create_app


def test_history_oldest_first_without_system_prompt(client):
    r1 = client.post("/chat", json={"session_id": "h", "message": "first", "system_prompt": "SYSTEM-SECRET"}).json()
    r2 = client.post("/chat", json={"session_id": "h", "message": "second"}).json()
    r = client.get("/sessions/h/messages")
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "h"
    msgs = body["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert [m["content"] for m in msgs] == ["first", r1["reply"], "second", r2["reply"]]
    assert msgs[0] == {"role": "user", "content": "first"}
    assert msgs[1]["metadata"] == r1["metadata"]
    assert msgs[3]["metadata"]["resolution_source"] in ("LIVE_INFERENCE", "LLM_CACHE")
    assert "SYSTEM-SECRET" not in r.text


def test_unknown_session_404(client):
    r = client.get("/sessions/does-not-exist/messages")
    assert r.status_code == 404
    assert r.json() == {"detail": "session not found"}


def test_history_survives_app_restart(settings):
    with TestClient(create_app(settings)) as c:
        reply = c.post("/chat", json={"session_id": "persist", "message": "remember me"}).json()["reply"]
    with TestClient(create_app(settings)) as c:  # new app instance, same SQLite file
        msgs = c.get("/sessions/persist/messages").json()["messages"]
    assert [m["content"] for m in msgs] == ["remember me", reply]
