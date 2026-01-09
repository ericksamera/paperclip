from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..db import rows_to_dicts
from ..parseutil import safe_int


def count_all_captures(db) -> int:
    row = db.execute("SELECT COUNT(1) AS n FROM captures").fetchone()
    return int(row["n"])


def _fts_query(q: str) -> str:
    """Conservative FTS5 query builder to avoid syntax errors."""
    q = (q or "").strip().lower()
    toks = re.findall(r"[a-z0-9]+", q)
    toks = [t for t in toks if t][:10]
    if not toks:
        return ""
    return " ".join(f"{t}*" for t in toks)


@dataclass
class LibraryQuery:
    q: str = ""
    selected_col: str = ""
    fts_enabled: bool = False

    join_parts: list[str] = field(default_factory=list)
    where_parts: list[str] = field(default_factory=list)
    params: list[Any] = field(default_factory=list)

    def build(self) -> None:
        self.join_parts.clear()
        self.where_parts.clear()
        self.params.clear()

        col_id = safe_int(self.selected_col)
        if col_id and col_id > 0:
            self.join_parts.append("JOIN collection_items ci ON ci.capture_id = cap.id")
            self.where_parts.append("ci.collection_id = ?")
            self.params.append(col_id)

        q = (self.q or "").strip()
        if q:
            qlike = f"%{q}%"
            fts_q = _fts_query(q) if self.fts_enabled else ""

            if self.fts_enabled and fts_q:
                # Avoid JOIN+alias MATCH quirks: use correlated subquery against the FTS table.
                self.where_parts.append(
                    "("
                    "cap.title LIKE ? OR cap.url LIKE ? OR cap.doi LIKE ? "
                    "OR cap.id IN (SELECT capture_id FROM capture_fts WHERE capture_fts MATCH ?)"
                    ")"
                )
                self.params.extend([qlike, qlike, qlike, fts_q])
            else:
                self.where_parts.append(
                    "("
                    "cap.title LIKE ? OR cap.url LIKE ? OR cap.doi LIKE ? "
                    "OR cap.id IN (SELECT capture_id FROM capture_text WHERE content_text LIKE ?)"
                    ")"
                )
                self.params.extend([qlike, qlike, qlike, qlike])

    @property
    def join_sql(self) -> str:
        return (" " + " ".join(self.join_parts)) if self.join_parts else ""

    @property
    def where_sql(self) -> str:
        return (" WHERE " + " AND ".join(self.where_parts)) if self.where_parts else ""


def search_captures(
    db,
    *,
    q: str,
    selected_col: str,
    page: int,
    page_size: int,
    fts_enabled: bool,
) -> tuple[list[dict[str, Any]], int, bool]:
    """Returns (captures, total, has_more)."""
    page = max(1, int(page))
    page_size = max(1, int(page_size))
    offset = max(0, (page - 1) * page_size)

    builder = LibraryQuery(q=q, selected_col=selected_col, fts_enabled=fts_enabled)
    builder.build()

    total = db.execute(
        "SELECT COUNT(1) AS n FROM captures cap" + builder.join_sql + builder.where_sql,
        tuple(builder.params),
    ).fetchone()["n"]

    rows = db.execute(
        (
            "SELECT cap.id, cap.title, cap.url, cap.doi, cap.year, cap.container_title, "
            "cap.updated_at, cap.meta_json "
            "FROM captures cap"
            + builder.join_sql
            + builder.where_sql
            + " ORDER BY cap.updated_at DESC LIMIT ? OFFSET ?"
        ),
        tuple(builder.params + [page_size, offset]),
    ).fetchall()

    captures = rows_to_dicts(rows)
    has_more = offset + len(captures) < total
    return captures, int(total), has_more
