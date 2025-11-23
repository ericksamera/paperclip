from __future__ import annotations

import json
from contextlib import suppress
from typing import Iterable, List

from django.conf import settings

from captures.dedup import find_near_duplicates


DUPE_FILE = settings.ANALYSIS_DIR / "dupes.json"
IGNORED_FILE = settings.ANALYSIS_DIR / "dupes_ignored.json"


def group_key(ids: Iterable[str]) -> str:
    """
    Stable group key string for a set/list of ids (used to track ignored groups).
    """
    return ",".join(sorted(str(i) for i in ids))


def read_dupes() -> List[List[str]]:
    """
    Read duplicate groups from dupes.json, returning [] on any error.
    Shape: {"groups": [ ["id1","id2"], ... ]}.
    """
    if not DUPE_FILE.exists():
        return []
    with suppress(Exception):
        data = json.loads(DUPE_FILE.read_text(encoding="utf-8"))
        groups = data.get("groups") or []
        if isinstance(groups, list):
            return groups
    return []


def ignored_set() -> set[str]:
    """
    Read dupes_ignored.json -> set of group keys.
    """
    if not IGNORED_FILE.exists():
        return set()
    try:
        data = json.loads(IGNORED_FILE.read_text(encoding="utf-8"))
        return set(data.get("ignored") or [])
    except Exception:
        return set()


def write_ignored(s: set[str]) -> None:
    """
    Persist ignored group keys back to dupes_ignored.json.
    """
    IGNORED_FILE.parent.mkdir(parents=True, exist_ok=True)
    IGNORED_FILE.write_text(
        json.dumps({"ignored": sorted(s)}, indent=2), encoding="utf-8"
    )


def scan_and_write_dupes(threshold: float = 0.85) -> List[List[str]]:
    """
    Run MinHash/LSH duplicate scan and persist dupes.json.

    Returns the groups so callers (view / management command) can report counts.
    """
    groups = find_near_duplicates(threshold=threshold)
    DUPE_FILE.parent.mkdir(parents=True, exist_ok=True)
    DUPE_FILE.write_text(json.dumps({"groups": groups}, indent=2), "utf-8")
    return groups
