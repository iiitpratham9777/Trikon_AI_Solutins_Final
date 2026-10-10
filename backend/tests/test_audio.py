import glob
import subprocess
import tempfile
import os

import pytest

from app.config import Settings
from app.errors import EmptyAudio, InvalidAudio, NoSpeech, UnsupportedAudio
from app.services.audio_service import AudioService, AudioStore
from app.errors import AudioNotFound

from .conftest import make_wav, wav_upload


@pytest.fixture
def svc():
    return AudioService(Settings(_env_file=None))


async def test_empty_upload_rejected(client):
    r = await client.post("/api/voice/transcribe", files=wav_upload(b""))
    assert r.status_code == 400 and r.json()["error"]["code"] == "EMPTY_AUDIO"


async def test_oversize_upload_rejected(client):
    r = await client.post("/api/voice/transcribe", files=wav_upload(b"\0" * (1024 * 1024 + 10)))
    assert r.status_code == 413 and r.json()["error"]["code"] == "AUDIO_TOO_LARGE"


async def test_unsupported_type_rejected(client):
    r = await client.post("/api/voice/transcribe", files=wav_upload(make_wav(), "text/plain"))
    assert r.status_code == 415 and r.json()["error"]["code"] == "UNSUPPORTED_AUDIO"


async def test_garbage_audio_is_invalid_not_a_crash(client):
    r = await client.post("/api/voice/transcribe", files=wav_upload(b"this is not audio at all" * 50, "audio/webm"))
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_AUDIO"
    assert "Traceback" not in r.text


async def test_silent_audio_rejected(client):
    r = await client.post("/api/voice/transcribe", files=wav_upload(make_wav(1.0, amp=0.0)))
    assert r.status_code == 422 and r.json()["error"]["code"] == "NO_SPEECH"


async def test_too_short_audio_rejected(client):
    r = await client.post("/api/voice/transcribe", files=wav_upload(make_wav(0.1)))
    assert r.status_code == 422 and r.json()["error"]["code"] == "NO_SPEECH"


async def test_decode_wav_is_16k_mono_float(svc):
    d = await svc.decode(make_wav(1.0, rate=44100), "audio/wav")
    assert d.samples.dtype.name == "float32" and d.samples.ndim == 1
    assert abs(d.duration_s - 1.0) < 0.05 and d.rms > 0.1


def _encode(fmt_args, suffix):
    ffmpeg = AudioService(Settings(_env_file=None)).find_ffmpeg()
    out = tempfile.mktemp(suffix=suffix)
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=300:duration=1", *fmt_args, out]
    if subprocess.run(cmd, capture_output=True).returncode != 0:
        pytest.skip(f"this ffmpeg build cannot encode {suffix}")
    with open(out, "rb") as fh:
        data = fh.read()
    os.remove(out)
    return data


@pytest.mark.parametrize("args,suffix,ctype", [
    (["-c:a", "libopus"], ".webm", "audio/webm;codecs=opus"),   # Chrome / Edge / Firefox
    (["-c:a", "libopus"], ".ogg", "audio/ogg;codecs=opus"),     # Firefox
    (["-c:a", "aac"], ".mp4", "audio/mp4"),                      # Safari
    (["-c:a", "libmp3lame"], ".mp3", "audio/mpeg"),
])
async def test_decode_real_container_formats(svc, args, suffix, ctype):
    d = await svc.decode(_encode(args, suffix), ctype)
    assert 0.8 < d.duration_s < 1.3 and d.rms > 0.05


async def test_temp_files_are_cleaned_up(svc):
    before = set(glob.glob(os.path.join(tempfile.gettempdir(), "voxpilot_*")))
    await svc.decode(make_wav(), "audio/wav")
    with pytest.raises(InvalidAudio):
        await svc.decode(b"garbage" * 100, "audio/webm")
    after = set(glob.glob(os.path.join(tempfile.gettempdir(), "voxpilot_*")))
    assert after == before


def test_validate_errors(svc):
    with pytest.raises(EmptyAudio):
        svc.validate_upload(b"", "audio/wav")
    with pytest.raises(UnsupportedAudio):
        svc.validate_upload(b"x", None)


def test_audio_store_is_bounded():
    store = AudioStore(2)
    ids = [store.put(bytes([i])) for i in range(3)]
    with pytest.raises(AudioNotFound):
        store.get(ids[0])
    assert store.get(ids[2]) == bytes([2])
