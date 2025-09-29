# services/server/captures/tests/test_api_ingest.py
from __future__ import annotations
import json, tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from captures.models import Capture

DOM_FOR_POST = """<!doctype html>
<html>
  <head>
    <meta name="citation_title" content="Server-Side Title">
    <meta name="citation_doi" content="10.9999/xyz.abc">
    <meta name="prism.publicationdate" content="2020-11-02">
    <meta name="citation_journal_title" content="Journal of Testing">
    <meta name="citation_keywords" content="alpha, beta; gamma">
  </head>
  <body><article><p>Hello A.</p><p>Hello B.</p></article></body>
</html>"""

CONTENT_FOR_POST = "<div><p>Hello A.</p><p>Hello B.</p></div>"

class ApiIngestTests(TestCase):
  def _temp_dirs(self):
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    arts = root / "artifacts"
    ana  = root / "analysis"
    arts.mkdir(parents=True, exist_ok=True)
    ana.mkdir(parents=True, exist_ok=True)
    return tmp, arts, ana

  def test_post_capture_writes_artifacts_and_merges_meta(self):
    tmp, artifacts_dir, analysis_dir = self._temp_dirs()
    self.addCleanup(tmp.cleanup)

    client = APIClient()

    payload = {
      "source_url": "https://example.org/post",
      "dom_html": DOM_FOR_POST,
      "extraction": {
        "meta": {"title": "Client Title"},  # initial client meta (we expect server may override)
        "content_html": CONTENT_FOR_POST,
        "references": []
      },
      "rendered": {},
      "client": {"ext": "chrome", "v": "0.1.0"}
    }

    # IMPORTANT: the API imports the function from captures.artifacts at call time,
    # so we must patch the symbol at that module path (not paperclip.api.*).
    # See: services/server/paperclip/api.py
    with override_settings(ARTIFACTS_DIR=artifacts_dir, ANALYSIS_DIR=analysis_dir):
      with patch("captures.artifacts.build_server_parsed", return_value={"id": "stubbed"}):

        resp = client.post("/api/captures/", data=json.dumps(payload),
                           content_type="application/json")
        self.assertEqual(resp.status_code, 201, resp.content)

        data = resp.json()
        cap_id = data.get("capture_id")
        self.assertTrue(cap_id)

        # DB assertions
        cap = Capture.objects.get(pk=cap_id)
        # Title should prefer strong head meta ("citation") over client title.
        self.assertEqual(cap.title, "Server-Side Title")
        # DOI/year propagated
        self.assertEqual(cap.doi, "10.9999/xyz.abc")
        self.assertEqual(cap.year, "2020")

        # Meta should be merged with container_title + keywords
        self.assertEqual((cap.meta or {}).get("container_title"), "Journal of Testing")
        self.assertEqual((cap.meta or {}).get("keywords"), ["alpha", "beta", "gamma"])

        # Artifacts written
        cap_dir = artifacts_dir / str(cap_id)
        self.assertTrue((cap_dir / "doc.json").exists())
        self.assertTrue((cap_dir / "view.json").exists())
        self.assertTrue((cap_dir / "page.html").exists())
        self.assertTrue((cap_dir / "content.html").exists())

        
        # Reduced view contains our preview paragraphs
        reduced = json.loads((cap_dir / "view.json").read_text(encoding="utf-8"))
        sections = (reduced.get("sections") or {})
        paras = sections.get("abstract_or_body") or []
        self.assertEqual(paras[:2], ["Hello A.", "Hello B."])