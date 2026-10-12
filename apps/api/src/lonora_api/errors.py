from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from lonora_core.user_error import LonoraError
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException
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

    @app.exception_handler(ValidationError)
    async def invalid_payload(request: Request, error: ValidationError) -> JSONResponse:
        return JSONResponse({"code": "invalid_request"}, 422)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        return JSONResponse(
            {"code": "endpoint_not_found" if error.status_code == 404 else "request_failed"},
            error.status_code,
        )
