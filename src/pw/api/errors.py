"""API error envelope `{error:{code,message}}` and exception handlers."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from pw.security.errors import SecurityError


class RunNotFound(SecurityError):
    status_code = 404
    code = "E-13"


class RunNotReady(SecurityError):
    status_code = 409
    code = "E-07"


class InvalidRequest(SecurityError):
    status_code = 422
    code = "E-04"


def error_response(error: SecurityError) -> JSONResponse:
    headers: dict[str, str] = {}
    retry_after = getattr(error, "retry_after_s", None)
    if error.status_code == 429:
        headers["Retry-After"] = str(int(retry_after)) if retry_after else "60"
    return JSONResponse(error.to_payload(), status_code=error.status_code, headers=headers)


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(SecurityError)
    async def _security(_: Request, exc: SecurityError) -> JSONResponse:
        return error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(InvalidRequest("Invalid request."))


__all__ = ["InvalidRequest", "RunNotFound", "RunNotReady", "error_response", "install_handlers"]
