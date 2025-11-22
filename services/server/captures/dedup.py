# services/server/captures/dedup.py
from __future__ import annotations


from datasketch import MinHash, MinHashLSH

from captures.models import Capture
from captures.text_assembly import build_doc_text
from captures.text_utils import tokenize


def _text_for(c: Capture) -> str:
    """
    Canonical representative text for a capture used by MinHash/LSH dedup.

    Delegates to captures.text_assembly.build_doc_text so that dedup, search,
    and analysis all share the same notion of “document text”.
    """
    return build_doc_text(c)


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
