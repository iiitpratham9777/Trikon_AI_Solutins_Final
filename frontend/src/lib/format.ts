export function formatMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || Number.isNaN(ms)) return "-";
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${Math.round(ms)} ms`;
}

export interface Segment {
  key: string;
  label: string;
  ms: number;
  pct: number;
}

/** Turns per-stage timings into proportional bar segments (percentages of their own sum). */
export function latencySegments(l: {
  audio_prep_ms: number | null;
  stt_ms: number | null;
  llm_ms: number | null;
  tts_ms: number | null;
}): Segment[] {
  const raw = [
    { key: "prep", label: "Audio prep", ms: l.audio_prep_ms },
    { key: "stt", label: "Speech to text", ms: l.stt_ms },
    { key: "llm", label: "Language model", ms: l.llm_ms },
    { key: "tts", label: "Text to speech", ms: l.tts_ms },
  ].filter((s): s is { key: string; label: string; ms: number } => typeof s.ms === "number" && s.ms > 0);
  const sum = raw.reduce((a, s) => a + s.ms, 0);
  return raw.map((s) => ({ ...s, pct: sum > 0 ? (s.ms / sum) * 100 : 0 }));
}
