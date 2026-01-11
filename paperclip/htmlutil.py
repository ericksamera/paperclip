from __future__ import annotations

from typing import Iterable

from bs4 import Tag


def safe_decompose(tag: Tag) -> None:
    """Best-effort removal of a BeautifulSoup tag."""
    try:
        tag.decompose()
    except Exception:
        try:
            tag.clear()
        except Exception:
            pass


def _class_str(tag: Tag) -> str:
    cls_val = tag.get("class")
    if isinstance(cls_val, list):
        return " ".join([str(x) for x in cls_val if x is not None])
    if isinstance(cls_val, str):
        return cls_val
    return ""


def _id_str(tag: Tag) -> str:
    bid = tag.get("id")
    return bid if isinstance(bid, str) else ""


def strip_noise(
    root: Tag,
    *,
    strip_tags: Iterable[str] | None = None,
    skip_class_fragments: Iterable[str] = (),
    skip_id_fragments: Iterable[str] = (),
    max_text_len: int = 400,
) -> None:
    """Remove obvious boilerplate / non-content nodes from an HTML subtree."""
    tags = set(strip_tags or [])
    if tags:
        for t in root.find_all(list(tags)):
            if isinstance(t, Tag):
                safe_decompose(t)

    cls_frags = tuple(str(x).lower() for x in skip_class_fragments if x)
    id_frags = tuple(str(x).lower() for x in skip_id_fragments if x)
    if not cls_frags and not id_frags:
        return

    for bad in root.find_all(True):
        try:
            if not isinstance(bad, Tag):
                continue

            hay_cls = _class_str(bad).lower()
            hay_id = _id_str(bad).lower()

            hit = (cls_frags and any(k in hay_cls for k in cls_frags)) or (
                id_frags and any(k in hay_id for k in id_frags)
            )
            if not hit:
                continue

            if len(bad.get_text(" ", strip=True)) < max_text_len:
                safe_decompose(bad)
        except Exception:
            continue
