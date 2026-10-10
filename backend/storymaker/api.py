"""Shared API conventions (spec 01.4): the /api router and one error shape.

Every error response looks like {"error": {"code": "...", "message": "..."}}.
The code is for the app's logic; the message is safe to show to people.
"""

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

API_PREFIX = "/api"

# Every endpoint is registered on this router (directly or via a sub-router).
api_router = APIRouter(prefix=API_PREFIX)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
    return error_response(exc.status, exc.code, exc.message)


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(part) for part in first.get("loc", ()) if part not in ("body", "query", "path"))
    reason = first.get("msg", "invalid value")
    message = f"Invalid request: '{field}': {reason}." if field else f"Invalid request: {reason}."
    return error_response(422, "validation_error", message)


_HTTP_CODES = {404: ("not_found", "Nothing here."), 405: ("method_not_allowed", "That action isn't allowed here.")}


async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code, message = _HTTP_CODES.get(exc.status_code, ("http_error", "The request couldn't be handled."))
    return error_response(exc.status_code, code, message)


async def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # No details in the response. Starlette re-raises the exception after this
    # handler, so the server (uvicorn) logs the full traceback.
    return error_response(500, "internal_error", "Something went wrong on our side. Please try again.")


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unexpected_error)
