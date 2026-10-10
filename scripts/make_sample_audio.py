"""Create a spoken sample WAV with the project's own TTS, for benchmarking.

    python scripts/make_sample_audio.py --text "What is the capital of India?" --out sample_en.wav
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import Settings  # noqa: E402
from app.services.tts_service import TTSService  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default="What is the capital of India, and why was it chosen?")
    ap.add_argument("--language", choices=["en", "hi"], default="en")
    ap.add_argument("--out", default="sample.wav")
    args = ap.parse_args()
    s = Settings(_env_file=Path(__file__).resolve().parents[1] / "backend" / ".env")
    res = await TTSService(s).synthesize(args.text, args.language)
    Path(args.out).write_bytes(res.wav)
    print(f"wrote {args.out} ({len(res.wav)} bytes, synthesised in {res.ms:.0f} ms)")


asyncio.run(main())
