"""Request-ID middleware plus the five exception handlers.

All five are required -- drop one and a class of failure escapes the envelope.
Each handler only turns its exception into an AppError and hands it to
`_deliver`, so one place can drift, not five.

`_deliver` is where the transports part. An HTTP connection gets a response with
a status code; a websocket gets the same envelope inside a frame, because past
the handshake there is no response left to return. Handlers are reached on both
-- Starlette passes a WebSocket where a Request would be -- so nothing here may
assume `.method` exists.
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
from starlette.websockets import WebSocketState

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


# RFC 6455 close codes -- a separate, far coarser namespace than HTTP status.
# 1008 is the whole 4xx range and 1011 the whole 5xx, so the code is only ever a
# hint and the frame carries the truth.
WS_NORMAL_CLOSURE = 1000
WS_POLICY_VIOLATION = 1008
WS_INTERNAL_ERROR = 1011


def ws_close_code(error: AppError) -> int:
    """The nearest close code to a status. Derived, not mapped by hand, so a new
    AppError subclass cannot land on a code nobody chose."""
    if error.status_code >= 500:
        return WS_INTERNAL_ERROR
    if error.status_code == ValidationFailed.status_code:
        return WS_POLICY_VIOLATION
    # No code means "that row does not exist", so say clean and let the frame
    # do the talking.
    return WS_NORMAL_CLOSURE


async def _close_with_error(
    websocket: WebSocket,
    error: AppError,
    *,
    exc_info: BaseException | None = None,
) -> None:
    """The websocket half of `_respond`: same log line, same envelope, no status
    line to put it on."""
    # Reuse the id the route already handed out, so one connection has one id.
    # A failure before the route ran has nothing to reuse.
    request_id = getattr(websocket.state, "request_id", None) or uuid.uuid4().hex[:12]
    log_error("WS", websocket.url.path, error, request_id, exc_info=exc_info)

    # Nothing left to send to, and send() on a dead socket raises -- which would
    # replace this error with an unrelated one.
    if websocket.client_state is WebSocketState.DISCONNECTED:
        return

    # A socket that was never accepted cannot carry a frame at all. Accepting
    # costs the rejection its status line and buys back the envelope.
    if websocket.client_state is WebSocketState.CONNECTING:
        await websocket.accept()

    await websocket.send_text(
        json.dumps(failure_frame(error.code, error.message, request_id, error.details))
    )
    await websocket.close(code=ws_close_code(error))


async def _deliver(
    conn: Request | WebSocket,
    error: AppError,
    *,
    exc_info: BaseException | None = None,
) -> JSONResponse | None:
    """Every handler's only exit. Starlette hands websocket scopes a WebSocket
    here, so the branch is required, not defensive."""
    if isinstance(conn, WebSocket):
        await _close_with_error(conn, error, exc_info=exc_info)
        return None
    return _respond(conn, error, exc_info=exc_info)


# errors raised on purpose
async def handle_app_error(
    conn: Request | WebSocket, exc: AppError
) -> JSONResponse | None:
    return await _deliver(conn, exc, exc_info=exc)


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

    return await _deliver(request, ValidationFailed(fields=fields))


# HTTPExceptions raised around the code (unmatched URL, 405)
# 405 is ROUTE_NOT_FOUND, not VALIDATION_FAILED -- a route is a path plus a
# method, and nothing about the payload was wrong.
_STATUS_TO_CODE = {
    404: ErrorCode.ROUTE_NOT_FOUND,
    405: ErrorCode.ROUTE_NOT_FOUND,
}


async def handle_http_exception(
    conn: Request | WebSocket, exc: StarletteHTTPException
) -> JSONResponse | None:
    if exc.status_code >= 500:
        code = ErrorCode.INTERNAL_ERROR
    else:
        code = _STATUS_TO_CODE.get(exc.status_code, ErrorCode.VALIDATION_FAILED)

    message = exc.detail if isinstance(exc.detail, str) else "Request failed."

    # No subclass fits -- Starlette picked the status
    return await _deliver(
        conn, AppError(message, status_code=exc.status_code, code=code)
    )


# the safety net for our own bugs
async def handle_unexpected(
    conn: Request | WebSocket, exc: Exception
) -> JSONResponse | None:
    """The request was fine, we broke, so 500.
    Exception text leaks table names, paths and query structure -- the client
    gets a request id, the traceback goes to the logs.
    """
    return await _deliver(conn, InternalError(), exc_info=exc)


# the rejection FastAPI would otherwise botch
async def handle_websocket_validation_error(
    websocket: WebSocket, exc: WebSocketRequestValidationError
) -> None:
    """Replaces FastAPI's default, which rejects the handshake with pydantic's
    raw error list as the close reason -- internals, on a channel the browser
    cannot read (a rejected handshake reaches JS as a bare 1006)."""
    await _close_with_error(
        websocket,
        ValidationFailed(
            fields=[
                {"field": _field_path(err.get("loc", [])), "reason": err.get("msg", "")}
                for err in exc.errors()
            ]
        ),
    )


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
