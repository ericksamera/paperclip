from __future__ import annotations

import json
from pathlib import Path

from paperclip.db import get_db


def _write_capture_with_sections(app, *, cap_id: str = "cap-chunks-1") -> str:
    doi = "10.1234/chunks.test" if cap_id == "cap-chunks-1" else f"10.1234/{cap_id}"
    artifacts_root = Path(app.config["ARTIFACTS_DIR"])
    cap_dir = artifacts_root / cap_id
    cap_dir.mkdir(parents=True, exist_ok=True)

    reduced = {
        "id": cap_id,
        "source_url": "https://example.org/chunks",
        "canonical_url": "https://example.org/chunks",
        "title": "Structured Chunking Paper",
        "doi": doi,
        "year": 2024,
        "container_title": "Journal of Chunks",
        "authors": ["Ada Lovelace", "Grace Hopper"],
        "abstract": "Metadata abstract should not duplicate parsed abstract.",
        "published_date_raw": "2024-02-03",
        "keywords": [],
        "captured_at": "2026-01-01T00:00:00+00:00",
        "meta": {},
        "parse": {"ok": True, "parser": "test"},
    }
    sections = [
        {
            "id": "s01",
            "kind": "abstract",
            "kinds": ["abstract"],
            "level": 2,
            "title": "Abstract",
            "text": "We tested structured chunk export.",
        },
        {
            "id": "s02",
            "kind": "results",
            "kinds": ["results"],
            "level": 2,
            "title": "Results",
            "text": "Overall results showed the intervention worked.",
        },
        {
            "id": "s03",
            "kind": "other",
            "kinds": ["other"],
            "level": 3,
            "parent_id": "s02",
            "title": "Growth assay",
            "text": "Growth increased under treatment.",
        },
        {
            "id": "s04",
            "kind": "other",
            "kinds": ["other"],
            "level": 3,
            "parent_id": "s02",
            "title": "Sequencing assay",
            "text": "Sequencing identified stable variants.",
        },
        {
            "id": "s05",
            "kind": "methods",
            "kinds": ["methods"],
            "level": 2,
            "title": "Culture protocol",
            "text": "Cells were cultured overnight before assay.",
        },
        {
            "id": "s06",
            "kind": "limitations",
            "kinds": ["limitations"],
            "level": 2,
            "title": "Limitations",
            "text": "The experiment used one model system.",
        },
        {
            "id": "s07",
            "kind": "references",
            "kinds": ["references"],
            "level": 2,
            "title": "References",
            "text": "Ref A. 2020. Reference text should be excluded.",
        },
    ]

    (cap_dir / "reduced.json").write_text(
        json.dumps(reduced, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (cap_dir / "sections.json").write_text(
        json.dumps(sections, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO captures (
              id, url, url_canon, url_hash,
              title, doi, year, container_title,
              meta_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cap_id,
                "https://example.org/chunks",
                "https://example.org/chunks",
                f"hash-{cap_id}",
                "Structured Chunking Paper",
                doi,
                2024,
                "Journal of Chunks",
                "{}",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        db.commit()

    return cap_id


def _parse_ndjson(body: str) -> list[dict]:
    return [json.loads(line) for line in body.splitlines() if line.strip()]


def test_export_chunks_jsonl_writes_structured_evidence_chunks(client, app):
    cap_id = _write_capture_with_sections(app)

    papers = client.get("/exports/papers.jsonl/")
    assert papers.status_code == 200
    assert cap_id in papers.get_data(as_text=True)

    out = client.get("/exports/chunks.jsonl/")
    assert out.status_code == 200
    assert "chunks" in out.headers.get("Content-Disposition", "")

    rows = _parse_ndjson(out.get_data(as_text=True))
    assert rows

    required_top = {
        "chunk_id",
        "paper_id",
        "doi",
        "title",
        "year",
        "authors",
        "section_kind",
        "section_title",
        "text",
        "source",
    }
    required_source = {
        "capture_id",
        "artifact",
        "section_id",
        "char_start",
        "char_end",
    }
    for row in rows:
        assert required_top.issubset(row.keys())
        assert required_source.issubset(row["source"].keys())
        assert row["paper_id"] == cap_id
        assert row["doi"] == "10.1234/chunks.test"
        assert row["year"] == 2024
        assert row["authors"] == ["Ada Lovelace", "Grace Hopper"]
        assert row["text"].startswith("Paper: Structured Chunking Paper")

    abstracts = [r for r in rows if r["section_kind"] == "abstract"]
    assert len(abstracts) == 1
    assert abstracts[0]["section_title"] == "Abstract"
    assert abstracts[0]["source"]["artifact"] == "sections.json"
    assert abstracts[0]["source"]["section_id"] == "s01"

    result_titles = {r["section_title"] for r in rows if r["section_kind"] == "results"}
    assert {"Results", "Growth assay", "Sequencing assay"}.issubset(result_titles)

    assert any(r["section_kind"] == "methods" for r in rows)
    assert any(r["section_kind"] == "limitations" for r in rows)
    assert not any(r["section_kind"] == "references" for r in rows)
    assert "Reference text should be excluded" not in out.get_data(as_text=True)


def test_chunks_jsonl_chunk_ids_are_deterministic(client, app):
    _write_capture_with_sections(app, cap_id="cap-chunks-deterministic")

    first = _parse_ndjson(client.get("/exports/chunks.jsonl/").get_data(as_text=True))
    second = _parse_ndjson(client.get("/exports/chunks.jsonl/").get_data(as_text=True))

    assert [r["chunk_id"] for r in first] == [r["chunk_id"] for r in second]
    assert any(r["chunk_id"] == "cap-chunks-deterministic:s03:c001" for r in first)


def test_export_selected_chunks_jsonl_only_includes_selected(client, app):
    id1 = _write_capture_with_sections(app, cap_id="cap-chunks-selected-1")
    id2 = _write_capture_with_sections(app, cap_id="cap-chunks-selected-2")

    out = client.post(
        "/exports/chunks.jsonl/selected/",
        data={"capture_ids": [id1]},
        follow_redirects=False,
    )
    assert out.status_code == 200
    rows = _parse_ndjson(out.get_data(as_text=True))

    assert any(r["paper_id"] == id1 for r in rows)
    assert not any(r["paper_id"] == id2 for r in rows)
