import { useState } from "react";
import type { Phase } from "../hooks/useAssistant";

interface Props {
  phase: Phase;
  level: number;
  micSupported: boolean;
  onMic: () => void;
  onSend: (text: string) => void;
  onStopSpeaking: () => void;
}

const MIC_LABEL: Record<Phase, string> = {
  idle: "Start recording",
  recording: "Stop recording",
  processing: "Interrupt and record again",
  speaking: "Interrupt and record",
};

export function Composer({ phase, level, micSupported, onMic, onSend, onStopSpeaking }: Props) {
  const [text, setText] = useState("");
  const busy = phase === "processing";

  const submit = () => {
    if (!text.trim() || busy) return;
    onSend(text);
    setText("");
  };

  return (
    <div className="composer">
      <button
        className={`mic ${phase === "recording" ? "live" : ""}`}
        style={{ ["--level" as string]: level }}
        onClick={onMic}
        disabled={!micSupported}
        aria-label={MIC_LABEL[phase]}
        aria-pressed={phase === "recording"}
        title={micSupported ? MIC_LABEL[phase] : "Recording is not supported in this browser"}
      >
        {phase === "recording" ? <span className="stop-glyph" /> : <span className="mic-glyph" />}
      </button>

      <div className="status-line" aria-live="polite">
        {phase === "recording" && "Listening - stops after you pause"}
        {phase === "processing" && "Transcribing and thinking..."}
        {phase === "speaking" && "Speaking"}
        {phase === "idle" && "Ready"}
      </div>

      {phase === "speaking" && (
        <button className="secondary" onClick={onStopSpeaking}>
          Stop speaking
        </button>
      )}

      <form
        className="text-entry"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Or type a message"
          aria-label="Type a message"
          maxLength={2000}
          disabled={busy}
        />
        <button type="submit" disabled={busy || !text.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
