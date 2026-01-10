from __future__ import annotations

import json
from pathlib import Path


def _dom_with_doi_and_authors(*, doi: str, authors: list[str], title: str) -> str:
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
  </head>
  <body><article><p>Hello A.</p><p>Hello B.</p></article></body>
</html>
"""


def _dom_no_doi(*, authors: list[str], title: str) -> str:
    authors_meta = "\n".join(
        [f'<meta name="citation_author" content="{a}">' for a in authors]
    )
    return f"""<!doctype html>
<html>
  <head>
    <title>{title}</title>
    <meta name="citation_title" content="{title}">
    {authors_meta}
  </head>
  <body><article><p>Hello A.</p><p>Hello B.</p></article></body>
</html>
"""


CONTENT_FOR_POST = "<div><p>Hello A.</p><p>Hello B.</p></div>"


def _post_capture(client, *, source_url: str, dom_html: str) -> str:
    payload = {
        "source_url": source_url,
        "dom_html": dom_html,
        "extraction": {"meta": {}, "content_html": CONTENT_FOR_POST, "references": []},
        "rendered": {},
        "client": {"ext": "chrome", "v": "0.1.0"},
    }
    r = client.post(
        "/api/captures/", data=json.dumps(payload), content_type="application/json"
    )
    assert r.status_code in (200, 201)
    return r.get_json()["capture_id"]


def test_crossref_nonempty_authors_overrides_and_preserves_local(
    monkeypatch, client, app
):
    # Local meta authors in DOM
    local_authors = ["Jane Doe", "John Smith"]
    doi = "10.5555/override.1"

    # Crossref authors (authoritative override)
    ext_authors = ["Ada Lovelace", "Grace Hopper"]

    # Provide provenance that should fill missing fields (only when override happens)
    prov = {
        "source": "crossref",
        "title": "Crossref Title",
        "container_title": "Crossref Journal",
        "published_date_raw": "2019-02-03",
        "year": 2019,
        "authors": ext_authors,
    }

    import paperclip.capture_dto as capture_dto

    def fake_best_external_authors_for_doi(got_doi: str):
        assert got_doi == doi
        return ext_authors, prov

    monkeypatch.setattr(
        capture_dto, "best_external_authors_for_doi", fake_best_external_authors_for_doi
    )

    dom = _dom_with_doi_and_authors(doi=doi, authors=local_authors, title="DOM Title")

    cap_id = _post_capture(
        client, source_url="https://example.org/override", dom_html=dom
    )

    cap_dir = Path(app.config["ARTIFACTS_DIR"]) / cap_id
    reduced = json.loads((cap_dir / "reduced.json").read_text(encoding="utf-8"))

    # Authors overridden to Crossref
    assert reduced["doi"] == doi
    assert reduced["authors"] == ext_authors

    # Local authors preserved in reduced["meta"] (this is merged_head_meta)
    assert reduced["meta"]["_paperclip_local_authors"] == local_authors

    # Provenance saved at meta_json top-level "_external" (reduced doesn't include meta_record),
    # but we can still check DB meta_json via API fetch.
    row = client.get(f"/api/captures/{cap_id}/").get_json()
    meta_json = json.loads(row["meta_json"])
    assert meta_json["_external"]["source"] == "crossref"

    # Filled from Crossref since original meta lacked these and override happened
    assert reduced["year"] == 2019
    assert reduced["container_title"] == "Crossref Journal"
    assert reduced["published_date_raw"] == "2019-02-03"
    assert (
        reduced["title"] == "DOM Title"
    )  # DOM title is already strong; no need to override


def test_crossref_empty_authors_does_not_override(monkeypatch, client, app):
    local_authors = ["Jane Doe", "John Smith"]
    doi = "10.6666/nooverride.1"

    import paperclip.capture_dto as capture_dto

    def fake_best_external_authors_for_doi(got_doi: str):
        assert got_doi == doi
        # empty list => should NOT override
        return [], {"source": "crossref", "authors": []}

    monkeypatch.setattr(
        capture_dto, "best_external_authors_for_doi", fake_best_external_authors_for_doi
    )

    dom = _dom_with_doi_and_authors(doi=doi, authors=local_authors, title="DOM Title")
    cap_id = _post_capture(
        client, source_url="https://example.org/nooverride", dom_html=dom
    )

    cap_dir = Path(app.config["ARTIFACTS_DIR"]) / cap_id
    reduced = json.loads((cap_dir / "reduced.json").read_text(encoding="utf-8"))

    # Keep local authors
    assert reduced["authors"] == local_authors

    # No local-preservation key should be injected because we didn't override
    assert "_paperclip_local_authors" not in reduced["meta"]


def test_no_doi_does_not_call_crossref(monkeypatch, client):
    import paperclip.capture_dto as capture_dto

    def boom(_doi: str):
        raise AssertionError(
            "best_external_authors_for_doi should not be called when doi is missing"
        )

    monkeypatch.setattr(capture_dto, "best_external_authors_for_doi", boom)

    dom = _dom_no_doi(authors=["Jane Doe"], title="No DOI Page")
    _post_capture(client, source_url="https://example.org/nodoi", dom_html=dom)
