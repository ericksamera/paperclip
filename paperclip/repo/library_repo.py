from __future__ import annotations

import re
from typing import Any

from ..db import rows_to_dicts
from ..parseutil import safe_int


def count_all_captures(db) -> int:
    row = db.execute("SELECT COUNT(1) AS n FROM captures").fetchone()
    return int(row["n"])


def _fts_query(q: str) -> str:
    """
    Conservative FTS5 query builder to avoid syntax errors.
    Tokenize to alnum and use prefix matches (term*).
    """
    q = (q or "").strip().lower()
    toks = re.findall(r"[a-z0-9]+", q)
    toks = [t for t in toks if t][:10]
    if not toks:
        return ""
    return " ".join(f"{t}*" for t in toks)


def search_captures(
    db,
    *,
    q: str,
    selected_col: str,
    page: int,
    page_size: int,
    fts_enabled: bool,
) -> tuple[list[dict[str, Any]], int, bool]:
    """
    Returns (captures, total, has_more).
    `captures` includes `meta_json` for caller-side formatting.
    """
    page = max(1, int(page))
    page_size = max(1, int(page_size))
    offset = max(0, (page - 1) * page_size)

    join_parts: list[str] = []
    where: list[str] = []
    params: list[Any] = []

    col_id = safe_int(selected_col)
    if col_id and col_id > 0:
        join_parts.append("JOIN collection_items ci ON ci.capture_id = cap.id")
        where.append("ci.collection_id = ?")
        params.append(col_id)

    if q:
        qlike = f"%{q}%"
        fts_q = _fts_query(q) if fts_enabled else ""

        if fts_enabled and fts_q:
            # Avoid JOIN+alias MATCH quirks: use correlated subquery against the FTS table.
            where.append(
                "("
                "cap.title LIKE ? OR cap.url LIKE ? OR cap.doi LIKE ? "
                "OR cap.id IN ("
                "  SELECT capture_id FROM capture_fts WHERE capture_fts MATCH ?"
                ")"
                ")"
            )
            params.extend([qlike, qlike, qlike, fts_q])
        else:
            where.append(
                "("
                "cap.title LIKE ? OR cap.url LIKE ? OR cap.doi LIKE ? "
                "OR cap.id IN ("
                "  SELECT capture_id FROM capture_text WHERE content_text LIKE ?"
                ")"
                ")"
            )
            params.extend([qlike, qlike, qlike, qlike])

    join_sql = (" " + " ".join(join_parts)) if join_parts else ""
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    total = db.execute(
        "SELECT COUNT(1) AS n FROM captures cap" + join_sql + where_sql,
        tuple(params),
    ).fetchone()["n"]

    rows = db.execute(
        """
        SELECT cap.id, cap.title, cap.url, cap.doi, cap.year, cap.container_title,
               cap.updated_at, cap.meta_json
        FROM captures cap
        """
        + join_sql
        + where_sql
        + " ORDER BY cap.updated_at DESC LIMIT ? OFFSET ?",
        tuple(params + [page_size, offset]),
    ).fetchall()

    captures = rows_to_dicts(rows)
    has_more = offset + len(captures) < total
    return captures, int(total), has_more
