from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from lonora_core.user_error import LonoraError
from sqlalchemy.exc import IntegrityError
from starlette.responses import JSONResponse


def install_errors(app: FastAPI) -> None:
    @app.exception_handler(LonoraError)
    async def domain_error(request: Request, error: LonoraError) -> JSONResponse:
        return JSONResponse(
            {"code": error.code, "request_id": getattr(request.state, "request_id", None)},
            error.status,
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            {
                "code": "invalid_request",
                "fields": [
                    {"path": [str(value) for value in item["loc"]], "code": item["type"]}
                    for item in error.errors()
                ],
            },
            422,
        )

    @app.exception_handler(IntegrityError)
    async def conflict(request: Request, error: IntegrityError) -> JSONResponse:
        return JSONResponse({"code": "resource_conflict"}, 409)
