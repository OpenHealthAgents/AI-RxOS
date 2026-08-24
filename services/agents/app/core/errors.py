from __future__ import annotations

from typing import Any


class AIPlatformError(RuntimeError):
    def __init__(self, message: str, *, code: str, operation: str, retriable: bool = False, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.operation = operation
        self.retriable = retriable
        self.details = details or {}

    def as_dict(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": str(self), "operation": self.operation, "retriable": self.retriable, "details": self.details}}


class TimeoutError(AIPlatformError):
    def __init__(self, operation: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(f"{operation} timed out", code="TIMEOUT", operation=operation, retriable=True, details=details)
