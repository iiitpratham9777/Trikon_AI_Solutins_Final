import { useEffect, useRef } from "react";
import type { Message } from "../hooks/useAssistant";

interface Props {
  messages: Message[];
  onReplay: (url: string) => void;
}

export function ChatPanel({ messages, onReplay }: Props) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => end.current?.scrollIntoView({ block: "end" }), [messages]);

  if (messages.length === 0) {
    return (
      <div className="chat empty">
        <p className="empty-title">Ask something out loud.</p>
        <p>
          Press the microphone, speak, and pause. VoxPilot transcribes, thinks and answers using models running on this
          computer.
        </p>
        <p className="hint">
          To check memory, say <em>"My name is Rahul"</em>, then ask <em>"What is my name?"</em>
        </p>
      </div>
    );
  }

  return (
    <div className="chat" role="log" aria-live="polite" aria-label="Conversation">
      {messages.map((m) => (
        <div key={m.id} className={`msg ${m.role}${m.pending ? " pending" : ""}`}>
          <div className="who">{m.role === "user" ? "You" : "VoxPilot"}</div>
          <div className="bubble" lang={/[\u0900-\u097f]/.test(m.text) ? "hi" : undefined}>
            {m.text}
          </div>
          {m.audioUrl && (
            <button className="link" onClick={() => onReplay(m.audioUrl!)}>
              Play reply
            </button>
          )}
        </div>
      ))}
      <div ref={end} />
    </div>
  );
}
