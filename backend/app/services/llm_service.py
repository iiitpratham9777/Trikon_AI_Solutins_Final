"""Ollama chat client (streamed internally so time-to-first-token is measured for real)."""
import json
import logging
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from ..concurrency import StageLimiter
from ..config import Settings
from ..errors import ModelFailure, ModelTimeout, ModelUnavailable
from ..schemas import ServiceStatus

log = logging.getLogger("voxpilot.llm")

SYSTEM_PROMPTS = {
    "en": (
        "You are VoxPilot, a friendly voice assistant. Your replies are read aloud, so answer in one "
        "to three short, plain sentences. Never use markdown, bullet lists, emojis or code blocks. "
        "Always reply in English. Use the conversation so far to remember what the user told you."
    ),
    "hi": (
        "You are VoxPilot, a friendly voice assistant. Your replies are read aloud, so answer in one "
        "to three short, plain sentences. Never use markdown, bullet lists, emojis or code blocks. "
        "Always reply in Hindi written in Devanagari script. Use the conversation so far to remember "
        "what the user told you."
    ),
}


@dataclass
class LLMResult:
    text: str
    ttft_ms: Optional[float]
    ms: float


class LLMService:
    def __init__(self, settings: Settings, client: Optional[httpx.AsyncClient] = None):
        self.s = settings
        self._client = client
        self._limiter = StageLimiter(settings.stage_concurrency, settings.queue_timeout_s, "language model")

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.s.ollama_url,
                timeout=httpx.Timeout(self.s.llm_timeout_s, connect=3.0),
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    def _unreachable(self) -> ModelUnavailable:
        return ModelUnavailable(
            f"Ollama is not reachable at {self.s.ollama_url}. Install it and run `ollama serve`."
        )

    async def chat(self, history: list[dict], user_text: str, language: str) -> LLMResult:
        messages = (
            [{"role": "system", "content": SYSTEM_PROMPTS[language]}]
            + history
            + [{"role": "user", "content": user_text}]
        )
        payload = {
            "model": self.s.llm_model,
            "messages": messages,
            "stream": True,
            "keep_alive": self.s.llm_keep_alive,
            "options": {
                "num_ctx": self.s.llm_num_ctx,
                "num_predict": self.s.llm_max_tokens,
                "temperature": self.s.llm_temperature,
            },
        }
        async with self._limiter.slot():
            start = time.perf_counter()
            ttft: Optional[float] = None
            parts: list[str] = []
            try:
                async with self._http().stream("POST", "/api/chat", json=payload) as resp:
                    if resp.status_code == 404:
                        raise ModelUnavailable(
                            f"Model '{self.s.llm_model}' is not installed. Run `ollama pull {self.s.llm_model}`."
                        )
                    if resp.status_code >= 400:
                        body = (await resp.aread()).decode("utf-8", "ignore")[:200]
                        log.error("Ollama HTTP %s: %s", resp.status_code, body)
                        raise ModelFailure("The language model returned an error.")
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            raise ModelFailure("The language model returned an unreadable response.")
                        if "error" in chunk:
                            log.error("Ollama stream error: %s", chunk["error"])
                            raise ModelFailure(
                                "The language model failed (it may be out of memory). "
                                "Try a smaller LLM_MODEL or lower LLM_NUM_CTX."
                            )
                        piece = chunk.get("message", {}).get("content", "")
                        if piece:
                            if ttft is None:
                                ttft = (time.perf_counter() - start) * 1000
                            parts.append(piece)
                        if chunk.get("done"):
                            break
            except httpx.ConnectError:
                raise self._unreachable()
            except httpx.TimeoutException:
                raise ModelTimeout("The language model took too long to answer.")
            except httpx.HTTPError as exc:
                log.error("Ollama transport error: %s", exc)
                raise ModelFailure("Lost connection to the language model.")
            ms = (time.perf_counter() - start) * 1000

        text = "".join(parts).strip()
        if not text:
            raise ModelFailure("The language model returned an empty answer.")
        return LLMResult(text=text, ttft_ms=ttft, ms=ms)

    async def warmup(self) -> None:
        """Loads the model into memory without generating text."""
        try:
            await self._http().post(
                "/api/generate", json={"model": self.s.llm_model, "keep_alive": self.s.llm_keep_alive}
            )
        except httpx.HTTPError:
            pass

    async def status(self) -> ServiceStatus:
        try:
            resp = await self._http().get("/api/tags", timeout=3.0)
            resp.raise_for_status()
            names = {m.get("name", "") for m in resp.json().get("models", [])}
        except httpx.HTTPError:
            return ServiceStatus(ready=False, detail=f"Ollama not reachable at {self.s.ollama_url}")
        want = self.s.llm_model
        found = want in names or (":" not in want and f"{want}:latest" in names)
        if not found:
            return ServiceStatus(ready=False, detail=f"Model not pulled: run `ollama pull {want}`")
        return ServiceStatus(ready=True, loaded=True, detail=f"ollama '{want}'")
