"""Typed application errors. Messages are user-safe; details go to the log only."""


class AppError(Exception):
    status_code = 500
    code = "INTERNAL_ERROR"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class BadRequest(AppError):
    status_code, code = 400, "BAD_REQUEST"


class EmptyAudio(AppError):
    status_code, code = 400, "EMPTY_AUDIO"


class AudioTooLarge(AppError):
    status_code, code = 413, "AUDIO_TOO_LARGE"


class UnsupportedAudio(AppError):
    status_code, code = 415, "UNSUPPORTED_AUDIO"


class InvalidAudio(AppError):
    status_code, code = 422, "INVALID_AUDIO"


class NoSpeech(AppError):
    status_code, code = 422, "NO_SPEECH"


class SessionNotFound(AppError):
    status_code, code = 404, "SESSION_NOT_FOUND"


class AudioNotFound(AppError):
    status_code, code = 404, "AUDIO_NOT_FOUND"


class Busy(AppError):
    status_code, code = 503, "BUSY"


class ModelUnavailable(AppError):
    status_code, code = 503, "MODEL_UNAVAILABLE"


class ModelTimeout(AppError):
    status_code, code = 504, "MODEL_TIMEOUT"


class ModelFailure(AppError):
    status_code, code = 502, "MODEL_FAILURE"
