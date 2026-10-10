/** Preferred recording containers, best first. Chromium/Firefox: webm or ogg (Opus). Safari: mp4. */
const CANDIDATES = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4", "audio/ogg"];

export function pickMimeType(isSupported: (t: string) => boolean): string | undefined {
  return CANDIDATES.find((t) => isSupported(t));
}

export function extensionFor(mime: string): string {
  const base = mime.split(";")[0];
  if (base.includes("webm")) return "webm";
  if (base.includes("ogg")) return "ogg";
  if (base.includes("mp4")) return "mp4";
  if (base.includes("wav")) return "wav";
  return "bin";
}

export function describeMicError(err: unknown): string {
  const name = err instanceof DOMException ? err.name : "";
  switch (name) {
    case "NotAllowedError":
    case "SecurityError":
      return "Microphone access was blocked. Allow it in the browser's address bar and try again.";
    case "NotFoundError":
      return "No microphone was found. Connect one and try again.";
    case "NotReadableError":
      return "The microphone is in use by another application.";
    default:
      return "Could not start the microphone.";
  }
}

/** Root-mean-square level (0..1) of a byte time-domain buffer centred on 128. */
export function rmsFromBytes(buf: ArrayLike<number>): number {
  let sum = 0;
  for (let i = 0; i < buf.length; i++) {
    const v = (buf[i] - 128) / 128;
    sum += v * v;
  }
  return buf.length ? Math.sqrt(sum / buf.length) : 0;
}
