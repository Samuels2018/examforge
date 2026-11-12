from typing import Any


class AppError(Exception):
    """Error de negocio con un contrato estable para la API."""

    status_code = 400
    code = "app_error"

    def __init__(self, message: str, *, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class UnsupportedFileError(AppError):
    status_code = 415
    code = "unsupported_file"


class FileTooLargeError(AppError):
    status_code = 413
    code = "file_too_large"


class TooManyFilesError(AppError):
    status_code = 413
    code = "too_many_files"


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"


class LLMUnavailableError(AppError):
    status_code = 502
    code = "llm_unavailable"


class EmbeddingUnavailableError(AppError):
    status_code = 502
    code = "embedding_unavailable"


class InvalidMaterialError(AppError):
    status_code = 422
    code = "invalid_material"


class AuthError(AppError):
    status_code = 401
    code = "unauthorized"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class GenerationCancelledError(AppError):
    status_code = 409
    code = "generation_cancelled"


class ImportFailedError(AppError):
    status_code = 422
    code = "import_failed"


class ImportBlockedError(AppError):
    status_code = 400
    code = "import_blocked"


class QuotaExceededError(AppError):
    status_code = 409
    code = "quota_exceeded"


class InvalidCursorError(AppError):
    status_code = 400
    code = "invalid_cursor"
