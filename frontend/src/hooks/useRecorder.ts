import { useCallback, useEffect, useRef, useState } from "react";
import { describeMicError, pickMimeType, rmsFromBytes } from "../lib/audio";

const SPEECH_RMS = 0.02; // above this counts as speech
const SILENCE_MS = 1500; // stop this long after speech ends
const NO_SPEECH_MS = 8000; // give up if nobody speaks
const MAX_MS = 60000; // matches the backend limit

interface Options {
  autoStop: boolean;
  onComplete: (blob: Blob) => void;
  onError: (message: string) => void;
}

export function useRecorder({ autoStop, onComplete, onError }: Options) {
  const [recording, setRecording] = useState(false);
  const [level, setLevel] = useState(0);
  const recRef = useRef<MediaRecorder | null>(null);
  const cleanupRef = useRef<() => void>(() => {});
  const cb = useRef({ onComplete, onError, autoStop });
  cb.current = { onComplete, onError, autoStop };

  const supported = typeof MediaRecorder !== "undefined" && !!navigator.mediaDevices?.getUserMedia;

  const stop = useCallback(() => {
    const rec = recRef.current;
    if (rec && rec.state !== "inactive") rec.stop();
  }, []);

  /** Aborts without delivering audio (used when the user interrupts). */
  const cancel = useCallback(() => {
    const rec = recRef.current;
    if (rec && rec.state !== "inactive") {
      rec.ondataavailable = null;
      rec.onstop = null;
      rec.stop();
    }
    cleanupRef.current();
  }, []);

  const start = useCallback(async () => {
    if (!supported) {
      cb.current.onError("This browser does not support audio recording. Use a recent Chrome, Edge, Firefox or Safari.");
      return false;
    }
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
      });
    } catch (err) {
      cb.current.onError(describeMicError(err));
      return false;
    }

    const mimeType = pickMimeType((t) => MediaRecorder.isTypeSupported(t));
    const rec = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    const chunks: Blob[] = [];
    const ctx = new AudioContext();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const buf = new Uint8Array(analyser.fftSize);

    const startedAt = Date.now();
    let heardSpeech = false;
    let lastVoice = startedAt;
    let finished = false;

    const timer = window.setInterval(() => {
      analyser.getByteTimeDomainData(buf);
      const rms = rmsFromBytes(buf);
      setLevel(Math.min(1, rms * 6));
      const now = Date.now();
      if (rms > SPEECH_RMS) {
        heardSpeech = true;
        lastVoice = now;
      }
      if (now - startedAt > MAX_MS) stop();
      else if (cb.current.autoStop && heardSpeech && now - lastVoice > SILENCE_MS) stop();
      else if (cb.current.autoStop && !heardSpeech && now - startedAt > NO_SPEECH_MS) stop();
    }, 100);

    const cleanup = () => {
      if (finished) return;
      finished = true;
      window.clearInterval(timer);
      stream.getTracks().forEach((t) => t.stop());
      void ctx.close();
      setRecording(false);
      setLevel(0);
      recRef.current = null;
    };
    cleanupRef.current = cleanup;

    rec.ondataavailable = (e) => e.data.size > 0 && chunks.push(e.data);
    rec.onerror = () => {
      cleanup();
      cb.current.onError("Recording failed. Please try again.");
    };
    rec.onstop = () => {
      const type = rec.mimeType || mimeType || "audio/webm";
      cleanup();
      if (chunks.length === 0) return cb.current.onError("Nothing was recorded.");
      cb.current.onComplete(new Blob(chunks, { type }));
    };

    recRef.current = rec;
    rec.start(250);
    setRecording(true);
    return true;
  }, [stop, supported]);

  useEffect(() => () => cancel(), [cancel]);

  return { recording, level, start, stop, cancel, supported };
}
