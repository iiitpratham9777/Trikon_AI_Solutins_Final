import pytest

from app.config import Settings
from app.errors import BadRequest, SessionNotFound
from app.services.conversation_service import ConversationService


def chat(client, text, sid=None, **kw):
    return client.post("/api/chat", json={"message": text, "session_id": sid, **kw})


async def test_memory_across_turns(client, parts):
    r1 = (await chat(client, "My name is Rahul.")).json()
    sid = r1["session_id"]
    assert "Rahul" in r1["response"]
    r2 = (await chat(client, "What is my name?", sid)).json()
    assert r2["session_id"] == sid and "Rahul" in r2["response"]
    # the LLM really received the earlier turn
    assert parts[2].calls[-1]["history"][0] == {"role": "user", "content": "My name is Rahul."}


async def test_sessions_are_isolated(client):
    a = (await chat(client, "My name is Rahul.")).json()
    b = (await chat(client, "My name is Priya.")).json()
    assert a["session_id"] != b["session_id"]
    ra = (await chat(client, "What is my name?", a["session_id"])).json()
    rb = (await chat(client, "What is my name?", b["session_id"])).json()
    rc = (await chat(client, "What is my name?")).json()  # brand-new session
    assert "Rahul" in ra["response"] and "Priya" not in ra["response"]
    assert "Priya" in rb["response"] and "Rahul" not in rb["response"]
    assert "don't know" in rc["response"]


async def test_history_is_bounded(client, parts):
    sid = (await chat(client, "one")).json()["session_id"]
    for word in ("two", "three", "four", "five"):
        await chat(client, word, sid)
    history = parts[2].calls[-1]["history"]
    assert len(history) == 4  # max_history_turns=2 in test settings -> 2 pairs
    assert history[0]["content"] == "three"


async def test_delete_session_resets_memory(client):
    r = (await chat(client, "My name is Rahul.")).json()
    sid = r["session_id"]
    assert (await client.delete(f"/api/sessions/{sid}")).status_code == 204
    assert (await client.delete(f"/api/sessions/{sid}")).status_code == 404
    again = (await chat(client, "What is my name?", sid)).json()
    assert "don't know" in again["response"]


async def test_failed_llm_turn_is_not_remembered(client, parts):
    from app.errors import ModelFailure
    sid = (await chat(client, "My name is Rahul.")).json()["session_id"]
    parts[2].error = ModelFailure("boom")
    assert (await chat(client, "What is my name?", sid)).status_code == 502
    parts[2].error = None
    await chat(client, "What is my name?", sid)
    users = [m["content"] for m in parts[2].calls[-1]["history"] if m["role"] == "user"]
    assert users == ["My name is Rahul."]


def test_eviction_by_capacity_and_validation():
    svc = ConversationService(Settings(max_sessions=2, _env_file=None))
    ids = [svc.get_or_create(None).id for _ in range(3)]
    assert svc.count() == 2 and ids[0] not in svc._sessions
    with pytest.raises(BadRequest):
        svc.get_or_create("../etc/passwd")
    with pytest.raises(SessionNotFound):
        svc.delete("missing-session-id")
