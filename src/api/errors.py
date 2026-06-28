"""Exception -> HTTP error mapping for the API layer."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException

from src.application.errors import (
    ApplicationError,
    ApplicationValidationError,
    ExternalServiceError,
    OperationCancelledError,
    PersistenceError,
    ResourceConflictError,
    ResourceNotFoundError,
)

_logger = logging.getLogger(__name__)


def application_error_to_http(error: ApplicationError) -> HTTPException:
    code = error.code
    message = error.public_message or error.message or code
    details: dict[str, Any] = error.details or {}
    if isinstance(error, ApplicationValidationError):
        status_code = 422
    elif isinstance(error, ResourceNotFoundError):
        status_code = 404
    elif isinstance(error, ResourceConflictError):
        status_code = 409
    elif isinstance(error, ExternalServiceError):
        status_code = 502
    elif isinstance(error, OperationCancelledError):
        status_code = 499  # Client closed request
    elif isinstance(error, PersistenceError):
        status_code = 500
    else:
        status_code = 500
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "details": details},
    )


def http_error(code: str, message: str, status_code: int, details: dict[str, Any] | None = None) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "details": details or {}},
    )
