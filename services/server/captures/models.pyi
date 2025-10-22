# services/server/captures/models.pyi
from __future__ import annotations
from datetime import datetime
from typing import Any, Iterable, Optional

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

class Reference:
    id: Any
    title: Optional[str]
    doi: Optional[str]
    doi_norm: Optional[str]  # NEW
    issued_year: int | str | None
    container_title: Optional[str]
    authors: list[str] | None
    apa: Optional[str]
    csl: dict[str, Any] | None
    objects: _Manager
    def save(self, *, update_fields: Iterable[str] | None = ...) -> None: ...

class Capture:
    id: Any
    title: Optional[str]
    url: Optional[str]
    doi: Optional[str]
    doi_norm: Optional[str]  # NEW
    year: int | str | None
    created_at: datetime
    site: Optional[str]
    meta: dict[str, Any] | None
    csl: dict[str, Any] | None
    references: _RelatedManager
    collections: _RelatedManager
    objects: _Manager
    def save(self, *args: Any, **kwargs: Any) -> None: ...

class Collection:
    id: int
    name: str
    parent_id: int | None
    parent: "Collection | None"
    captures: _RelatedManager
