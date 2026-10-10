"""Upload validation, ffmpeg decoding to 16 kHz mono float32, and the in-memory reply store."""
import asyncio
import logging
import os
import shutil
import tempfile
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

import numpy as np

from ..config import Settings
from ..errors import (
    AudioNotFound,
    AudioTooLarge,
    EmptyAudio,
    InvalidAudio,
    ModelUnavailable,
    NoSpeech,
    UnsupportedAudio,
)

log = logging.getLogger("voxpilot.audio")

SAMPLE_RATE = 16000
# Types MediaRecorder produces: Chromium/Firefox -> webm/ogg (Opus), Safari -> mp4. Plus WAV/MP3.
ALLOWED_TYPES = {
    "audio/webm", "audio/ogg", "audio/mp4", "audio/x-m4a", "audio/aac",
    "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/wave", "video/webm",
}
_SUFFIX = {
    "audio/webm": ".webm", "video/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".mp4",
    "audio/x-m4a": ".m4a", "audio/aac": ".aac", "audio/mpeg": ".mp3", "audio/mp3": ".mp3",
    "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/wave": ".wav",
}


@dataclass
class DecodedAudio:
    samples: np.ndarray  # float32, mono, 16 kHz
    duration_s: float
    rms: float


class AudioService:
    def __init__(self, settings: Settings):
        self.s = settings

    # ---------- ffmpeg discovery ----------
    def find_ffmpeg(self) -> Optional[str]:
        if self.s.ffmpeg_path:
            return self.s.ffmpeg_path if os.path.exists(self.s.ffmpeg_path) else None
        found = shutil.which("ffmpeg")
        if found:
            return found
        try:  # bundled binary from the imageio-ffmpeg wheel (handy on Windows)
            import imageio_ffmpeg

            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return None

    # ---------- validation ----------
    def validate_upload(self, data: bytes, content_type: Optional[str]) -> str:
        """Returns the temp-file suffix to use. Raises a typed AppError on bad input."""
        if not data:
            raise EmptyAudio("The audio upload is empty.")
        if len(data) > self.s.max_upload_mb * 1024 * 1024:
            raise AudioTooLarge(f"Audio is larger than {self.s.max_upload_mb} MB.")
        base = (content_type or "").split(";")[0].strip().lower()
        if base not in ALLOWED_TYPES:
            raise UnsupportedAudio(
                f"Unsupported audio type '{base or 'unknown'}'. Use webm, ogg, mp4, mp3 or wav."
            )
        return _SUFFIX.get(base, ".bin")

    # ---------- decoding ----------
    async def decode(self, data: bytes, content_type: Optional[str]) -> DecodedAudio:
        suffix = self.validate_upload(data, content_type)
        ffmpeg = self.find_ffmpeg()
        if not ffmpeg:
            raise ModelUnavailable(
                "ffmpeg was not found. Install ffmpeg or `pip install imageio-ffmpeg`, "
                "or set FFMPEG_PATH."
            )
        fd, path = tempfile.mkstemp(suffix=suffix, prefix="voxpilot_")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            raw = await self._run_ffmpeg(ffmpeg, path)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

        if len(raw) < 4:
            raise InvalidAudio("No audio could be decoded from the upload.")
        samples = np.frombuffer(raw[: len(raw) // 4 * 4], dtype=np.float32).copy()
        duration = len(samples) / SAMPLE_RATE
        if duration > self.s.max_audio_seconds:
            raise InvalidAudio(f"Audio is longer than {self.s.max_audio_seconds:.0f} seconds.")
        if duration < self.s.min_audio_seconds:
            raise NoSpeech("The recording is too short. Hold the button a little longer.")
        rms = float(np.sqrt(np.mean(np.square(samples))))
        if rms < self.s.silence_rms_threshold:
            raise NoSpeech("No speech detected - the recording is silent.")
        return DecodedAudio(samples=samples, duration_s=duration, rms=rms)

    async def _run_ffmpeg(self, ffmpeg: str, path: str) -> bytes:
        cmd = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
            "-i", path, "-vn", "-t", str(self.s.max_audio_seconds + 1),
            "-f", "f32le", "-ac", "1", "-ar", str(SAMPLE_RATE), "pipe:1",
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
        except OSError as exc:
            log.error("ffmpeg could not start: %s", exc)
            raise ModelUnavailable("ffmpeg could not be started. Check FFMPEG_PATH.")
        try:
            out, err = await asyncio.wait_for(proc.communicate(), self.s.ffmpeg_timeout_s)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise InvalidAudio("Audio decoding timed out.")
        if proc.returncode != 0:
            log.warning("ffmpeg failed: %s", err.decode("utf-8", "ignore")[:300])
            raise InvalidAudio("The audio could not be decoded. Try recording again.")
        return out


class AudioStore:
    """Holds the most recent synthesised replies in memory (no temp files to leak)."""

    def __init__(self, max_items: int):
        self._items: "OrderedDict[str, bytes]" = OrderedDict()
        self._max = max(1, max_items)

    def put(self, wav: bytes) -> str:
        audio_id = uuid.uuid4().hex
        self._items[audio_id] = wav
        while len(self._items) > self._max:
            self._items.popitem(last=False)
        return audio_id

    def get(self, audio_id: str) -> bytes:
        data = self._items.get(audio_id)
        if data is None:
            raise AudioNotFound("That audio is no longer available.")
        return data
