"""Faster-Whisper speech-to-text. The model loads once and is reused."""
import asyncio
import logging
import threading
import time
from dataclasses import dataclass

import numpy as np

from ..concurrency import StageLimiter
from ..config import Settings
from ..errors import ModelFailure, ModelTimeout, ModelUnavailable, NoSpeech
from ..schemas import ServiceStatus

log = logging.getLogger("voxpilot.stt")


@dataclass
class STTResult:
    text: str
    language: str
    ms: float


class STTService:
    def __init__(self, settings: Settings):
        self.s = settings
        self._model = None
        self._load_lock = threading.Lock()
        self._limiter = StageLimiter(settings.stage_concurrency, settings.queue_timeout_s, "speech-to-text")

    def _load(self):
        with self._load_lock:
            if self._model is not None:
                return self._model
            try:
                from faster_whisper import WhisperModel

                log.info("Loading Whisper '%s' (%s/%s)", self.s.whisper_model,
                         self.s.whisper_device, self.s.whisper_compute_type)
                self._model = WhisperModel(
                    self.s.whisper_model,
                    device=self.s.whisper_device,
                    compute_type=self.s.whisper_compute_type,
                    cpu_threads=self.s.whisper_cpu_threads,
                )
            except Exception as exc:
                log.exception("Whisper load failed")
                hint = ""
                if self.s.whisper_device != "cpu":
                    hint = " For CUDA you need cuBLAS/cuDNN 12 libraries; set WHISPER_DEVICE=cpu to fall back."
                raise ModelUnavailable(
                    f"Could not load Whisper model '{self.s.whisper_model}' "
                    f"({type(exc).__name__}). Check the model name, disk space and network for "
                    f"the first download.{hint}"
                )
            return self._model

    async def warmup(self) -> None:
        await asyncio.to_thread(self._load)

    def _transcribe_sync(self, samples: np.ndarray, language: str) -> tuple[str, str]:
        model = self._load()
        try:
            segments, info = model.transcribe(
                samples,
                language=language,
                beam_size=self.s.whisper_beam_size,
                vad_filter=self.s.whisper_vad_filter,
                condition_on_previous_text=False,
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
        except Exception as exc:
            log.exception("Whisper inference failed")
            raise ModelFailure(f"Speech recognition failed ({type(exc).__name__}).")
        return text, info.language

    async def transcribe(self, samples: np.ndarray, language: str) -> STTResult:
        async with self._limiter.slot():
            start = time.perf_counter()
            try:
                text, lang = await asyncio.wait_for(
                    asyncio.to_thread(self._transcribe_sync, samples, language), self.s.stt_timeout_s
                )
            except asyncio.TimeoutError:
                raise ModelTimeout("Speech recognition timed out.")
            ms = (time.perf_counter() - start) * 1000
        if not text:
            raise NoSpeech("No speech was recognised. Speak closer to the microphone and try again.")
        return STTResult(text=text, language=lang, ms=ms)

    def status(self) -> ServiceStatus:
        return ServiceStatus(
            ready=True,
            loaded=self._model is not None,
            detail=f"faster-whisper '{self.s.whisper_model}' on {self.s.whisper_device}/{self.s.whisper_compute_type}",
        )
