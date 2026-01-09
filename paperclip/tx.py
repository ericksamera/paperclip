from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from .db import get_db


@contextmanager
def db_tx() -> Iterator[object]:
    """
    Context manager for a single request-scoped transaction.
    - commits if the block exits cleanly
    - rollbacks if an exception occurs
    """
    db = get_db()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    else:
        db.commit()
