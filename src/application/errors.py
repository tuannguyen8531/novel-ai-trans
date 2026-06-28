"""Application-level error hierarchy.

Adapters (CLI, API) translate these exceptions into their own output formats.
Workflows in :mod:`src.application` raise these instead of HTTPException or
calling :func:`sys.exit`.
"""

from __future__ import annotations

from typing import Any


class ApplicationError(Exception):
    """Base class for application-layer errors."""

    code: str = "application_error"
    public_message: str = "Application error."

    def __init__(self, message: str | None = None, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message or self.public_message)
        self.message = message or self.public_message
        self.details = details or {}


class ApplicationValidationError(ApplicationError):
    code = "validation_error"
    public_message = "Invalid input."


class ResourceNotFoundError(ApplicationError):
    code = "not_found"
    public_message = "Resource not found."


class ResourceConflictError(ApplicationError):
    code = "conflict"
    public_message = "Resource conflict."


class ExternalServiceError(ApplicationError):
    code = "external_service_error"
    public_message = "External service error."


class PersistenceError(ApplicationError):
    code = "persistence_error"
    public_message = "Could not read or write required data."


class OperationCancelledError(ApplicationError):
    code = "cancelled"
    public_message = "Operation cancelled."


__all__ = [
    "ApplicationError",
    "ApplicationValidationError",
    "ResourceNotFoundError",
    "ResourceConflictError",
    "ExternalServiceError",
    "PersistenceError",
    "OperationCancelledError",
]
