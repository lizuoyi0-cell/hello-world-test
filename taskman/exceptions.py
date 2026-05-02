"""Custom exceptions for the taskman application.

Each error class corresponds to a specific failure category so callers can
catch precisely the situations they want to handle.
"""


class TaskmanError(Exception):
    """Base class for all taskman errors."""


class ValidationError(TaskmanError):
    """Raised when user input fails validation (empty fields, bad formats)."""


class AuthError(TaskmanError):
    """Raised for authentication and authorization failures."""


class NotFoundError(TaskmanError):
    """Raised when a requested entity does not exist."""


class PermissionError_(TaskmanError):
    """Raised when a user lacks permission for an operation.

    Suffixed with an underscore to avoid shadowing the built-in
    ``PermissionError``.
    """


class DuplicateError(TaskmanError):
    """Raised when a uniqueness constraint would be violated."""


class StorageError(TaskmanError):
    """Raised for database / persistence failures."""
