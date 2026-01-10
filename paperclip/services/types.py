from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ActionResult:
    """Standard result object for service-layer mutations."""

    ok: bool
    message: str
    category: str = "success"  # success | warning | error
    changed_count: int = 0
    cleanup_paths: list[str] = field(default_factory=list)


def ok(
    message: str, *, changed_count: int = 0, cleanup_paths: list[str] | None = None
) -> ActionResult:
    return ActionResult(
        ok=True,
        message=message,
        category="success",
        changed_count=changed_count,
        cleanup_paths=list(cleanup_paths or []),
    )


def warn(message: str) -> ActionResult:
    return ActionResult(ok=False, message=message, category="warning")


def err(message: str) -> ActionResult:
    return ActionResult(ok=False, message=message, category="error")
