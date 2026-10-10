"""Orchestrates STT -> LLM -> TTS and measures every stage."""
import logging
import time
from typing import Awaitable, Callable, Optional

from .config import Settings
from .errors import AppError
from .schemas import ChatResponse, Latency, ModelsStatus, ServiceStatus, TranscribeResponse, VoiceResponse
from .services.audio_service import AudioService, AudioStore
from .services.conversation_service import ConversationService
from .services.llm_service import LLMService
from .services.stt_service import STTService
from .services.tts_service import TTSService

log = logging.getLogger("voxpilot.pipeline")
DisconnectCheck = Callable[[], Awaitable[bool]]


class ClientDisconnected(AppError):
    status_code, code = 499, "CLIENT_CLOSED"


def _ms(since: float) -> float:
    return (time.perf_counter() - since) * 1000


class Pipeline:
    def __init__(self, settings: Settings, audio: AudioService, stt: STTService, llm: LLMService,
                 tts: TTSService, conversations: ConversationService, store: AudioStore):
        self.settings, self.audio, self.stt, self.llm = settings, audio, stt, llm
        self.tts, self.conversations, self.store = tts, conversations, store

    @staticmethod
    async def _alive(check: Optional[DisconnectCheck]) -> None:
        """Skip remaining (expensive) stages when the browser has already gone away."""
        if check is not None and await check():
            raise ClientDisconnected("Client disconnected.")

    async def transcribe(self, data: bytes, content_type: Optional[str], language: str) -> TranscribeResponse:
        t0 = time.perf_counter()
        lat = Latency()
        decoded = await self.audio.decode(data, content_type)
        lat.audio_prep_ms = _ms(t0)
        result = await self.stt.transcribe(decoded.samples, language)
        lat.stt_ms = result.ms
        lat.total_ms = _ms(t0)
        return TranscribeResponse(transcript=result.text, language=result.language,
                                  audio_duration_s=round(decoded.duration_s, 2), latency=lat)

    async def _converse(self, session_id: Optional[str], text: str, language: str, lat: Latency,
                        alive: Optional[DisconnectCheck]):
        session = self.conversations.get_or_create(session_id)
        async with session.lock:  # same-session requests are answered one at a time, in order
            await self._alive(alive)
            result = await self.llm.chat(self.conversations.history(session), text, language)
            self.conversations.append_turn(session, text, result.text)
        lat.llm_ttft_ms, lat.llm_ms = result.ttft_ms, result.ms
        return session, result.text

    async def _speak(self, text: str, language: str, lat: Latency, alive: Optional[DisconnectCheck]) -> str:
        await self._alive(alive)
        tts = await self.tts.synthesize(text, language)
        lat.tts_ms = tts.ms
        return f"/api/audio/{self.store.put(tts.wav)}"

    async def chat(self, message: str, session_id: Optional[str], language: str, speak: bool,
                   alive: Optional[DisconnectCheck] = None) -> ChatResponse:
        t0 = time.perf_counter()
        lat = Latency()
        session, reply = await self._converse(session_id, message.strip(), language, lat, alive)
        audio_url = await self._speak(reply, language, lat, alive) if speak else None
        lat.total_ms = _ms(t0)
        if speak:
            lat.time_to_audio_ms = lat.total_ms
        return ChatResponse(session_id=session.id, response=reply, audio_url=audio_url, latency=lat)

    async def respond(self, data: bytes, content_type: Optional[str], session_id: Optional[str],
                      language: str, alive: Optional[DisconnectCheck] = None) -> VoiceResponse:
        t0 = time.perf_counter()
        lat = Latency()
        decoded = await self.audio.decode(data, content_type)
        lat.audio_prep_ms = _ms(t0)
        await self._alive(alive)
        stt = await self.stt.transcribe(decoded.samples, language)
        lat.stt_ms = stt.ms
        session, reply = await self._converse(session_id, stt.text, language, lat, alive)
        audio_url = await self._speak(reply, language, lat, alive)
        lat.total_ms = lat.time_to_audio_ms = _ms(t0)
        log.info("voice turn: %s", lat.model_dump(exclude_none=True))
        return VoiceResponse(session_id=session.id, transcript=stt.text, response=reply,
                             audio_url=audio_url, language=language, latency=lat)

    async def models_status(self) -> ModelsStatus:
        ffmpeg = self.audio.find_ffmpeg()
        s = self.settings
        return ModelsStatus(
            stt=self.stt.status(),
            llm=await self.llm.status(),
            tts=self.tts.status(),
            ffmpeg=ServiceStatus(ready=bool(ffmpeg), loaded=bool(ffmpeg), detail=ffmpeg or "ffmpeg not found"),
            config={"whisper_model": s.whisper_model, "whisper_device": s.whisper_device,
                    "whisper_compute_type": s.whisper_compute_type, "llm_model": s.llm_model,
                    "tts_engine": s.tts_engine, "max_history_turns": s.max_history_turns},
        )
