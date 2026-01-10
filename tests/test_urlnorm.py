from __future__ import annotations

from paperclip.urlnorm import canonicalize_url


def test_canonicalize_drops_fragment_and_sorts_query_and_keeps_port():
    u = "https://Example.org:8443/path?a=2&b=1&a=1#section"
    c = canonicalize_url(u)

    assert c.startswith("https://example.org:8443/path?")
    assert "#section" not in c

    # query should be stable and sorted by key then value
    assert c.endswith("a=1&a=2&b=1")


def test_canonicalize_default_path_is_slash():
    c = canonicalize_url("https://example.org")
    assert c == "https://example.org/"


def test_canonicalize_drops_tracking_params():
    c = canonicalize_url("https://example.org/x?utm_source=abc&z=9")
    assert "utm_source" not in c
    assert c.endswith("?z=9")
