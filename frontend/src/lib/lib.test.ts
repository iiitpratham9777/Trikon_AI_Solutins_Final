import { describe, expect, it, vi } from "vitest";
import { describeMicError, extensionFor, pickMimeType, rmsFromBytes } from "./audio";
import { formatMs, latencySegments } from "./format";
import { api, ApiError } from "../api/client";

describe("audio helpers", () => {
  it("picks the first supported recording type", () => {
    expect(pickMimeType((t) => t === "audio/mp4")).toBe("audio/mp4"); // Safari
    expect(pickMimeType(() => true)).toBe("audio/webm;codecs=opus"); // Chromium
    expect(pickMimeType(() => false)).toBeUndefined();
  });
  it("maps mime types to file extensions", () => {
    expect(extensionFor("audio/webm;codecs=opus")).toBe("webm");
    expect(extensionFor("audio/mp4")).toBe("mp4");
    expect(extensionFor("audio/ogg;codecs=opus")).toBe("ogg");
  });
  it("explains microphone permission errors", () => {
    expect(describeMicError(new DOMException("x", "NotAllowedError"))).toMatch(/blocked/);
    expect(describeMicError(new DOMException("x", "NotFoundError"))).toMatch(/No microphone/);
    expect(describeMicError(new Error("boom"))).toMatch(/Could not start/);
  });
  it("computes RMS: silence is 0, full-scale square wave is 1", () => {
    expect(rmsFromBytes(new Uint8Array(100).fill(128))).toBe(0);
    expect(rmsFromBytes(Uint8Array.from([0, 255, 0, 255]))).toBeGreaterThan(0.99);
  });
});

describe("format helpers", () => {
  it("formats milliseconds", () => {
    expect(formatMs(null)).toBe("-");
    expect(formatMs(340.4)).toBe("340 ms");
    expect(formatMs(1234)).toBe("1.23 s");
  });
  it("builds proportional segments and skips missing stages", () => {
    const segs = latencySegments({ audio_prep_ms: 100, stt_ms: 300, llm_ms: 500, tts_ms: null });
    expect(segs.map((s) => s.key)).toEqual(["prep", "stt", "llm"]);
    expect(segs.reduce((a, s) => a + s.pct, 0)).toBeCloseTo(100);
  });
});

describe("api client errors", () => {
  it("surfaces the backend's error message and code", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: { code: "NO_SPEECH", message: "No speech detected." } }), { status: 422 }),
    ));
    await expect(api.chat("hi", null, "en", false)).rejects.toMatchObject({ code: "NO_SPEECH", message: "No speech detected.", status: 422 });
  });
  it("reports an unreachable backend clearly", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const err = await api.chat("hi", null, "en", false).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("NETWORK");
  });
  it("treats deleting an already-missing session as success", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: { code: "SESSION_NOT_FOUND", message: "x" } }), { status: 404 }),
    ));
    await expect(api.deleteSession("abc12345")).resolves.toBeUndefined();
  });
});
