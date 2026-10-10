import { useRecorder } from "./hooks/useRecorder";
import { useAssistant } from "./hooks/useAssistant";
import { ChatPanel } from "./components/ChatPanel";
import { Composer } from "./components/Composer";
import { PipelinePanel } from "./components/PipelinePanel";
import { useState } from "react";
import type { Language } from "./api/types";

const LANGS: { id: Language; label: string }[] = [
  { id: "en", label: "English" },
  { id: "hi", label: "हिन्दी" },
];

export default function App() {
  const a = useAssistant();
  const [autoStop, setAutoStop] = useState(true);

  const rec = useRecorder({ autoStop, onComplete: a.sendVoice, onError: (m) => { a.setError(m); a.setPhase("idle"); } });
  const phase = rec.recording ? "recording" : a.phase;

  const onMic = async () => {
    if (rec.recording) return rec.stop();
    a.interrupt(); // cancels any in-flight request and playing audio so nothing stale is spoken
    a.setPhase("idle");
    a.setError(null);
    await rec.start();
  };

  const newConversation = () => {
    rec.cancel();
    a.newConversation();
  };

  return (
    <div className="app">
      <header>
        <h1>VoxPilot</h1>
        <div className="controls">
          <div className="seg-control" role="radiogroup" aria-label="Language">
            {LANGS.map((l) => (
              <button
                key={l.id}
                role="radio"
                aria-checked={a.language === l.id}
                className={a.language === l.id ? "on" : ""}
                onClick={() => a.setLanguage(l.id)}
                lang={l.id}
              >
                {l.label}
              </button>
            ))}
          </div>
          <label className="check">
            <input type="checkbox" checked={autoStop} onChange={(e) => setAutoStop(e.target.checked)} />
            Stop on silence
          </label>
          <button className="secondary" onClick={newConversation}>
            New conversation
          </button>
        </div>
      </header>

      <main>
        <section className="conversation" aria-label="Conversation">
          <ChatPanel messages={a.messages} onReplay={a.replay} />
          {a.error && (
            <div className="error" role="alert">
              <span>{a.error}</span>
              <button className="link" onClick={() => a.setError(null)}>
                Dismiss
              </button>
            </div>
          )}
          <Composer
            phase={phase}
            level={rec.level}
            micSupported={rec.supported}
            onMic={onMic}
            onSend={a.sendText}
            onStopSpeaking={a.stopSpeaking}
          />
        </section>
        <PipelinePanel status={a.status} backendUp={a.backendUp} timing={a.timing} />
      </main>
    </div>
  );
}
