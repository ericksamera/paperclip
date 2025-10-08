# services/server/captures/dedup.py
from __future__ import annotations

from contextlib import suppress

from datasketch import MinHash, MinHashLSH

from captures.models import Capture
from captures.reduced_view import read_reduced_view
from analysis.text import tokenize


def _text_for(c: Capture) -> str:
    """
    Build a representative text for a capture:
      • title + doi
      • meta.abstract (if present)
      • first ~80 preview paragraphs from reduced view (if present)
    """
    bits = [c.title or "", c.doi or ""]
    meta = c.meta or {}
    if meta.get("abstract"):
        bits.append(str(meta["abstract"]))
    with suppress(Exception):
        view = read_reduced_view(str(c.id))
        paras = (view.get("sections") or {}).get("abstract_or_body") or []
        if isinstance(paras, list) and paras:
            bits.append(" ".join(paras[:80]))
    return " ".join(bits)


def _minhash(text: str, num_perm: int = 128) -> MinHash:
    mh = MinHash(num_perm=num_perm)
    toks = set(tokenize(text))  # <-- analysis-grade tokenization
    if not toks:
        mh.update(b"__EMPTY__")
    else:
        for tok in toks:
            mh.update(tok.encode("utf-8"))
    return mh


def find_near_duplicates(threshold: float = 0.85) -> list[list[str]]:
    """
    Return groups of capture IDs that look like near duplicates under MinHash/LSH.
    """
    mhs: dict[str, MinHash] = {}
    for c in Capture.objects.all().iterator():
        mhs[str(c.id)] = _minhash(_text_for(c))
    lsh = MinHashLSH(threshold=threshold, num_perm=128)
    for pk, mh in mhs.items():
        lsh.insert(pk, mh)
    seen: set[str] = set()
    groups: list[list[str]] = []
    for pk, mh in mhs.items():
        if pk in seen:
            continue
        bucket = set(lsh.query(mh))
        if len(bucket) > 1:
            groups.append(sorted(bucket))
            seen |= bucket
    return groups
