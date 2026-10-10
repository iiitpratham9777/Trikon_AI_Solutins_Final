"""Pre-download the speech models so the first request is not a multi-minute download.

Run from the backend folder's environment:
    python scripts/download_models.py [--pull-llm]
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import Settings  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pull-llm", action="store_true", help="also run `ollama pull <LLM_MODEL>`")
    args = ap.parse_args()
    s = Settings(_env_file=Path(__file__).resolve().parents[1] / "backend" / ".env")
    failed = False

    print(f"[1/3] Faster-Whisper '{s.whisper_model}' ({s.whisper_device}/{s.whisper_compute_type}) ...")
    try:
        from faster_whisper import WhisperModel

        WhisperModel(s.whisper_model, device=s.whisper_device, compute_type=s.whisper_compute_type)
        print("      ok")
    except Exception as exc:
        failed = True
        print(f"      FAILED: {type(exc).__name__}: {exc}")

    print("[2/3] Kokoro TTS (English + Hindi voices) ...")
    if s.tts_engine != "kokoro":
        print("      skipped (TTS_ENGINE is not kokoro)")
    else:
        try:
            import asyncio

            from app.services.tts_service import TTSService

            tts = TTSService(s)
            for lang in ("en", "hi"):
                asyncio.run(tts.synthesize("Hello." if lang == "en" else "नमस्ते।", lang))
                print(f"      {lang}: ok")
        except Exception as exc:
            failed = True
            print(f"      FAILED: {getattr(exc, 'message', exc)}")

    print(f"[3/3] Ollama model '{s.llm_model}' ...")
    if args.pull_llm:
        failed |= subprocess.call(["ollama", "pull", s.llm_model]) != 0
    else:
        print(f"      run: ollama pull {s.llm_model}   (or re-run with --pull-llm)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
