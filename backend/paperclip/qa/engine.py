# services/server/paperclip/qa/engine.py
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Any

from django.core.cache import cache

from .adapter import BaseAdapter, SimpleORMAdapter


# ---- OpenAI client (modern SDK) ----
def _openai_chat(
    messages: list[dict[str, str]], model: str, temperature: float = 0.2
) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not configured.")
    try:
        from openai import OpenAI
    except Exception as e:
        raise RuntimeError("The 'openai' package is not installed.") from e
    client = OpenAI(api_key=api_key, base_url=os.getenv("OPENAI_BASE_URL"))
    resp = client.chat.completions.create(
        model=model, temperature=temperature, messages=messages
    )
    return resp.choices[0].message.content or ""


# ---- Chunking ----
def _chunk_text(s: str, max_chars: int = 1200, overlap: int = 200) -> list[str]:
    s = s.strip()
    if not s:
        return []
    chunks: list[str] = []
    start = 0
    n = len(s)
    while start < n:
        end = min(start + max_chars, n)
        chunk = s[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        start = max(0, end - overlap)
    return chunks


SYSTEM_PROMPT = (
    "You are a careful literature review assistant. Use ONLY the supplied context. "
    "Synthesize concise answers. Always include bracketed citations like [1], [2] tied "
    "to the numbered sources provided. If information is not in the context, say you do not know."
)


@dataclass
class Citation:
    n: int
    id: int
    title: str
    year: int | None
    doi: str | None


class QAEngine:
    def __init__(self, adapter: BaseAdapter | None = None):
        self.adapter = adapter or SimpleORMAdapter()
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        # Context sizing knobs
        self.k_docs = int(os.getenv("QA_K_DOCS", "12"))
        self.max_chunks = int(os.getenv("QA_MAX_CHUNKS", "10"))
        self.chars_per_chunk = int(os.getenv("QA_CHARS_PER_CHUNK", "1100"))

    def _cache_key(self, collection_id: int, question: str, seed_ids: list[int]) -> str:
        raw = f"{collection_id}|{question}|{','.join(map(str, seed_ids))}"
        return "qa:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]

    def ask(
        self, collection_id: int, question: str, mode: str = "hybrid"
    ) -> dict[str, Any]:
        # 1) scope to collection
        all_ids = self.adapter.collection_capture_ids(collection_id)
        if not all_ids:
            return {
                "question": question,
                "answer": "This collection has no items.",
                "citations": [],
                "used_chunks": [],
            }

        # 2) retrieve top-K docs
        doc_ids = self.adapter.hybrid_search(
            question, restrict_to_ids=all_ids, limit=self.k_docs, mode=mode
        )
        if not doc_ids:
            return {
                "question": question,
                "answer": "No relevant papers were found for this question.",
                "citations": [],
                "used_chunks": [],
            }

        # caching key includes doc id shortlist
        ck = self._cache_key(collection_id, question, doc_ids)
        cached = cache.get(ck)
        if cached:
            return cached

        # 3) create chunks (cap to ~10)
        contexts: list[str] = []
        citations: list[Citation] = []
        used_chunks: list[dict[str, Any]] = []
        n_counter = 1

        for cid in doc_ids:
            meta = self.adapter.capture_meta(cid)
            text = self.adapter.capture_text(cid)
            if not text:
                continue
            chunks = _chunk_text(text, max_chars=self.chars_per_chunk, overlap=200)
            if not chunks:
                continue
            # take at most one or two chunks per doc to diversify context
            take = 2 if len(contexts) < 4 else 1
            for ch in chunks[:take]:
                header = f"[{n_counter}] {meta.title}"
                if meta.year:
                    header += f" ({meta.year})"
                if meta.doi:
                    header += f". DOI: {meta.doi}"
                context_block = f"{header}\n{ch}"
                contexts.append(context_block)
                citations.append(
                    Citation(
                        n=n_counter,
                        id=meta.id,
                        title=meta.title,
                        year=meta.year,
                        doi=meta.doi,
                    )
                )
                used_chunks.append({"n": n_counter, "id": meta.id, "text": ch})
                n_counter += 1
                if len(contexts) >= self.max_chunks:
                    break
            if len(contexts) >= self.max_chunks:
                break

        # 4) LLM answer
        ctx = "\n\n".join(contexts)
        user_prompt = (
            f"Question: {question}\n\nContext:\n{ctx}\n\n"
            "Answer succinctly. Cite sources like [1], [2]."
        )
        answer = _openai_chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            model=self.model,
            temperature=0.2,
        )

        payload = {
            "question": question,
            "answer": answer.strip(),
            "citations": [c.__dict__ for c in citations],
            "used_chunks": used_chunks,
        }
        cache.set(ck, payload, timeout=60 * 60)  # 1h
        return payload
