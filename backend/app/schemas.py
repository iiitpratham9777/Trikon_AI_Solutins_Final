from typing import Literal, Optional

from pydantic import BaseModel, Field

Language = Literal["en", "hi"]


class Latency(BaseModel):
    """All values are measured on the server, in milliseconds. None = stage not run."""

    audio_prep_ms: Optional[float] = None
    stt_ms: Optional[float] = None
    llm_ttft_ms: Optional[float] = None
    llm_ms: Optional[float] = None
    tts_ms: Optional[float] = None
    total_ms: Optional[float] = None
    # Whole-clip TTS: first playable audio is available when the response returns.
    time_to_audio_ms: Optional[float] = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: Optional[str] = Field(default=None, max_length=64)
    language: Language = "en"
    speak: bool = False  # also synthesise speech for the reply


class ChatResponse(BaseModel):
    session_id: str
    response: str
    audio_url: Optional[str] = None
    latency: Latency


class TranscribeResponse(BaseModel):
    transcript: str
    language: str
    audio_duration_s: float
    latency: Latency


class VoiceResponse(BaseModel):
    session_id: str
    transcript: str
    response: str
    audio_url: str
    language: Language
    latency: Latency


class ServiceStatus(BaseModel):
    ready: bool
    loaded: bool = False
    detail: str = ""


class ModelsStatus(BaseModel):
    stt: ServiceStatus
    llm: ServiceStatus
    tts: ServiceStatus
    ffmpeg: ServiceStatus
    config: dict


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    sessions: int
