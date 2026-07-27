"""The error envelope. misc/docs/11-backend-api.md §2.2/§2.3 — built exactly,
per the brief: this is small and load-bearing."""

from __future__ import annotations

import hashlib
import traceback
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


@dataclass(frozen=True, slots=True)
class ApiError(Exception):
    code: str
    message: str
    http_status: int
    retriable: bool = False
    session_id: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def body(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "http_status": self.http_status,
                "session_id": self.session_id,
                "retriable": self.retriable,
                "detail": self.detail,
            }
        }


def not_found(what: str, *, session_id: str | None = None) -> ApiError:
    return ApiError(
        code="not_found",
        message=f"{what} does not exist.",
        http_status=status.HTTP_404_NOT_FOUND,
        session_id=session_id,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.body())

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [".".join(str(p) for p in e["loc"]) for e in exc.errors()]
        err = ApiError(
            code="schema_invalid",
            message="Request body failed validation.",
            http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"fields": fields},
        )
        return JSONResponse(status_code=err.http_status, content=err.body())

    @app.exception_handler(Exception)
    async def _internal_handler(_request: Request, exc: Exception) -> JSONResponse:
        digest = hashlib.sha256(traceback.format_exc().encode()).hexdigest()[:16]
        err = ApiError(
            code="internal",
            message="An internal error occurred.",
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"trace_digest": digest},
        )
        return JSONResponse(status_code=err.http_status, content=err.body())
