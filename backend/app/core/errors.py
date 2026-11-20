"""Domain exceptions + centralised handlers (safe error responses)."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    status_code = 400
    code = "domain_error"

    def __init__(self, message: str, detail: dict | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class NotFound(DomainError):
    status_code = 404
    code = "not_found"


class Conflict(DomainError):
    status_code = 409
    code = "conflict"


class InsufficientStock(Conflict):
    code = "insufficient_stock"


class Forbidden(DomainError):
    status_code = 403
    code = "forbidden"


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.code, "message": exc.message, "detail": exc.detail})

    @app.exception_handler(ValueError)
    async def _value(_: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"error": "invalid_value", "message": str(exc), "detail": {}})
