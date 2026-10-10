import io
import re

import httpx
import numpy as np
import pytest
import soundfile as sf

from app.config import Settings
from app.main import create_app
from app.pipeline import Pipeline
from app.schemas import ServiceStatus
from app.services.audio_service import AudioService, AudioStore
from app.services.conversation_service import ConversationService
from app.services.llm_service import LLMResult
from app.services.stt_service import STTResult
from app.services.tts_service import TTSResult


def make_wav(seconds=1.0, amp=0.3, freq=220.0, rate=16000) -> bytes:
    t = np.arange(int(seconds * rate)) / rate
    buf = io.BytesIO()
    sf.write(buf, (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32), rate, format="WAV")
    return buf.getvalue()


class FakeSTT:
    def __init__(self):
        self.text = "my name is Rahul"
        self.error = None
        self.calls = []

    async def transcribe(self, samples, language):
        self.calls.append((len(samples), language))
        if self.error:
            raise self.error
        return STTResult(text=self.text, language=language, ms=12.0)

    def status(self):
        return ServiceStatus(ready=True, loaded=True, detail="fake stt")

    async def warmup(self):
        pass


class FakeLLM:
    """Deterministic stand-in: remembers a name only if it appears in the history it is given."""

    def __init__(self):
        self.error = None
        self.calls = []

    async def chat(self, history, user_text, language):
        self.calls.append({"history": list(history), "text": user_text, "language": language})
        if self.error:
            raise self.error
        m = re.search(r"my name is (\w+)", user_text, re.I)
        if m:
            return LLMResult(f"Nice to meet you, {m.group(1)}.", ttft_ms=5.0, ms=20.0)
        if "what is my name" in user_text.lower():
            for msg in history:
                m = re.search(r"my name is (\w+)", msg["content"], re.I)
                if msg["role"] == "user" and m:
                    return LLMResult(f"Your name is {m.group(1)}.", ttft_ms=5.0, ms=20.0)
            return LLMResult("I don't know your name yet.", ttft_ms=5.0, ms=20.0)
        return LLMResult("Okay.", ttft_ms=5.0, ms=20.0)

    async def status(self):
        return ServiceStatus(ready=True, loaded=True, detail="fake llm")

    async def warmup(self):
        pass

    async def aclose(self):
        pass


class FakeTTS:
    def __init__(self):
        self.error = None
        self.calls = []

    async def synthesize(self, text, language):
        self.calls.append((text, language))
        if self.error:
            raise self.error
        return TTSResult(wav=make_wav(0.5, rate=24000), ms=30.0)

    def status(self):
        return ServiceStatus(ready=True, loaded=True, detail="fake tts")

    async def warmup(self):
        pass


@pytest.fixture
def settings():
    return Settings(warmup_on_start=False, max_history_turns=2, max_upload_mb=1, _env_file=None)


@pytest.fixture
def parts(settings):
    stt, llm, tts = FakeSTT(), FakeLLM(), FakeTTS()
    pipeline = Pipeline(settings, AudioService(settings), stt, llm, tts,
                        ConversationService(settings), AudioStore(settings.audio_store_items))
    return pipeline, stt, llm, tts


@pytest.fixture
async def client(parts):
    pipeline = parts[0]
    app = create_app(pipeline=pipeline, settings=pipeline.settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


def wav_upload(data=None, ctype="audio/wav"):
    return {"audio": ("clip.wav", data if data is not None else make_wav(), ctype)}
