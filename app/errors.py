from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .reasons import REASONS, reason


class DomainError(ValueError):
    def __init__(self, code: str, message: str | None = None):
        self.code = code
        self.message = message or reason(code)
        super().__init__(self.message)


def install(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError):
        return JSONResponse(
            status_code=422,
            content={"error": exc.code, "message": exc.message},
        )

    @app.exception_handler(ValueError)
    async def value_error(request: Request, exc: ValueError):
        code = str(exc)
        if code not in REASONS:
            code = "INVALID_VALUE"
        return JSONResponse(
            status_code=422,
            content={"error": code, "message": reason(code)},
        )
