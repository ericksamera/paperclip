from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flask import Flask

from .apiutil import api_error


@dataclass(frozen=True)
class APIError(Exception):
    status: int
    code: str
    message: str
    details: dict[str, Any] | None = None


class BadRequest(APIError):
    def __init__(
        self,
        *,
        code: str = "bad_request",
        message: str = "Bad request",
        details: dict[str, Any] | None = None,
        status: int = 400,
    ) -> None:
        super().__init__(status=status, code=code, message=message, details=details)


class NotFound(APIError):
    def __init__(
        self,
        *,
        code: str = "not_found",
        message: str = "Not found",
        details: dict[str, Any] | None = None,
        status: int = 404,
    ) -> None:
        super().__init__(status=status, code=code, message=message, details=details)


class Conflict(APIError):
    def __init__(
        self,
        *,
        code: str = "conflict",
        message: str = "Conflict",
        details: dict[str, Any] | None = None,
        status: int = 409,
    ) -> None:
        super().__init__(status=status, code=code, message=message, details=details)


class InternalError(APIError):
    def __init__(
        self,
        *,
        code: str = "internal_error",
        message: str = "Internal error",
        details: dict[str, Any] | None = None,
        status: int = 500,
    ) -> None:
        super().__init__(status=status, code=code, message=message, details=details)


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(APIError)
    def _handle_api_error(err: APIError):
        return api_error(
            status=int(err.status),
            code=str(err.code),
            message=str(err.message),
            details=err.details,
        )
