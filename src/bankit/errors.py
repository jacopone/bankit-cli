"""Errors with stable codes; the CLI maps each class to its exit status."""

from __future__ import annotations


class BankitError(Exception):
    code = "error"
    exit_status = 1

    def __init__(self, message: str, **details: object) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def to_dict(self) -> dict[str, object]:
        return {"error": self.code, "message": self.message, **self.details}


class UsageError(BankitError):
    code = "usage"
    exit_status = 2


class Unsupported(BankitError):
    code = "unsupported"
    exit_status = 3


class NotFound(BankitError):
    code = "not_found"
    exit_status = 4


class SourceError(BankitError):
    code = "source_error"
    exit_status = 5


class Rejected(SourceError):
    """The source's firewall answered with an HTML rejection page instead of data."""

    code = "rejected"


class OfflineMiss(BankitError):
    code = "offline_cache_miss"
    exit_status = 6
