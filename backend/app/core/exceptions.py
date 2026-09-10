"""
ABCI-MI Core Exceptions and Error Handlers
Provides centralized domain and infrastructure exceptions with standard API response formats.
"""

from typing import Any, Dict, List, Optional, Union
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger("exceptions")


class AppException(Exception):
    """Base application exception from which all domain errors inherit."""

    def __init__(
        self,
        message: str = "An unexpected application error occurred",
        code: str = "INTERNAL_SERVER_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Union[Dict[str, Any], List[Any], str]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details


# Compatibility Aliases
CoreException = AppException
DatabaseException = AppException


class NotFoundException(AppException):
    """Resource not found (404)."""

    def __init__(
        self,
        message: str = "Resource not found",
        code: str = "RESOURCE_NOT_FOUND",
        details: Optional[Union[Dict[str, Any], str]] = None,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )


class BadRequestException(AppException):
    """Bad client request (400)."""

    def __init__(
        self,
        message: str = "Bad request",
        code: str = "BAD_REQUEST",
        details: Optional[Union[Dict[str, Any], str]] = None,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
        )


class UnauthorizedException(AppException):
    """Authentication required / invalid credentials (401)."""

    def __init__(
        self,
        message: str = "Authentication credentials were not provided or are invalid",
        code: str = "UNAUTHORIZED",
        details: Optional[Union[Dict[str, Any], str]] = None,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
        )


class ForbiddenException(AppException):
    """Permission denied (403)."""

    def __init__(
        self,
        message: str = "You do not have permission to access this resource",
        code: str = "FORBIDDEN",
        details: Optional[Union[Dict[str, Any], str]] = None,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_403_FORBIDDEN,
            details=details,
        )


class ConflictException(AppException):
    """Resource state conflict (409)."""

    def __init__(
        self,
        message: str = "Conflict with the current state of the resource",
        code: str = "RESOURCE_CONFLICT",
        details: Optional[Union[Dict[str, Any], str]] = None,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


class ValidationException(AppException):
    """Input validation error (422)."""

    def __init__(
        self,
        message: str = "Validation failed for one or more fields",
        code: str = "VALIDATION_ERROR",
        details: Optional[Union[Dict[str, Any], List[Any], str]] = None,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class InfrastructureException(AppException):
    """Underlying infrastructure (DB, Redis, Qdrant) error (503)."""

    def __init__(
        self,
        message: str = "Infrastructure service communication failed",
        code: str = "INFRASTRUCTURE_ERROR",
        details: Optional[Union[Dict[str, Any], str]] = None,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details=details,
        )


class ServiceUnavailableException(AppException):
    """Service or component temporarily unavailable (503)."""

    def __init__(
        self,
        message: str = "Service temporarily unavailable",
        code: str = "SERVICE_UNAVAILABLE",
        details: Optional[Union[Dict[str, Any], str]] = None,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details=details,
        )


# -----------------------------------------------------------------------------
# FastAPI Exception Handlers Registration
# -----------------------------------------------------------------------------
def register_exception_handlers(app: FastAPI) -> None:
    """Registers standard JSON response error handlers on the FastAPI application."""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        logger.warning(
            f"AppException occurred: {exc.code} - {exc.message} (status: {exc.status_code}) on {request.method} {request.url.path}"
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                },
            },
        )

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    async def validation_exception_handler(
        request: Request, exc: Union[RequestValidationError, ValidationError]
    ) -> JSONResponse:
        logger.warning(
            f"Validation error on {request.method} {request.url.path}: {exc.errors()}"
        )
        serializable_errors = []
        for err in exc.errors():
            err_copy = dict(err)
            if "ctx" in err_copy and isinstance(err_copy["ctx"], dict):
                err_copy["ctx"] = {
                    k: str(v) if isinstance(v, (Exception, BaseException)) else v
                    for k, v in err_copy["ctx"].items()
                }
            serializable_errors.append(err_copy)

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "success": False,
                "error": {
                    "code": "REQUEST_VALIDATION_ERROR",
                    "message": "Invalid request payload or query parameters",
                    "details": serializable_errors,
                },
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        logger.warning(
            f"HTTPException {exc.status_code} on {request.method} {request.url.path}: {exc.detail}"
        )
        code = f"HTTP_{exc.status_code}"
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            code = "NOT_FOUND"
        elif exc.status_code == status.HTTP_403_FORBIDDEN:
            code = "FORBIDDEN"
        elif exc.status_code == status.HTTP_401_UNAUTHORIZED:
            code = "UNAUTHORIZED"

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": {
                    "code": code,
                    "message": str(exc.detail),
                    "details": None,
                },
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            f"Unhandled exception on {request.method} {request.url.path}: {str(exc)}"
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An internal server error occurred. Please contact administrator.",
                    "details": str(exc) if app.debug else None,
                },
            },
        )
