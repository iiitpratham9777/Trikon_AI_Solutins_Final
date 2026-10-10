import re
from typing import Optional

from fastapi import APIRouter, File, Form, Request, Response, UploadFile

from .errors import AudioTooLarge, BadRequest, AudioNotFound
from .pipeline import Pipeline
from .schemas import (ChatRequest, ChatResponse, HealthResponse, Language, ModelsStatus,
                      TranscribeResponse, VoiceResponse)

router = APIRouter(prefix="/api")
_AUDIO_ID = re.compile(r"^[0-9a-f]{32}$")


def _pipe(request: Request) -> Pipeline:
    return request.app.state.pipeline


async def _read_upload(request: Request, file: UploadFile) -> bytes:
    limit = _pipe(request).settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)  # never buffer more than limit+1 bytes
    if len(data) > limit:
        raise AudioTooLarge(f"Audio is larger than {limit // (1024 * 1024)} MB.")
    return data


@router.get("/health", response_model=HealthResponse)
async def health(request: Request):
    return HealthResponse(sessions=_pipe(request).conversations.count())


@router.get("/models/status", response_model=ModelsStatus)
async def models_status(request: Request):
    return await _pipe(request).models_status()


@router.post("/voice/transcribe", response_model=TranscribeResponse)
async def transcribe(request: Request, audio: UploadFile = File(...), language: Language = Form("en")):
    data = await _read_upload(request, audio)
    return await _pipe(request).transcribe(data, audio.content_type, language)


@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest):
    if not body.message.strip():
        raise BadRequest("Message must not be blank.")
    return await _pipe(request).chat(body.message, body.session_id, body.language, body.speak,
                                     alive=request.is_disconnected)


@router.post("/voice/respond", response_model=VoiceResponse)
async def voice_respond(request: Request, audio: UploadFile = File(...),
                        session_id: Optional[str] = Form(None), language: Language = Form("en")):
    data = await _read_upload(request, audio)
    return await _pipe(request).respond(data, audio.content_type, session_id or None, language,
                                        alive=request.is_disconnected)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(request: Request, session_id: str):
    _pipe(request).conversations.delete(session_id)
    return Response(status_code=204)


@router.get("/audio/{audio_id}")
async def get_audio(request: Request, audio_id: str):
    if not _AUDIO_ID.match(audio_id):
        raise AudioNotFound("That audio is no longer available.")
    wav = _pipe(request).store.get(audio_id)
    return Response(content=wav, media_type="audio/wav", headers={"Cache-Control": "no-store"})
