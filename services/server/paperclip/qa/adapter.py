# services/server/paperclip/qa/adapter.py
"""
QA adapter: isolates the QA engine from your models and search layer.

What changed:
- Uses your canonical retriever: captures.search.search_ids_for_query(
      question, restrict_to_ids=set(...), mode=..., limit=...
  )
  so collection scoping is handled inside the search rails.
- If that isn't available, falls back to your semantic/text functions and
  intersects results with the collection.
- Safe final fallback: plain FTS + intersection (no fragile ORM 'abstract' filters).
- Chunk text comes from reduced view + keywords for better RAG context.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from captures.models import Capture, Collection
from captures.reduced_view import read_reduced_view

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
        # year is often a CharField; coerce if numeric
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
            paras = sections.get("abstract_or_body")
            if isinstance(paras, list) and paras:
                parts.append(" ".join([str(p) for p in paras[:6] if p]))

        meta = c.meta or {}
        kw = meta.get("keywords") or []
        if isinstance(kw, list) and kw:
            parts.append(" ".join([str(k) for k in kw if k]))

        if len(parts) <= 1:  # no abstract/body picked up
            csl = c.csl or {}
            if meta.get("abstract"):
                parts.append(str(meta["abstract"]))
            elif isinstance(csl, dict) and csl.get("abstract"):
                parts.append(str(csl["abstract"]))

        return "\n\n".join([p for p in parts if p])

    # ---- retrieval ----
    def _intersect_ordered(
        self, ranked_ids: list[PK], scope: Iterable[PK], limit: int
    ) -> list[PK]:
        S = {str(x) for x in scope}
        out = [pk for pk in ranked_ids if str(pk) in S]
        return out[: max(1, int(limit))]

    def _via_search_ids_for_query(
        self, question: str, restrict_to_ids: Iterable[PK], limit: int, mode: str
    ) -> list[PK]:
        """
        Preferred path: your canonical retriever that already supports restrict_to_ids.
        """
        try:
            from captures.search import search_ids_for_query  # type: ignore
        except Exception:
            return []
        ranked = list(
            search_ids_for_query(
                question,
                restrict_to_ids=set(restrict_to_ids),
                mode=mode,
                limit=limit,
            )
        )
        return ranked or []

    def _via_semantic_or_fts(
        self, question: str, restrict_to_ids: Iterable[PK], limit: int, mode: str
    ) -> list[PK]:
        """
        Fallback path: use project rails without restrict, then intersect.
        """
        q = (question or "").strip()
        if not q:
            return []
        # try semantic/hybrid first
        try:
            if mode == "text":
                from captures.search import search_ids as fts_search

                ranked = list(fts_search(q, limit=max(2000, limit)))
            elif mode == "semantic":
                from captures.semantic import search_ids_semantic

                ranked = list(search_ids_semantic(q, k=max(2000, limit)))
            else:
                from captures.semantic import rrf_hybrid_ids

                ranked = list(rrf_hybrid_ids(q, limit=max(2000, limit)))
            if ranked:
                return self._intersect_ordered(ranked, restrict_to_ids, limit)
        except Exception:
            pass
        # plain FTS as the final fallback
        try:
            from captures.search import search_ids as fts_search
        except Exception:
            return []
        ranked = list(fts_search(q, limit=max(2000, limit)))
        return self._intersect_ordered(ranked, restrict_to_ids, limit)

    def hybrid_search(
        self,
        question: str,
        restrict_to_ids: Iterable[PK],
        limit: int,
        mode: str = "hybrid",
    ) -> list[PK]:
        # 1) Prefer the canonical retriever with restrict_to_ids
        ranked = self._via_search_ids_for_query(
            question, restrict_to_ids, limit, mode=mode.lower()
        )
        if ranked:
            return ranked
        # 2) Then semantic/hybrid/text rails with intersection
        return self._via_semantic_or_fts(
            question, restrict_to_ids, limit, mode=mode.lower()
        )
