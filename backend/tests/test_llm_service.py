import json

import httpx
import pytest

from app.config import Settings
from app.errors import ModelFailure, ModelTimeout, ModelUnavailable
from app.services.llm_service import LLMService, SYSTEM_PROMPTS
from app.services.tts_service import TTSService, clean_for_speech


def ndjson(*objs) -> bytes:
    return ("\n".join(json.dumps(o) for o in objs) + "\n").encode()


def svc_with(handler):
    s = Settings(_env_file=None, llm_model="qwen2.5:3b")
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://ollama.test")
    return LLMService(s, client)


async def test_streamed_reply_is_joined_and_ttft_measured():
    seen = {}

    def handler(req: httpx.Request):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, content=ndjson(
            {"message": {"role": "assistant", "content": ""}, "done": False},
            {"message": {"role": "assistant", "content": "Hello"}, "done": False},
            {"message": {"role": "assistant", "content": " there."}, "done": False},
            {"message": {"role": "assistant", "content": ""}, "done": True},
        ))

    res = await svc_with(handler).chat([{"role": "user", "content": "hi"}], "again", "en")
    assert res.text == "Hello there." and res.ttft_ms is not None and res.ms >= res.ttft_ms
    msgs = seen["body"]["messages"]
    assert msgs[0] == {"role": "system", "content": SYSTEM_PROMPTS["en"]}
    assert [m["content"] for m in msgs[1:]] == ["hi", "again"]
    assert seen["body"]["options"]["num_ctx"] == 2048 and seen["body"]["stream"] is True


async def test_hindi_uses_hindi_system_prompt():
    seen = {}

    def handler(req):
        seen["sys"] = json.loads(req.content)["messages"][0]["content"]
        return httpx.Response(200, content=ndjson({"message": {"content": "ठीक है"}, "done": True}))

    await svc_with(handler).chat([], "नमस्ते", "hi")
    assert "Devanagari" in seen["sys"]


async def test_model_not_pulled():
    with pytest.raises(ModelUnavailable) as e:
        await svc_with(lambda r: httpx.Response(404, json={"error": "model not found"})).chat([], "hi", "en")
    assert "ollama pull qwen2.5:3b" in e.value.message


async def test_ollama_down():
    def handler(req):
        raise httpx.ConnectError("refused")

    with pytest.raises(ModelUnavailable) as e:
        await svc_with(handler).chat([], "hi", "en")
    assert "ollama serve" in e.value.message


async def test_timeout():
    def handler(req):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(ModelTimeout):
        await svc_with(handler).chat([], "hi", "en")


async def test_stream_error_line_and_empty_reply_are_failures():
    with pytest.raises(ModelFailure):
        await svc_with(lambda r: httpx.Response(200, content=ndjson({"error": "out of memory"}))).chat([], "hi", "en")
    with pytest.raises(ModelFailure):
        await svc_with(lambda r: httpx.Response(200, content=ndjson({"message": {"content": ""}, "done": True}))).chat([], "hi", "en")


async def test_status_reports_missing_model():
    ok = svc_with(lambda r: httpx.Response(200, json={"models": [{"name": "qwen2.5:3b"}]}))
    assert (await ok.status()).ready is True
    missing = svc_with(lambda r: httpx.Response(200, json={"models": [{"name": "llama3:8b"}]}))
    st = await missing.status()
    assert st.ready is False and "ollama pull" in st.detail


def test_clean_for_speech_strips_markdown_emoji_and_truncates():
    assert clean_for_speech("**Hi** `there` 😀 #1", 100) == "Hi there 1"
    out = clean_for_speech("First sentence. " + "word " * 100, 20)
    assert out == "First sentence."
    assert clean_for_speech("नमस्ते। " * 50, 30).endswith("।")


async def test_kokoro_missing_is_a_clear_error():
    import importlib.util
    if importlib.util.find_spec("kokoro"):
        pytest.skip("kokoro is installed")
    with pytest.raises(ModelUnavailable) as e:
        await TTSService(Settings(_env_file=None)).synthesize("hello", "en")
    assert "requirements-tts" in e.value.message


async def test_piper_without_voice_is_a_clear_error():
    with pytest.raises(ModelUnavailable):
        await TTSService(Settings(_env_file=None, tts_engine="piper")).synthesize("hello", "en")
