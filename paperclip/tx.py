from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from .db import get_db


@contextmanager
def db_tx(*, commit: bool = True) -> Iterator[sqlite3.Connection]:
    """
    Context manager for a single request-scoped transaction.

    - If `commit=True` (default): commits if the block exits cleanly.
    - Always rollbacks on exception.
    - If `commit=False`: does not commit on success (useful for read-only blocks).
    """
    db: sqlite3.Connection = get_db()
    try:
        yield db
    except Exception:
        try:
            db.rollback()
        finally:
            raise
    else:
        if commit:
            db.commit()
