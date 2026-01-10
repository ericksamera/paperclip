from __future__ import annotations

import json
from pathlib import Path


def _dom_with_meta(*, doi: str, authors: list[str], abstract: str, title: str) -> str:
    authors_meta = "\n".join(
        [f'<meta name="citation_author" content="{a}">' for a in authors]
    )
    return f"""<!doctype html>
<html>
  <head>
    <title>{title}</title>
    <meta name="citation_title" content="{title}">
    <meta name="citation_doi" content="{doi}">
    {authors_meta}
    <meta name="citation_abstract" content="{abstract}">
    <meta name="prism.publicationdate" content="2021-06-15">
    <meta name="citation_journal_title" content="Journal of Metadata">
  </head>
  <body>
    <article><p>Hello A.</p><p>Hello B.</p></article>
  </body>
</html>
"""


def _dom_with_citation_authors(*, doi: str, authors_str: str, title: str) -> str:
    # PubMed-style: citation_authors often appears as a semicolon-separated string
    return f"""<!doctype html>
<html>
  <head>
    <title>{title}</title>
    <meta name="citation_title" content="{title}">
    <meta name="citation_doi" content="{doi}">
    <meta name="citation_authors" content="{authors_str}">
    <meta name="prism.publicationdate" content="2021-06-15">
    <meta name="citation_journal_title" content="Journal of Metadata">
  </head>
  <body>
    <article><p>Hello A.</p><p>Hello B.</p></article>
  </body>
</html>
"""


CONTENT_FOR_POST = "<div><p>Hello A.</p><p>Hello B.</p></div>"


def test_ingest_extracts_authors_and_abstract_and_api_includes_snips(client, app):
    dom = _dom_with_meta(
        doi="10.5555/meta.123",
        authors=["Jane Doe", "John Smith", "Ada Lovelace"],
        abstract="This is an abstract about metadata extraction that should show up in the UI.",
        title="Metadata Extraction Paper",
    )

    payload = {
        "source_url": "https://example.org/meta",
        "dom_html": dom,
        "extraction": {"meta": {}, "content_html": CONTENT_FOR_POST, "references": []},
        "rendered": {},
        "client": {"ext": "chrome", "v": "0.1.0"},
    }

    r = client.post(
        "/api/captures/", data=json.dumps(payload), content_type="application/json"
    )
    assert r.status_code in (200, 201)
    cap_id = r.get_json()["capture_id"]

    # Verify reduced.json contains extracted authors + abstract
    arts = Path(app.config["ARTIFACTS_DIR"]) / cap_id
    reduced = json.loads((arts / "reduced.json").read_text(encoding="utf-8"))
    assert reduced["doi"] == "10.5555/meta.123"
    assert reduced["authors"] == ["Jane Doe", "John Smith", "Ada Lovelace"]
    assert reduced["abstract"].startswith("This is an abstract")

    # Verify library API includes derived fields from meta_json
    api = client.get("/api/library/?q=10.5555/meta.123")
    assert api.status_code == 200
    data = api.get_json()
    assert data and data["total"] >= 1
    row = next((c for c in data["captures"] if c["id"] == cap_id), None)
    assert row is not None

    # 3 authors => "Doe et al."
    assert row["authors_short"] == "Doe et al."
    # abstract_snip should be non-empty
    assert isinstance(row["abstract_snip"], str)
    assert len(row["abstract_snip"]) > 0


def test_ingest_extracts_authors_from_citation_authors_plural(client, app):
    dom = _dom_with_citation_authors(
        doi="10.6666/plural.1",
        authors_str="Weremijewicz J;da Silveira Lobo O'Reilly Sternberg L;Janos DP;",
        title="Plural Authors Paper",
    )

    payload = {
        "source_url": "https://example.org/meta-plural",
        "dom_html": dom,
        "extraction": {"meta": {}, "content_html": CONTENT_FOR_POST, "references": []},
        "rendered": {},
        "client": {"ext": "chrome", "v": "0.1.0"},
    }

    r = client.post(
        "/api/captures/", data=json.dumps(payload), content_type="application/json"
    )
    assert r.status_code in (200, 201)
    cap_id = r.get_json()["capture_id"]

    arts = Path(app.config["ARTIFACTS_DIR"]) / cap_id
    reduced = json.loads((arts / "reduced.json").read_text(encoding="utf-8"))

    # Should split on semicolons and keep non-empty names
    assert reduced["authors"][:2] == [
        "Weremijewicz J",
        "da Silveira Lobo O'Reilly Sternberg L",
    ]
    assert any(a == "Janos DP" for a in reduced["authors"])
