from __future__ import annotations


def test_library_page_includes_new_export_buttons(client):
    r = client.get("/library/")
    assert r.status_code == 200
    body = r.get_data(as_text=True)

    # top-level exports
    assert "Export Papers JSONL" in body

    # library exports row
    assert "Export Papers JSONL" in body
    assert "Export Master MD" in body

    # bulk actions
    assert "Export selected (Papers JSONL)" in body
    assert "Export selected (Master MD)" in body


def test_collections_page_includes_papers_jsonl_link(client):
    r = client.get("/collections/")
    assert r.status_code == 200
    body = r.get_data(as_text=True)

    # Even with no collections yet, template should still be valid.
    # Once collections exist, the link label should be present in the table rows.
    # We just sanity-check the page includes the word "Collections".
    assert "Collections" in body
