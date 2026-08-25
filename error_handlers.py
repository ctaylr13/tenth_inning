"""Request-ID middleware plus the five exception handlers.

All five are required -- drop one and a class of failure escapes the envelope.
Each handler only turns its exception into an AppError; `_respond` owns the
envelope and header, `log_error` owns the log line, so one place can drift, not
five. Four answer HTTP; the fifth answers a websocket, where there is no
response to return and no middleware has run.
"""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import FastAPI, Request, WebSocket
from fastapi.exceptions import RequestValidationError, WebSocketRequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from errors import (
    AppError,
    ErrorCode,
    InternalError,
    ValidationFailed,
    error_body,
    failure_frame,
)

logger = logging.getLogger("tenth_inning")

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a request id to every request and echo it back.

    A client-supplied id is kept, so the frontend can mint one, log it with its
    own error, and give you something to grep for.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:12]
        # request.state is backed by request.scope["state"], and the scope object
        # is passed down unchanged -- so handlers that run *outside* this
        # middleware still read this id off their own Request.
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def get_request_id(request: Request) -> str:
    """Never raises -- a missing id must not mask the error being handled."""
    return str(getattr(request.state, "request_id", "-"))


def log_error(
    method: str,
    path: str,
    error: AppError,
    request_id: str,
    *,
    exc_info: BaseException | None = None,
) -> None:
    """One log format for every failure, whatever transport carried it --
    `method` is "WS" for a websocket."""
    is_server_error = error.status_code >= 500

    # 4xx is normal traffic -- info level, and no traceback even when we have one.
    # fmt: off
    # Grouped to mirror the format string above it: where, then what, then why.
    (logger.error if is_server_error else logger.info)(
        "%s %s -> %s %s [request_id=%s] %s %s",
        method, path, error.status_code,
        error.code.value, request_id, error.message, error.details,
        exc_info=exc_info if is_server_error else None,
    )
    # fmt: on


def _respond(
    request: Request,
    error: AppError,
    *,
    exc_info: BaseException | None = None,
) -> JSONResponse:
    """Log the failure and return the envelope. The HTTP handlers' only exit."""
    request_id = get_request_id(request)
    log_error(request.method, request.url.path, error, request_id, exc_info=exc_info)

    return JSONResponse(
        status_code=error.status_code,
        content=error_body(error.code, error.message, request_id, error.details),
        headers={REQUEST_ID_HEADER: request_id},
    )


# errors raised on purpose
async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    return _respond(request, exc, exc_info=exc)


# FastAPI starts every loc with where the value came from. The client knows
# which endpoint it called, so that prefix is noise -- and keeping it for query
# params while dropping it for bodies would make `field` mean two things.
_REQUEST_LOCATIONS = {"body", "query", "path", "header", "cookie"}


def _field_path(loc) -> str:
    parts = list(loc)
    if parts and parts[0] in _REQUEST_LOCATIONS:
        parts = parts[1:]
    return ".".join(str(p) for p in parts)


# FastAPI rejected the request before our code
async def handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Reshaped so a form can consume it: dotted field path plus the reason.
    fields = [
        {"field": _field_path(err.get("loc", [])), "reason": err.get("msg", "")}
        for err in exc.errors()
    ]

    return _respond(request, ValidationFailed(fields=fields))


# HTTPExceptions raised around the code (unmatched URL, 405)
# 405 is ROUTE_NOT_FOUND, not VALIDATION_FAILED -- a route is a path plus a
# method, and nothing about the payload was wrong.
_STATUS_TO_CODE = {
    404: ErrorCode.ROUTE_NOT_FOUND,
    405: ErrorCode.ROUTE_NOT_FOUND,
}


async def handle_http_exception(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    if exc.status_code >= 500:
        code = ErrorCode.INTERNAL_ERROR
    else:
        code = _STATUS_TO_CODE.get(exc.status_code, ErrorCode.VALIDATION_FAILED)

    message = exc.detail if isinstance(exc.detail, str) else "Request failed."

    # No subclass fits -- Starlette picked the status
    return _respond(request, AppError(message, status_code=exc.status_code, code=code))


# the safety net for our own bugs
async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    """The request was fine, we broke, so 500.
    Exception text leaks table names, paths and query structure -- the client
    gets a request id, the traceback goes to the logs.
    """
    return _respond(request, InternalError(), exc_info=exc)


# the same rejection, on a transport with no response to reject with
# RFC 6455 close codes. A separate namespace from HTTP status codes and much
# coarser -- 1008 is the whole 4xx range.
WS_POLICY_VIOLATION = 1008


async def handle_websocket_validation_error(
    websocket: WebSocket, exc: WebSocketRequestValidationError
) -> None:
    """The fifth handler, and the one the websocket transport forced.

    FastAPI's default rejects the handshake with 1008 and pydantic's raw error
    list as the close reason -- internals `handle_validation_error` exists to
    reshape, on a channel the browser cannot read anyway (a handshake-phase
    close reaches JavaScript as a bare 1006 with no reason at all).

    So: accept, then report. That costs the rejection its status line -- every
    bad request now looks like a successful 101 to proxies and metrics -- and
    buys back the envelope, which is the only thing that lets the client tell
    "you sent a bad gamePk" from "the API is down". Same trade stream_game_ws
    makes for a missing game, made in the same direction on purpose.
    """
    # No middleware runs on a websocket scope, so there is no id to read back.
    request_id = uuid.uuid4().hex[:12]
    error = ValidationFailed(
        fields=[
            {"field": _field_path(err.get("loc", [])), "reason": err.get("msg", "")}
            for err in exc.errors()
        ]
    )
    log_error("WS", websocket.url.path, error, request_id)

    await websocket.accept()
    await websocket.send_text(
        json.dumps(failure_frame(error.code, error.message, request_id, error.details))
    )
    await websocket.close(code=WS_POLICY_VIOLATION)


def install_error_handling(app: FastAPI) -> None:
    """Wire the middleware and all five handlers onto the app. One call."""
    app.add_middleware(RequestIDMiddleware)
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(Exception, handle_unexpected)
    app.add_exception_handler(
        WebSocketRequestValidationError, handle_websocket_validation_error
    )
