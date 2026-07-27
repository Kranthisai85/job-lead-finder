class RepositoryError(Exception):
    """Base exception for repository-level failures."""


class NotFoundError(RepositoryError):
    """Raised when a requested record does not exist."""


class DuplicateRecordError(RepositoryError):
    """Raised when a unique constraint is violated."""


class DatabaseConnectionError(RepositoryError):
    """Raised when database connectivity or initialization fails."""
