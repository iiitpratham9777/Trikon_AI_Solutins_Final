import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { Language, Latency, ModelsStatus } from "../api/types";

export interface Message {
  id: number;
  role: "user" | "assistant";
  text: string;
  audioUrl?: string;
  pending?: boolean;
}

export type Phase = "idle" | "recording" | "processing" | "speaking";

export interface TurnTiming {
  server: Latency;
  clientRoundTripMs: number; // request sent -> response parsed
  clientToPlayMs: number | null; // request sent -> audio actually started
}

const errText = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong. Please try again.");

export function useAssistant() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [language, setLanguage] = useState<Language>("en");
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [timing, setTiming] = useState<TurnTiming | null>(null);
  const [status, setStatus] = useState<ModelsStatus | null>(null);
  const [backendUp, setBackendUp] = useState<boolean | null>(null);

  const sessionId = useRef<string | null>(null);
  const requestSeq = useRef(0); // bumps on every submit/interrupt; stale replies compare against it
  const msgSeq = useRef(0);
  const abort = useRef<AbortController | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);

  // ---- health polling ----
  useEffect(() => {
    let alive = true;
    const ctl = new AbortController();
    const poll = async () => {
      try {
        const s = await api.modelsStatus(ctl.signal);
        if (alive) {
          setStatus(s);
          setBackendUp(true);
        }
      } catch {
        if (alive) setBackendUp(false);
      }
    };
    void poll();
    const t = window.setInterval(poll, 8000);
    return () => {
      alive = false;
      ctl.abort();
      window.clearInterval(t);
    };
  }, []);

  // ---- playback ----
  const stopSpeaking = useCallback(() => {
    const a = audio.current;
    if (a) {
      a.pause();
      audio.current = null;
    }
    setPhase((p) => (p === "speaking" ? "idle" : p));
  }, []);

  const play = useCallback((url: string, onStarted?: () => void) => {
    audio.current?.pause();
    const a = new Audio(api.audioUrl(url));
    audio.current = a;
    a.onplaying = () => {
      if (audio.current === a) {
        setPhase("speaking");
        onStarted?.();
      }
    };
    a.onended = () => audio.current === a && setPhase("idle");
    a.onerror = () => {
      if (audio.current === a) {
        setPhase("idle");
        setError("The reply audio could not be played.");
      }
    };
    a.play().catch(() => {
      if (audio.current === a) {
        setPhase("idle");
        setError("The browser blocked autoplay. Press Play on the reply.");
      }
    });
  }, []);

  /** Invalidate any in-flight request and silence audio. Returns the new request id. */
  const interrupt = useCallback(() => {
    abort.current?.abort();
    abort.current = null;
    audio.current?.pause();
    audio.current = null;
    return ++requestSeq.current;
  }, []);

  const finishTurn = useCallback(
    (id: number, started: number, sid: string, server: Latency, audioUrl: string | null) => {
      setTiming({ server, clientRoundTripMs: performance.now() - started, clientToPlayMs: null });
      sessionId.current = sid;
      if (audioUrl) {
        play(audioUrl, () => {
          if (requestSeq.current === id)
            setTiming((t) => (t ? { ...t, clientToPlayMs: performance.now() - started } : t));
        });
      } else setPhase("idle");
    },
    [play],
  );

  const sendVoice = useCallback(
    async (blob: Blob) => {
      const id = interrupt();
      const ctl = new AbortController();
      abort.current = ctl;
      const pendingId = ++msgSeq.current;
      setError(null);
      setPhase("processing");
      setMessages((m) => [...m, { id: pendingId, role: "user", text: "Transcribing...", pending: true }]);
      const started = performance.now();
      try {
        const res = await api.voiceRespond(blob, sessionId.current, language, ctl.signal);
        if (id !== requestSeq.current) return; // user interrupted: drop the outdated reply
        setMessages((m) => [
          ...m.filter((x) => x.id !== pendingId),
          { id: pendingId, role: "user", text: res.transcript },
          { id: ++msgSeq.current, role: "assistant", text: res.response, audioUrl: res.audio_url },
        ]);
        finishTurn(id, started, res.session_id, res.latency, res.audio_url);
      } catch (e) {
        setMessages((m) => m.filter((x) => x.id !== pendingId));
        if (e instanceof DOMException && e.name === "AbortError") return;
        if (id !== requestSeq.current) return;
        setError(errText(e));
        setPhase("idle");
      }
    },
    [finishTurn, interrupt, language],
  );

  const sendText = useCallback(
    async (text: string) => {
      const clean = text.trim();
      if (!clean || phase === "processing") return; // blocks duplicate submissions
      const id = interrupt();
      const ctl = new AbortController();
      abort.current = ctl;
      setError(null);
      setPhase("processing");
      setMessages((m) => [...m, { id: ++msgSeq.current, role: "user", text: clean }]);
      const started = performance.now();
      try {
        const res = await api.chat(clean, sessionId.current, language, true, ctl.signal);
        if (id !== requestSeq.current) return;
        setMessages((m) => [
          ...m,
          { id: ++msgSeq.current, role: "assistant", text: res.response, audioUrl: res.audio_url ?? undefined },
        ]);
        finishTurn(id, started, res.session_id, res.latency, res.audio_url);
      } catch (e) {
        if (e instanceof DOMException && e.name === "AbortError") return;
        if (id !== requestSeq.current) return;
        setError(errText(e));
        setPhase("idle");
      }
    },
    [finishTurn, interrupt, language, phase],
  );

  const newConversation = useCallback(() => {
    interrupt();
    const old = sessionId.current;
    sessionId.current = null;
    setMessages([]);
    setTiming(null);
    setError(null);
    setPhase("idle");
    if (old) void api.deleteSession(old).catch(() => undefined);
  }, [interrupt]);

  const replay = useCallback(
    (url: string) => {
      setError(null);
      play(url);
    },
    [play],
  );

  return {
    messages, language, setLanguage, phase, setPhase, error, setError, timing, status, backendUp,
    sendVoice, sendText, newConversation, stopSpeaking, replay, interrupt,
  };
}
