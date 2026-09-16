from typing import Any, Optional
from fastapi import Request, status
from fastapi.responses import JSONResponse


class AppBaseException(Exception):
    """Base exception for domain application errors."""

    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(message)
        self.message = message
        self.details = details


class DataIngestionError(AppBaseException):
    """Raised when CSV ingestion or schema normalization fails."""
    pass


class InvalidQueryError(AppBaseException):
    """Raised when an incoming natural language or structured query cannot be parsed or validated."""
    pass


class LLMUnavailableError(AppBaseException):
    """Raised when the LLM service (Ollama) cannot be contacted or times out."""
    pass


class QueryExecutionError(AppBaseException):
    """Raised when query builder encounters an execution or execution constraint failure."""
    pass


class ResourceNotFoundError(AppBaseException):
    """Raised when an entity such as a ticket cannot be located."""
    pass


async def app_exception_handler(request: Request, exc: AppBaseException) -> JSONResponse:
    """Centralized exception handler for custom application exceptions."""
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_type = exc.__class__.__name__

    if isinstance(exc, ResourceNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, (InvalidQueryError, DataIngestionError)):
        status_code = status.HTTP_400_BAD_REQUEST
    elif isinstance(exc, LLMUnavailableError):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif isinstance(exc, QueryExecutionError):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    return JSONResponse(
        status_code=status_code,
        content={
            "error": error_type,
            "message": exc.message,
            "details": exc.details,
            "path": str(request.url.path),
        },
    )
