"""Measure the real pipeline through the HTTP API. Nothing here is simulated.

Start the backend first, then:
    python scripts/benchmark.py --audio sample_en.wav --runs 8 --label baseline
Restart the backend between configurations to capture a true cold start.
Run 1 is reported separately as "first request" (cold if the server was just restarted
with WARMUP_ON_START=false); runs 2..N are "warm".
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import httpx

FIELDS = ["audio_prep_ms", "stt_ms", "llm_ttft_ms", "llm_ms", "tts_ms", "total_ms", "time_to_audio_ms", "client_ms"]


def summarize(rows: list[dict]) -> dict:
    out = {}
    for f in FIELDS:
        vals = [r[f] for r in rows if r.get(f) is not None]
        if vals:
            out[f] = {"median": statistics.median(vals), "mean": statistics.fmean(vals),
                      "min": min(vals), "max": max(vals), "n": len(vals)}
    return out


def table(title: str, summary: dict) -> str:
    lines = [f"### {title}", "", "| stage | median ms | mean ms | min ms | max ms | n |", "|---|---:|---:|---:|---:|---:|"]
    for f, s in summary.items():
        lines.append(f"| {f} | {s['median']:.0f} | {s['mean']:.0f} | {s['min']:.0f} | {s['max']:.0f} | {s['n']} |")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True, help="WAV/WebM/OGG/MP4 clip containing speech")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--language", choices=["en", "hi"], default="en")
    ap.add_argument("--runs", type=int, default=6)
    ap.add_argument("--label", default="run")
    ap.add_argument("--out", help="write raw results as JSON (e.g. docs/benchmark-baseline.json)")
    args = ap.parse_args()

    path = Path(args.audio)
    ctype = {".wav": "audio/wav", ".webm": "audio/webm", ".ogg": "audio/ogg", ".mp4": "audio/mp4"}.get(path.suffix, "audio/wav")
    data = path.read_bytes()
    rows = []
    with httpx.Client(base_url=args.url, timeout=180) as c:
        try:
            status = c.get("/api/models/status").json()
        except httpx.HTTPError:
            print("Backend is not reachable. Start it first.", file=sys.stderr)
            return 2
        for i in range(args.runs):
            t0 = time.perf_counter()
            r = c.post("/api/voice/respond", files={"audio": (path.name, data, ctype)},
                       data={"language": args.language})
            client_ms = (time.perf_counter() - t0) * 1000
            if r.status_code != 200:
                print(f"run {i + 1} failed: {r.status_code} {r.text}", file=sys.stderr)
                return 1
            body = r.json()
            rows.append({**body["latency"], "client_ms": client_ms, "transcript": body["transcript"]})
            print(f"run {i + 1}/{args.runs}: total {body['latency']['total_ms']:.0f} ms | transcript: {body['transcript']!r}")

    report = {"label": args.label, "config": status["config"], "language": args.language,
              "first_request": rows[0], "warm": summarize(rows[1:]) if len(rows) > 1 else {}}
    print()
    print(f"## {args.label}  (config: {json.dumps(status['config'])})")
    print(table("First request", {k: {"median": v, "mean": v, "min": v, "max": v, "n": 1}
                                  for k, v in rows[0].items() if k in FIELDS and v is not None}))
    if report["warm"]:
        print()
        print(table(f"Warm requests (runs 2-{len(rows)})", report["warm"]))
    if args.out:
        Path(args.out).write_text(json.dumps({**report, "runs": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nraw results saved to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
