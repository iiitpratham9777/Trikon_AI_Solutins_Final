import { extensionFor } from "../lib/audio";
import type { ChatResponse, Language, ModelsStatus, VoiceResponse } from "./types";

export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export class ApiError extends Error {
  constructor(message: string, public code: string, public status: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError("Cannot reach the VoxPilot backend. Is it running on port 8000?", "NETWORK", 0);
  }
  if (!res.ok) {
    let code = "HTTP_ERROR";
    let message = `The server returned an error (${res.status}).`;
    try {
      const body = await res.json();
      if (body?.error?.message) {
        code = body.error.code ?? code;
        message = body.error.message;
      }
    } catch {
      /* non-JSON error body: keep the generic message */
    }
    throw new ApiError(message, code, res.status);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const api = {
  modelsStatus: (signal?: AbortSignal) => request<ModelsStatus>("/api/models/status", { signal }),

  chat: (message: string, sessionId: string | null, language: Language, speak: boolean, signal?: AbortSignal) =>
    request<ChatResponse>("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: sessionId, language, speak }),
      signal,
    }),

  voiceRespond: (blob: Blob, sessionId: string | null, language: Language, signal?: AbortSignal) => {
    const form = new FormData();
    form.append("audio", blob, `recording.${extensionFor(blob.type)}`);
    form.append("language", language);
    if (sessionId) form.append("session_id", sessionId);
    return request<VoiceResponse>("/api/voice/respond", { method: "POST", body: form, signal });
  },

  deleteSession: async (sessionId: string) => {
    try {
      await request<void>(`/api/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
    } catch (err) {
      if (!(err instanceof ApiError && err.status === 404)) throw err; // already gone is fine
    }
  },

  audioUrl: (path: string) => `${API_BASE}${path}`,
};
