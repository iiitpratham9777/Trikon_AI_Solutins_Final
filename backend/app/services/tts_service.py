"""Text-to-speech with Kokoro (default) or Piper. Returns 16-bit PCM WAV bytes."""
import asyncio
import importlib.util
import io
import logging
import os
import re
import shlex
import tempfile
import threading
import time
from dataclasses import dataclass

import numpy as np
import soundfile as sf

from ..concurrency import StageLimiter
from ..config import Settings
from ..errors import BadRequest, ModelFailure, ModelTimeout, ModelUnavailable
from ..schemas import ServiceStatus

log = logging.getLogger("voxpilot.tts")

KOKORO_SAMPLE_RATE = 24000
_KOKORO_LANG = {"en": "a", "hi": "h"}  # a = American English, h = Hindi
_MD_RE = re.compile(r"[*_`#>~|]+")
_EMOJI_RE = re.compile("[\U00010000-\U0010ffff\u2600-\u27bf\ufe0f]")


def clean_for_speech(text: str, max_chars: int) -> str:
    text = _EMOJI_RE.sub("", _MD_RE.sub("", text))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        cut = text[:max_chars]
        # prefer ending on a sentence boundary (ASCII or Devanagari danda)
        idx = max(cut.rfind("."), cut.rfind("?"), cut.rfind("!"), cut.rfind("\u0964"))
        text = cut[: idx + 1] if idx > max_chars // 2 else cut
    return text


@dataclass
class TTSResult:
    wav: bytes
    ms: float


def _wav_bytes(samples: np.ndarray, rate: int) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, samples, rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


class TTSService:
    def __init__(self, settings: Settings):
        self.s = settings
        self._pipelines: dict = {}
        self._lock = threading.Lock()
        self._limiter = StageLimiter(settings.stage_concurrency, settings.queue_timeout_s, "text-to-speech")

    # ---------- Kokoro ----------
    def _kokoro_pipeline(self, language: str):
        code = _KOKORO_LANG[language]
        with self._lock:
            if code in self._pipelines:
                return self._pipelines[code]
            try:
                from kokoro import KPipeline

                shared = next(iter(self._pipelines.values()), None)
                model = getattr(shared, "model", True) if shared is not None else True
                log.info("Loading Kokoro pipeline '%s' on %s", code, self.s.tts_device)
                pipe = KPipeline(lang_code=code, model=model, device=self.s.tts_device)
            except ImportError:
                raise ModelUnavailable(
                    "Kokoro is not installed. Run `pip install -r requirements-tts.txt` "
                    "(see README) or set TTS_ENGINE=piper."
                )
            except Exception as exc:
                log.exception("Kokoro load failed")
                raise ModelUnavailable(
                    f"Could not load Kokoro ({type(exc).__name__}). For Hindi, espeak-ng must be installed."
                )
            self._pipelines[code] = pipe
            return pipe

    def _kokoro_sync(self, text: str, language: str) -> bytes:
        pipe = self._kokoro_pipeline(language)
        voice = self.s.kokoro_voice_hi if language == "hi" else self.s.kokoro_voice_en
        try:
            chunks = []
            for _, _, audio in pipe(text, voice=voice, speed=self.s.kokoro_speed):
                if audio is None:
                    continue
                arr = audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio)
                chunks.append(arr.astype(np.float32))
        except Exception as exc:
            log.exception("Kokoro inference failed")
            raise ModelFailure(f"Speech synthesis failed ({type(exc).__name__}).")
        if not chunks:
            raise ModelFailure("Speech synthesis produced no audio.")
        return _wav_bytes(np.concatenate(chunks), KOKORO_SAMPLE_RATE)

    # ---------- Piper ----------
    async def _piper(self, text: str, language: str) -> bytes:
        model = self.s.piper_model_hi if language == "hi" else self.s.piper_model_en
        if not model or not os.path.exists(model):
            raise ModelUnavailable(
                f"No Piper voice configured for '{language}'. Set PIPER_MODEL_{language.upper()} to a .onnx file."
            )
        fd, out_path = tempfile.mkstemp(suffix=".wav", prefix="voxpilot_tts_")
        os.close(fd)
        try:
            cmd = shlex.split(self.s.piper_executable, posix=os.name != "nt") + [
                "--model", model, "--output_file", out_path,
            ]
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd, stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
                )
            except OSError:
                raise ModelUnavailable("Piper could not be started. Check PIPER_EXECUTABLE.")
            try:
                _, err = await proc.communicate(text.encode("utf-8"))
            except asyncio.CancelledError:
                proc.kill()
                raise
            if proc.returncode != 0:
                log.error("piper failed: %s", err.decode("utf-8", "ignore")[:300])
                raise ModelFailure("Speech synthesis failed.")
            with open(out_path, "rb") as fh:
                data = fh.read()
            if len(data) < 100:
                raise ModelFailure("Speech synthesis produced no audio.")
            return data
        finally:
            try:
                os.remove(out_path)
            except OSError:
                pass

    # ---------- public ----------
    async def synthesize(self, text: str, language: str) -> TTSResult:
        text = clean_for_speech(text, self.s.tts_max_chars)
        if not text:
            raise BadRequest("There is no speakable text in the reply.")
        async with self._limiter.slot():
            start = time.perf_counter()
            try:
                if self.s.tts_engine == "piper":
                    wav = await asyncio.wait_for(self._piper(text, language), self.s.tts_timeout_s)
                else:
                    wav = await asyncio.wait_for(
                        asyncio.to_thread(self._kokoro_sync, text, language), self.s.tts_timeout_s
                    )
            except asyncio.TimeoutError:
                raise ModelTimeout("Speech synthesis timed out.")
            return TTSResult(wav=wav, ms=(time.perf_counter() - start) * 1000)

    async def warmup(self) -> None:
        if self.s.tts_engine == "kokoro":
            await asyncio.to_thread(self._kokoro_pipeline, "en")

    def status(self) -> ServiceStatus:
        if self.s.tts_engine == "kokoro":
            has = importlib.util.find_spec("kokoro") is not None
            return ServiceStatus(
                ready=has,
                loaded=bool(self._pipelines),
                detail=f"kokoro on {self.s.tts_device}" if has else "kokoro not installed (requirements-tts.txt)",
            )
        configured = bool(self.s.piper_model_en and os.path.exists(self.s.piper_model_en))
        return ServiceStatus(
            ready=configured, loaded=False,
            detail="piper" if configured else "PIPER_MODEL_EN not set or file missing",
        )
