from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_DROP_QUERY_KEYS = {
    # UTM
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "utm_reader",
    "utm_name",
    "utm_cid",
    # Ads / click ids
    "gclid",
    "dclid",
    "fbclid",
    "msclkid",
    # Common misc
    "ref",
    "ref_src",
    "ref_url",
}


def canonicalize_url(url: str) -> str:
    s = (url or "").strip()
    if not s:
        return ""

    p = urlparse(s)
    scheme = (p.scheme or "https").lower()
    netloc = (p.netloc or "").lower()

    # Drop default ports
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    # Filter + normalize query params
    q = []
    for k, v in parse_qsl(p.query, keep_blank_values=False):
        kk = (k or "").strip()
        if not kk:
            continue
        if kk.lower() in _DROP_QUERY_KEYS:
            continue
        q.append((kk, v))

    # Stable order
    q.sort(key=lambda kv: (kv[0].lower(), kv[1]))

    query = urlencode(q, doseq=True)
    fragment = ""  # always drop

    # Keep path as-is (case can matter on some sites)
    path = p.path or "/"

    return urlunparse((scheme, netloc, path, p.params, query, fragment))


def url_hash(canonical_url: str) -> str:
    b = (canonical_url or "").encode("utf-8", errors="ignore")
    return hashlib.sha256(b).hexdigest()
