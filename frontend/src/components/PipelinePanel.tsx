import type { ModelsStatus } from "../api/types";
import type { TurnTiming } from "../hooks/useAssistant";
import { formatMs, latencySegments } from "../lib/format";

interface Props {
  status: ModelsStatus | null;
  backendUp: boolean | null;
  timing: TurnTiming | null;
}

const SERVICES: { key: "stt" | "llm" | "tts" | "ffmpeg"; label: string }[] = [
  { key: "stt", label: "Speech to text" },
  { key: "llm", label: "Language model" },
  { key: "tts", label: "Text to speech" },
  { key: "ffmpeg", label: "Audio decoder" },
];

export function PipelinePanel({ status, backendUp, timing }: Props) {
  const segs = timing ? latencySegments(timing.server) : [];
  const s = timing?.server;

  return (
    <aside className="panel" aria-label="Pipeline status and latency">
      <section>
        <h2>Models</h2>
        {backendUp === false && <p className="bad">Backend offline. Start it on port 8000.</p>}
        {backendUp === null && <p className="muted">Checking...</p>}
        {status && backendUp && (
          <ul className="health">
            {SERVICES.map(({ key, label }) => {
              const st = status[key];
              return (
                <li key={key}>
                  <span className={`dot ${st.ready ? "ok" : "off"}`} aria-hidden />
                  <span className="svc">
                    {label}
                    <span className="sr-only">{st.ready ? " ready" : " not ready"}</span>
                  </span>
                  <span className="detail">
                    {st.detail}
                    {st.ready && !st.loaded && key !== "ffmpeg" ? " (loads on first use)" : ""}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section>
        <h2>Last response</h2>
        {!timing || !s ? (
          <p className="muted">Timings appear after your first turn. All values are measured, not estimated.</p>
        ) : (
          <>
            <div className="bar" role="img" aria-label="Share of server time per stage">
              {segs.map((g) => (
                <span key={g.key} className={`seg ${g.key}`} style={{ width: `${g.pct}%` }} title={`${g.label}: ${formatMs(g.ms)}`} />
              ))}
            </div>
            <dl className="timings">
              <Row cls="prep" label="Audio prep" v={s.audio_prep_ms} />
              <Row cls="stt" label="Speech to text" v={s.stt_ms} />
              <Row cls="llm" label="LLM first token" v={s.llm_ttft_ms} sub />
              <Row cls="llm" label="LLM total" v={s.llm_ms} />
              <Row cls="tts" label="Text to speech" v={s.tts_ms} />
              <Row cls="total" label="Server total" v={s.total_ms} strong />
              <Row cls="" label="Round trip (browser)" v={timing.clientRoundTripMs} />
              <Row cls="" label="Until audio started" v={timing.clientToPlayMs} />
            </dl>
          </>
        )}
      </section>
    </aside>
  );
}

function Row({ cls, label, v, sub, strong }: { cls: string; label: string; v: number | null; sub?: boolean; strong?: boolean }) {
  if (v === null && sub) return null;
  return (
    <div className={`row${sub ? " sub" : ""}${strong ? " strong" : ""}`}>
      <dt>
        {cls && !sub && <span className={`key ${cls}`} aria-hidden />}
        {label}
      </dt>
      <dd>{formatMs(v)}</dd>
    </div>
  );
}
