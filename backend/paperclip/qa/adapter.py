from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence, Set

from django.db.models import Q

from captures.models import Capture, Collection
from captures.reduced_view import read_reduced_view  # uses artifacts on disk

"""
QA adapter: isolates the QA engine from your models and search layer.

Behavior:
- Prefer your canonical retriever in captures.search:
    search_ids_for_query(question, restrict_to_ids=..., mode=..., limit=...)
  If it isn't available or has a different signature, try common alternates,
  then safely fall back to simple ORM filtering intersected with the collection.
- Chunk text for RAG: reduced view (title, abstract/body) + keywords + meta.
"""

PK = int | str


@dataclass
class CaptureMeta:
    id: PK
    title: str
    year: int | None
    doi: str | None


class BaseAdapter:
    def collection_capture_ids(self, collection_id: int) -> list[PK]:
        raise NotImplementedError

    def capture_meta(self, capture_id: PK) -> CaptureMeta:
        raise NotImplementedError

    def capture_text(self, capture_id: PK) -> str:
        raise NotImplementedError

    def hybrid_search(
        self,
        question: str,
        restrict_to_ids: Iterable[PK],
        limit: int,
        mode: str = "hybrid",
    ) -> list[PK]:
        raise NotImplementedError


class SimpleORMAdapter(BaseAdapter):
    """
    Minimal adapter wired to your models; retrieval prefers project rails
    and falls back safely when needed.
    """

    # ---- collection scope ----
    def _get_collection_qs(self, collection_id: int):
        col = Collection.objects.get(pk=collection_id)
        return col.captures.all()

    def collection_capture_ids(self, collection_id: int) -> list[PK]:
        # Preserve native PK types (UUID/int) to match your search rails
        return list(self._get_collection_qs(collection_id).values_list("id", flat=True))

    # ---- metadata ----
    def capture_meta(self, capture_id: PK) -> CaptureMeta:
        c = Capture.objects.get(pk=capture_id)
        title = (c.title or "").strip() or "(untitled)"
        year_val: int | None = None
        try:
            if c.year:
                year_val = int(str(c.year))
        except Exception:
            year_val = None
        doi_val = (c.doi or "").strip() or None
        return CaptureMeta(id=c.id, title=title, year=year_val, doi=doi_val)

    # ---- text for chunking ----
    def capture_text(self, capture_id: PK) -> str:
        """
        Title + abstract (reduced view) + first body paras + keywords + meta/CSL abstracts.
        """
        c = Capture.objects.get(pk=capture_id)
        parts: list[str] = []
        if c.title:
            parts.append(str(c.title))

        view = read_reduced_view(str(c.id)) or {}
        sections = view.get("sections") or {}
        if isinstance(sections, dict):
            abs_txt = sections.get("abstract")
            if isinstance(abs_txt, str) and abs_txt.strip():
                parts.append(abs_txt.strip())

            # include first body-ish paras
            paras = sections.get("abstract_or_body")
            if isinstance(paras, list) and paras:
                parts.append(" ".join([str(p) for p in paras[:6] if p]))

        # keywords from meta
        meta = c.meta or {}
        kw = meta.get("keywords") or []
        if isinstance(kw, (list, tuple)):
            parts.append(" ".join([str(k) for k in kw if k]))

        # lightweight CSL/extra abstracts if present
        for key in ("csl", "extra", "notes"):
            v = meta.get(key)
            if isinstance(v, dict):
                ab = v.get("abstract") or v.get("Abstract")
                if isinstance(ab, str) and ab.strip():
                    parts.append(ab.strip())

        return "\n\n".join([p for p in parts if p])

    # ---- hybrid search ----
    def hybrid_search(
        self,
        question: str,
        restrict_to_ids: Iterable[PK],
        limit: int,
        mode: str = "hybrid",
    ) -> list[PK]:
        restrict: Set[str] = {str(x) for x in restrict_to_ids}

        # 1) Try canonical search rails in captures.search with several function names
        try:
            from importlib import import_module

            cs = import_module("captures.search")
            candidates: list[str] = [
                "search_ids_for_query",  # preferred
                "search_ids",
                "hybrid_search",
                "semantic_search_ids",
                "semantic_search",  # may return objs; we coerce to ids
            ]
            for name in candidates:
                fn = getattr(cs, name, None)
                if not callable(fn):
                    continue
                try:
                    # Attempt with rich kwargs first
                    res = fn(
                        question,
                        restrict_to_ids=restrict,
                        limit=limit,
                        mode=mode,
                    )
                except TypeError:
                    # Fallback to simpler signatures
                    try:
                        res = fn(question, restrict, limit)
                    except TypeError:
                        res = fn(question)

                # Coerce to a list of IDs and intersect with restrict
                ids = [str(getattr(r, "id", r)) for r in (res or [])]
                ids = [i for i in ids if i in restrict] if restrict else ids
                if ids:
                    # Preserve input types where possible
                    return _coerce_ids_to_native(ids, desired=restrict, limit=limit)
        except Exception:
            pass

        # 2) Safe final fallback: OR over a few text-ish fields and intersect with restrict
        q = (
            Q(title__icontains=question)
            | Q(meta__abstract__icontains=question)
            | Q(meta__keywords__icontains=question)
        )
        qs = Capture.objects.filter(q)
        if restrict:
            qs = qs.filter(id__in=list(restrict))
        ids = list(qs.values_list("id", flat=True)[: max(1, int(limit))])
        return list(ids)


def _coerce_ids_to_native(
    ids: Sequence[str], desired: Set[str], limit: int
) -> list[PK]:
    """
    Keep IDs in their native type where possible: if the DB holds UUIDs as strings,
    leave them as strings; if they are integers, attempt int() coercion.
    """
    out: list[PK] = []
    for i in ids[: max(1, int(limit))]:
        try:
            # Only coerce if it looks like a pure int (avoid UUIDs)
            if i.isdigit():
                out.append(int(i))
            else:
                out.append(i)
        except Exception:
            out.append(i)
    return out
