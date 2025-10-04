# services/server/captures/tests/test_ingest_overrides_and_dedupe.py
from __future__ import annotations

import contextlib
import json
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

from django.test import Client, TestCase, override_settings

from captures.models import Capture
from captures.site_parsers import clear_registry, extract_references, register
from paperclip.artifacts import artifact_path


class IngestOverrideAndDedupeTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()

    @contextlib.contextmanager
    def tmp_data_dir(self) -> Iterator[Path]:
        tmp = tempfile.mkdtemp(prefix="pc-test-data-")
        try:
            with override_settings(DATA_DIR=Path(tmp)):
                yield Path(tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @patch("captures.parsing_bridge.robust_parse")
    def test_strong_head_meta_overrides_client_fields_and_writes_artifacts(
        self, mock_bridge: Any
    ) -> None:
        # robust_parse returns strong head meta; these MUST override client-provided fields
        mock_bridge.return_value = {
            "meta_updates": {
                "title": "Citation Title Wins",
                "doi": "10.5555/OVERRIDE",
                "issued_year": 2024,
                "container_title": "Super Journal",
            },
            "content_sections": {"abstract_or_body": ["Hello world."]},
        }
        payload = {
            "source_url": "https://example.org/article",
            "dom_html": (
                "<html><head><meta name='citation_title' content='Citation Title Wins'>"
                "</head></html>"
            ),
            "extraction": {
                "meta": {"title": "Client Title", "doi": "10.1111/CLIENT", "issued_year": "1999"},
                "csl": {"title": "CSL Client Title"},
                "content_html": "<div>content</div>",
                "references": [
                    {"raw": "A ref", "doi": "10.1000/xxx", "title": "R1", "issued_year": "2000"}
                ],
            },
        }
        with self.tmp_data_dir():
            resp = self.client.post(
                "/api/captures/", data=json.dumps(payload), content_type="application/json"
            )
            self.assertEqual(resp.status_code, 201, resp.content)
            cap = Capture.objects.order_by("-id").first()
            # Use a plain assert so mypy narrows type from "Capture | None" to "Capture".
            assert cap is not None

            # Strong meta overrides
            self.assertEqual(cap.title, "Citation Title Wins")
            self.assertEqual(cap.doi, "10.5555/OVERRIDE")
            self.assertEqual(cap.year, "2024")
            # Other strong meta merged into cap.meta
            self.assertIn("container_title", cap.meta)
            self.assertEqual(cap.meta["container_title"], "Super Journal")

            # Artifacts are written to disk, not to model fields
            page_p = artifact_path(str(cap.id), "page.html")
            content_p = artifact_path(str(cap.id), "content.html")
            self.assertTrue(page_p.exists(), "page.html not written")
            self.assertTrue(content_p.exists(), "content.html not written")
            self.assertIn("citation_title", page_p.read_text("utf-8"))

            # References created (1 client ref)
            self.assertEqual(cap.references.count(), 1)

    @patch(
        "captures.parsing_bridge.robust_parse",
        return_value={"meta_updates": {}, "content_sections": {}},
    )
    @patch("captures.site_parsers.extract_references")
    def test_site_ref_dedup_against_client_refs_by_normalized_doi(
        self, mock_extract_refs: Any, _mock_bridge: Any
    ) -> None:
        # Client provides DOI with scheme; site parser returns same DOI in different case;
        # only one should remain.
        payload = {
            "source_url": "https://example.org/dup",
            "dom_html": "<html></html>",
            "extraction": {
                "meta": {"title": "Client Title"},
                "content_html": "",
                "references": [
                    {
                        "raw": "ClientRef",
                        "doi": "https://doi.org/10.1000/ABC",
                        "title": "Client R",
                        "issued_year": "2000",
                    }
                ],
            },
        }
        mock_extract_refs.return_value = [
            {"raw": "SiteRef", "doi": "10.1000/abc", "title": "Site R", "issued_year": "2000"}
        ]
        resp = self.client.post(
            "/api/captures/", data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        cap = Capture.objects.get(url="https://example.org/dup")
        self.assertEqual(cap.references.count(), 1, "Duplicate DOI (case/format) was not de-duped")

    def test_registry_first_non_empty_wins_and_order_matters(self) -> None:
        # Save/restore registry
        try:
            clear_registry()

            # Rule A (URL) matches and returns empty -> should fall through to Rule B
            def parser_empty(url: str, html: str) -> list[dict[str, Any]]:
                return []

            # Rule B (HOST) matches and returns non-empty -> should be selected
            def parser_hit(url: str, html: str) -> list[dict[str, Any]]:
                return [{"raw": "hit", "title": "hit"}]

            register(r"/custom/path", parser_empty, where="url", name="A_empty")
            register(r"(?:^|\.)example\.com$", parser_hit, where="host", name="B_hit")
            out = extract_references("https://sub.example.com/custom/path", "<html></html>")
            self.assertEqual(out, [{"raw": "hit", "title": "hit"}])

            # Now reverse order: Rule A returns non-empty; it should win immediately.
            clear_registry()

            def parser_hit_first(url: str, html: str) -> list[dict[str, Any]]:
                return [{"raw": "first", "title": "first"}]

            register(r"/custom/path", parser_hit_first, where="url", name="A_first")
            register(r"(?:^|\.)example\.com$", parser_hit, where="host", name="B_hit")
            out2 = extract_references("https://sub.example.com/custom/path", "<html></html>")
            self.assertEqual(out2, [{"raw": "first", "title": "first"}])
        finally:
            clear_registry()  # leave registry clean for other tests
