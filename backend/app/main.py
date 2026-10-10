import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import router
from .config import Settings, get_settings
from .errors import AppError
from .pipeline import Pipeline
from .services.audio_service import AudioService, AudioStore
from .services.conversation_service import ConversationService
from .services.llm_service import LLMService
from .services.stt_service import STTService
from .services.tts_service import TTSService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("voxpilot")


def build_pipeline(settings: Settings) -> Pipeline:
    return Pipeline(settings, AudioService(settings), STTService(settings), LLMService(settings),
                    TTSService(settings), ConversationService(settings), AudioStore(settings.audio_store_items))


async def _warmup(pipeline: Pipeline) -> None:
    """Load models in the background so the first user request is not a cold start."""
    for name, fn in (("stt", pipeline.stt.warmup), ("llm", pipeline.llm.warmup), ("tts", pipeline.tts.warmup)):
        try:
            await fn()
            log.info("warm-up ok: %s", name)
        except Exception as exc:  # warm-up must never stop the server
            log.warning("warm-up skipped for %s: %s", name, exc)


def create_app(pipeline: Optional[Pipeline] = None, settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or get_settings()
    pipeline = pipeline or build_pipeline(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(_warmup(pipeline)) if settings.warmup_on_start else None
        yield
        if task:
            task.cancel()
        await pipeline.llm.aclose()

    app = FastAPI(title="VoxPilot", version="1.0.0", lifespan=lifespan)
    app.state.pipeline = pipeline
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_methods=["*"], allow_headers=["*"])
    app.include_router(router)

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        return JSONResponse(status_code=422, content={"error": {
            "code": "VALIDATION_ERROR", "message": f"Invalid request: {where or 'body'} - {first.get('msg', 'invalid')}"}})

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.exception("Unhandled error")
        return JSONResponse(status_code=500, content={"error": {
            "code": "INTERNAL_ERROR", "message": "Something went wrong on the server."}})

    return app


app = create_app()
