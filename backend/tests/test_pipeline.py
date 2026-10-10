import asyncio

from app.errors import ModelFailure, ModelUnavailable, NoSpeech
from app.pipeline import ClientDisconnected

from .conftest import make_wav, wav_upload


async def test_full_voice_pipeline(client, parts):
    r = await client.post("/api/voice/respond", files=wav_upload(), data={"language": "en"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["transcript"] == "my name is Rahul"
    assert "Rahul" in body["response"] and body["session_id"] and body["language"] == "en"
    lat = body["latency"]
    for key in ("audio_prep_ms", "stt_ms", "llm_ms", "llm_ttft_ms", "tts_ms", "total_ms", "time_to_audio_ms"):
        assert lat[key] is not None and lat[key] >= 0, key
    assert lat["total_ms"] >= lat["tts_ms"]
    audio = await client.get(body["audio_url"])
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/wav"
    assert audio.content[:4] == b"RIFF" and audio.content[8:12] == b"WAVE"
    assert parts[1].calls[0][1] == "en" and parts[3].calls[0][1] == "en"


async def test_voice_turns_share_session_memory(client, parts):
    parts[1].text = "my name is Rahul"
    sid = (await client.post("/api/voice/respond", files=wav_upload())).json()["session_id"]
    parts[1].text = "what is my name"
    r = await client.post("/api/voice/respond", files=wav_upload(), data={"session_id": sid})
    assert "Rahul" in r.json()["response"]


async def test_hindi_language_is_propagated(client, parts):
    r = await client.post("/api/chat", json={"message": "नमस्ते", "language": "hi", "speak": True})
    assert r.status_code == 200
    assert parts[2].calls[-1]["language"] == "hi" and parts[3].calls[-1][1] == "hi"
    assert r.json()["audio_url"].startswith("/api/audio/")


async def test_chat_without_speak_skips_tts(client, parts):
    r = await client.post("/api/chat", json={"message": "hello"})
    assert r.json()["audio_url"] is None and r.json()["latency"]["tts_ms"] is None
    assert parts[3].calls == []


async def test_transcribe_endpoint(client):
    r = await client.post("/api/voice/transcribe", files=wav_upload(), data={"language": "hi"})
    body = r.json()
    assert r.status_code == 200 and body["transcript"] and body["audio_duration_s"] > 0.9


async def test_stt_failure_returns_error_and_skips_llm(client, parts):
    parts[1].error = NoSpeech("No speech was recognised.")
    r = await client.post("/api/voice/respond", files=wav_upload())
    assert r.status_code == 422 and r.json()["error"]["code"] == "NO_SPEECH"
    assert parts[2].calls == []


async def test_llm_failure_is_an_error_not_a_fake_answer(client, parts):
    parts[2].error = ModelUnavailable("Ollama is not reachable.")
    r = await client.post("/api/voice/respond", files=wav_upload())
    assert r.status_code == 503
    assert "response" not in r.json() and r.json()["error"]["code"] == "MODEL_UNAVAILABLE"
    assert parts[3].calls == []


async def test_tts_failure_is_an_error(client, parts):
    parts[3].error = ModelFailure("Speech synthesis failed.")
    r = await client.post("/api/voice/respond", files=wav_upload())
    assert r.status_code == 502 and r.json()["error"]["code"] == "MODEL_FAILURE"


async def test_unexpected_exception_hides_details(parts):
    import httpx
    from app.main import create_app

    pipeline, _, llm, _ = parts
    llm.error = RuntimeError("secret internal path /srv/x")
    app = create_app(pipeline=pipeline, settings=pipeline.settings)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/chat", json={"message": "hi"})
    assert r.status_code == 500 and "secret" not in r.text and "Traceback" not in r.text


async def test_disconnected_client_skips_model_work(parts):
    pipeline, stt, llm, tts = parts

    async def gone():
        return True

    try:
        await pipeline.respond(make_wav(), "audio/wav", None, "en", alive=gone)
        raise AssertionError("expected ClientDisconnected")
    except ClientDisconnected:
        pass
    assert stt.calls == [] and llm.calls == [] and tts.calls == []


async def test_same_session_requests_are_serialised(parts):
    pipeline, _, llm, _ = parts
    session = pipeline.conversations.get_or_create(None)
    order = []
    orig = llm.chat

    async def slow_chat(history, text, language):
        order.append(("start", text))
        await asyncio.sleep(0.05)
        res = await orig(history, text, language)
        order.append(("end", text))
        return res

    llm.chat = slow_chat
    await asyncio.gather(
        pipeline.chat("first", session.id, "en", False),
        pipeline.chat("second", session.id, "en", False),
    )
    assert [o[0] for o in order] == ["start", "end", "start", "end"]
