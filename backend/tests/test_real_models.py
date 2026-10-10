"""Smoke tests against REAL local models. Skipped unless RUN_REAL_MODELS=1.

    RUN_REAL_MODELS=1 pytest -m real -v -s

Requires: `ollama serve` with the configured model pulled, Whisper weights downloadable,
and Kokoro installed (requirements-tts.txt).
"""
import os

import httpx
import pytest

from app.config import Settings
from app.pipeline import Pipeline
from app.services.audio_service import AudioService, AudioStore
from app.services.conversation_service import ConversationService
from app.services.llm_service import LLMService
from app.services.stt_service import STTService
from app.services.tts_service import TTSService

pytestmark = [
    pytest.mark.real,
    pytest.mark.skipif(os.getenv("RUN_REAL_MODELS") != "1", reason="set RUN_REAL_MODELS=1 to run"),
]


@pytest.fixture(scope="module")
def real():
    s = Settings()
    return Pipeline(s, AudioService(s), STTService(s), LLMService(s), TTSService(s),
                    ConversationService(s), AudioStore(5))


async def test_real_tts_then_stt_roundtrip_and_llm_memory(real):
    # 1. TTS makes speech, 2. Whisper transcribes it, 3. Ollama answers with memory.
    tts = await real.tts.synthesize("My name is Rahul. Please remember it.", "en")
    assert tts.wav[:4] == b"RIFF"
    result = await real.respond(tts.wav, "audio/wav", None, "en")
    print("transcript:", result.transcript, "| reply:", result.response, "|", result.latency)
    assert "rahul" in result.transcript.lower()
    follow = await real.chat("What is my name?", result.session_id, "en", speak=False)
    print("memory reply:", follow.response)
    assert "rahul" in follow.response.lower()


async def test_real_hindi_reply(real):
    out = await real.chat("भारत की राजधानी क्या है?", None, "hi", speak=True)
    print(out.response, out.latency)
    assert any("\u0900" <= ch <= "\u097f" for ch in out.response)
    assert out.audio_url
