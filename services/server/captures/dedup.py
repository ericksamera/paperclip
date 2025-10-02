# services/server/captures/dedup.py
from __future__ import annotations
import re
from typing import Dict, List
from datasketch import MinHash, MinHashLSH
from captures.reduced_view import read_reduced_view
from captures.models import Capture

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z\-]{2,}")

def _text_for(c: Capture) -> str:
    bits = [c.title or "", c.doi or ""]
    meta = c.meta or {}
    if meta.get("abstract"):
        bits.append(str(meta["abstract"]))

    try:
        view = read_reduced_view(str(c.id))
        paras = ((view.get("sections") or {}).get("abstract_or_body") or [])
        if isinstance(paras, list) and paras:
            bits.append(" ".join(paras[:80]))
    except Exception:
        pass

    return " ".join(bits)

def _minhash(text: str, num_perm: int = 128) -> MinHash:
    mh = MinHash(num_perm=num_perm)
    toks = [w.lower() for w in TOKEN_RE.findall(text)]
    if not toks:
        mh.update(b"__EMPTY__")
    else:
        for tok in set(toks):
            mh.update(tok.encode("utf-8"))
    return mh

def find_near_duplicates(threshold: float = 0.85) -> List[List[str]]:
    mhs: Dict[str, MinHash] = {}
    for c in Capture.objects.all().iterator():
        mhs[str(c.id)] = _minhash(_text_for(c))
    lsh = MinHashLSH(threshold=threshold, num_perm=128)
    for pk, mh in mhs.items():
        lsh.insert(pk, mh)
    seen, groups = set(), []
    for pk, mh in mhs.items():
        if pk in seen:
            continue
        bucket = set(lsh.query(mh))
        if len(bucket) > 1:
            groups.append(sorted(bucket))
            seen |= bucket
    return groups
