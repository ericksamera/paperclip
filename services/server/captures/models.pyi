from __future__ import annotations

"""
Type stub for the `captures` app models.

This file exists solely to make static checkers (Pylance/pyright/mypy)
aware of dynamic Django attributes such as reverse managers and fields
added via `.annotate(...)`.

It does not affect runtime.
"""

from datetime import datetime
from typing import Any, Iterable, Optional


# ---- Minimal helpers ---------------------------------------------------------

class _Manager: ...
class _RelatedManager:
    def all(self) -> Any: ...
    def count(self) -> int: ...
    def add(self, *objs: Any) -> None: ...
    def remove(self, *objs: Any) -> None: ...
    def filter(self, *args: Any, **kwargs: Any) -> Any: ...
    def order_by(self, *fields: str) -> Any: ...
    def only(self, *fields: str) -> Any: ...
    def exists(self) -> bool: ...


# ---- Reference model (subset of fields we touch) -----------------------------

class Reference:
    id: Any
    title: Optional[str]
    doi: Optional[str]
    issued_year: int | str | None

    # Enrichment targets we sometimes set
    container_title: Optional[str]
    authors: list[str] | None
    apa: Optional[str]
    csl: dict[str, Any] | None

    # Standard Django bits used in code/tests
    objects: _Manager
    def save(self, *, update_fields: Iterable[str] | None = ...) -> None: ...


# ---- Capture model (subset) --------------------------------------------------

class Capture:
    id: Any
    title: Optional[str]
    url: Optional[str]
    doi: Optional[str]
    year: int | str | None
    created_at: datetime
    site: Optional[str]

    # JSON-ish blobs we read from
    meta: dict[str, Any] | None
    csl: dict[str, Any] | None

    # Reverse/dynamic managers
    references: _RelatedManager
    collections: _RelatedManager

    objects: _Manager


# ---- Collection model (subset) ----------------------------------------------

class Collection:
    id: int
    name: str
    parent_id: int | None
    parent: "Collection | None"

    # Reverse manager to captures
    captures: _RelatedManager

    # Present after `.annotate(count=...)`; declared here so Pylance knows it.
    count: int

    objects: _Manager
