# Performance measurement

**Status: no real-model benchmark has been recorded yet.** The development sandbox that built this project had no GPU and could not download Whisper/Kokoro weights or run Ollama, so every table below is an empty template. Run the commands on your machine and paste the real output. Numbers must never be edited by hand.

## What is measured

All timings come from `time.perf_counter()` on the server and are returned in every response (`latency`):

| Field | Meaning |
|---|---|
| `audio_prep_ms` | validation + temp file + ffmpeg decode to 16 kHz mono |
| `stt_ms` | Faster-Whisper inference (includes waiting for the model slot, not the load) |
| `llm_ttft_ms` | request sent to Ollama -> first non-empty token |
| `llm_ms` | full LLM generation |
| `tts_ms` | speech synthesis of the whole reply |
| `total_ms` | server time for the entire turn |
| `time_to_audio_ms` | when the first playable audio exists on the server (= `total_ms`, whole-clip TTS) |
| `client_ms` (benchmark only) | upload + server + response download, seen by the client |

The browser also shows round-trip time and "until audio started" (request sent -> `playing` event).

## Method

1. Create a speech sample with the project's own TTS (or record your own, 3-6 seconds):
   ```powershell
   cd backend
   .\.venv\Scripts\python.exe ..\scripts\make_sample_audio.py --text "What is the capital of India, and why was it chosen?" --out sample_en.wav
   ```
2. **Cold start**: set `WARMUP_ON_START=false`, restart the backend, then immediately run the benchmark. Run 1 is reported as the first request.
3. **Warm**: runs 2..N of the same process.
4. Record the hardware, the `config` block printed by the script, and the driver/CUDA versions.
5. Compare configurations by changing one setting at a time in `backend/.env`, restarting, and re-running with a different `--label`:
   ```powershell
   python ..\scripts\benchmark.py --audio sample_en.wav --runs 8 --label baseline --out ..\docs\benchmark-baseline.json
   ```
   Suggested comparisons: `WHISPER_MODEL` (base vs small), `WHISPER_BEAM_SIZE` (5 vs 1), `WHISPER_DEVICE` (cpu vs cuda), `LLM_MAX_TOKENS`, `LLM_NUM_CTX`, `WARMUP_ON_START`.

## Results (fill in)

Machine: _CPU / RAM / GPU / driver / OS_
Date: _YYYY-MM-DD_

### Baseline (first working configuration)

| stage | first request (cold) ms | warm median ms | warm min ms | warm max ms |
|---|---:|---:|---:|---:|
| audio_prep_ms | - | - | - | - |
| stt_ms | - | - | - | - |
| llm_ttft_ms | - | - | - | - |
| llm_ms | - | - | - | - |
| tts_ms | - | - | - | - |
| total_ms | - | - | - | - |

### Optimised configuration

_Same table, plus a one-line description of every setting changed._

### Observations

_What dominated the latency? Which setting moved it most? Peak VRAM from `nvidia-smi` during a turn?_
