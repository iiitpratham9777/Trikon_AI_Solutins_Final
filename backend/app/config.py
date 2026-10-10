"""Central configuration. Every value can be overridden via environment / .env."""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Server ---
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    warmup_on_start: bool = True

    # --- Audio ---
    max_upload_mb: int = 10
    max_audio_seconds: float = 60.0
    min_audio_seconds: float = 0.3
    silence_rms_threshold: float = 0.003
    ffmpeg_path: str = ""  # empty = PATH, then imageio-ffmpeg
    ffmpeg_timeout_s: float = 20.0

    # --- STT (Faster-Whisper) ---
    whisper_model: str = "small"
    whisper_device: Literal["cpu", "cuda", "auto"] = "cpu"
    whisper_compute_type: str = "int8"
    whisper_cpu_threads: int = 4
    whisper_beam_size: int = 1
    whisper_vad_filter: bool = True
    stt_timeout_s: float = 60.0

    # --- LLM (Ollama) ---
    ollama_url: str = "http://127.0.0.1:11434"
    llm_model: str = "qwen2.5:3b"
    llm_num_ctx: int = 2048
    llm_max_tokens: int = 200
    llm_temperature: float = 0.6
    llm_keep_alive: str = "10m"
    llm_timeout_s: float = 90.0

    # --- TTS ---
    tts_engine: Literal["kokoro", "piper"] = "kokoro"
    tts_device: Literal["cpu", "cuda"] = "cpu"  # keep VRAM free for the LLM
    tts_timeout_s: float = 60.0
    tts_max_chars: int = 600
    kokoro_voice_en: str = "af_heart"
    kokoro_voice_hi: str = "hf_alpha"
    kokoro_speed: float = 1.0
    piper_executable: str = "piper"
    piper_model_en: str = ""  # path to an English .onnx voice
    piper_model_hi: str = ""  # path to a Hindi .onnx voice

    # --- Conversation / concurrency ---
    max_history_turns: int = 6  # user+assistant pairs kept per session
    max_sessions: int = 200
    session_ttl_s: int = 3600
    max_message_chars: int = 2000
    audio_store_items: int = 20
    stage_concurrency: int = 1  # simultaneous calls per model stage
    queue_timeout_s: float = 30.0  # wait for a free slot before answering 503

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
