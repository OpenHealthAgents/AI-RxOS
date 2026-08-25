from __future__ import annotations

from typing import Literal

TaskStatus = Literal[
    "pending",
    "queued",
    "running",
    "retrying",
    "succeeded",
    "failed",
    "dead_letter",
    "cancelled",
]

_TERMINAL = {"succeeded", "failed", "cancelled"}
_ALLOWED: dict[str, set[str]] = {
    "pending": {"queued", "running", "cancelled"},
    "queued": {"running", "cancelled"},
    "running": {"succeeded", "failed", "retrying", "cancelled"},
    "retrying": {"queued", "running", "cancelled", "failed"},
    "succeeded": set(),
    "failed": {"retrying", "dead_letter"},
    "dead_letter": {"queued", "cancelled"},
    "cancelled": set(),
}


def is_terminal(status: str) -> bool:
    return status in _TERMINAL


def validate_transition(current: str, target: str) -> None:
    if target not in _ALLOWED.get(current, set()):
        raise ValueError(f"invalid task transition: {current} -> {target}")


def transition(task: object, target: TaskStatus) -> None:
    current = task.__dict__.get("status", task.__class__.__dict__.get("status"))
    if not isinstance(current, str):
        raise TypeError("task status is missing")
    validate_transition(current, target)
    task.__dict__["status"] = target
