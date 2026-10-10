from .conftest import wav_upload


async def test_health(client):
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "sessions": 0}


async def test_models_status(client):
    r = await client.get("/api/models/status")
    body = r.json()
    assert r.status_code == 200
    assert body["stt"]["ready"] and body["llm"]["ready"] and body["tts"]["ready"]
    assert body["ffmpeg"]["ready"], "ffmpeg (or imageio-ffmpeg) must be available"
    assert "llm_model" in body["config"]


async def test_chat_validation(client):
    assert (await client.post("/api/chat", json={"message": ""})).status_code == 422
    assert (await client.post("/api/chat", json={"message": "   "})).status_code == 400
    assert (await client.post("/api/chat", json={"message": "hi", "language": "fr"})).status_code == 422
    assert (await client.post("/api/chat", json={"message": "x" * 2001})).status_code == 422
    r = await client.post("/api/chat", json={"message": "hi", "session_id": "bad id!"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "BAD_REQUEST"


async def test_missing_audio_field_is_validation_error(client):
    r = await client.post("/api/voice/respond", data={"language": "en"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_bad_language_on_voice_endpoint(client):
    r = await client.post("/api/voice/respond", files=wav_upload(), data={"language": "xx"})
    assert r.status_code == 422


async def test_audio_endpoint_unknown_id(client):
    assert (await client.get("/api/audio/" + "0" * 32)).status_code == 404
    assert (await client.get("/api/audio/not-an-id")).status_code == 404
