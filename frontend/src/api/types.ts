export type Language = "en" | "hi";

export interface Latency {
  audio_prep_ms: number | null;
  stt_ms: number | null;
  llm_ttft_ms: number | null;
  llm_ms: number | null;
  tts_ms: number | null;
  total_ms: number | null;
  time_to_audio_ms: number | null;
}

export interface VoiceResponse {
  session_id: string;
  transcript: string;
  response: string;
  audio_url: string;
  language: Language;
  latency: Latency;
}

export interface ChatResponse {
  session_id: string;
  response: string;
  audio_url: string | null;
  latency: Latency;
}

export interface ServiceStatus {
  ready: boolean;
  loaded: boolean;
  detail: string;
}

export interface ModelsStatus {
  stt: ServiceStatus;
  llm: ServiceStatus;
  tts: ServiceStatus;
  ffmpeg: ServiceStatus;
  config: Record<string, string | number>;
}
