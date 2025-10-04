# services/server/captures/tests/test_search_ensure_fts_guard.py
from __future__ import annotations

from unittest import TestCase

from captures.search import ensure_fts


class _DummyCursor:
    def __init__(self, sink):
        self.sink = sink

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, *params):
        self.sink.append(sql)


class _Conn:
    def __init__(self, vendor):
        self.vendor = vendor
        self.executed = []

    def cursor(self):
        return _DummyCursor(self.executed)


class EnsureFtsGuardTests(TestCase):
    def test_noop_for_non_sqlite(self):
        conn = _Conn("postgresql")
        ensure_fts(conn)
        self.assertEqual(conn.executed, [], "Should not execute SQL for non-sqlite")

    def test_executes_for_sqlite(self):
        conn = _Conn("sqlite")
        ensure_fts(conn)
        self.assertTrue(
            any("CREATE VIRTUAL TABLE" in s for s in conn.executed),
            "Should create FTS table on sqlite",
        )
