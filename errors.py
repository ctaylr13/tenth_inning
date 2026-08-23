"""Typed application errors and the single error-envelope builder.

Envelope: {"error": {"code", "message", "details", "request_id"}}

Status rule: 4xx if the client sent something wrong, 5xx if the client was fine
and we broke. The test is whether retrying the identical request could succeed.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    VALIDATION_FAILED = "VALIDATION_FAILED"
    ROUTE_NOT_FOUND = "ROUTE_NOT_FOUND"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    DUPLICATE_WATCH_ENTRY = "DUPLICATE_WATCH_ENTRY"
    DATA_SOURCE_UNAVAILABLE = "DATA_SOURCE_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    """Base for every error we raise deliberately.

    Keyword args land in `details`: DuplicateWatchEntry(duplicates=[776543]).
    `status_code` and `code` are overridable per raise -- for a code carrying
    two statuses, and for handlers with no subclass to reach for.
    """

    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    status_code: int = 500
    message: str = "Something went wrong."

    def __init__(
        self,
        message: str | None = None,
        *,
        status_code: int | None = None,
        code: ErrorCode | None = None,
        **details: Any,
    ) -> None:
        cls = type(self)
        self.message = message if message is not None else cls.message
        self.status_code = status_code if status_code is not None else cls.status_code
        self.code = code if code is not None else cls.code
        self.details = details
        super().__init__(self.message)


# --- 4xx: the client sent something wrong -----------------------------------
class ValidationFailed(AppError):
    code = ErrorCode.VALIDATION_FAILED
    status_code = 422
    message = "The request failed validation."


class ResourceNotFound(AppError):
    """The route exists and the id parsed -- there just is no such row.

    Distinct from ROUTE_NOT_FOUND, which means the client built a URL we don't
    serve. This one is normal traffic: asking for a game that isn't there.
    """

    code = ErrorCode.RESOURCE_NOT_FOUND
    status_code = 404
    message = "That resource does not exist."


class DuplicateWatchEntry(AppError):
    code = ErrorCode.DUPLICATE_WATCH_ENTRY
    status_code = 409
    message = "The payload lists the same gamePk more than once."


# --- 5xx: we broke ----------------------------------------------------------
class DataSourceUnavailable(AppError):
    """Transient only -- a missing file never retries clean, so that's InternalError."""

    code = ErrorCode.DATA_SOURCE_UNAVAILABLE
    status_code = 503
    message = "The data source is temporarily unavailable. Try again shortly."


class InternalError(AppError):
    code = ErrorCode.INTERNAL_ERROR
    status_code = 500
    message = "Something went wrong on our end."


# --- the one envelope builder ----------------------------------------------
def error_body(
    code: ErrorCode | str,
    message: str,
    request_id: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The only place that knows the envelope's shape, so it can't drift."""
    return {
        "error": {
            "code": code.value if isinstance(code, ErrorCode) else str(code),
            "message": message,
            "details": details or {},
            "request_id": request_id,
        }
    }
