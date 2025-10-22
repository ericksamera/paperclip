# services/server/captures/tests/test_reference_ingest.py
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from captures.models import Capture

PMC_PAGE = """<!doctype html>
<html>
<head>
  <meta name="citation_title" content="PMC page">
  <meta name="citation_journal_title" content="Journal X">
  <meta name="prism.publicationdate" content="2017-01-01">
</head>
<body>
  <article><p>Body.</p></article>
  <section class="ref-list">
    <ul class="ref-list">
      <li id="B1"><span class="label">1.</span>
        <cite>Foreman ... 2013. Environ Res Lett.</cite>
        <a href="https://doi.org/10.1088/1748-9326/8/3/035022">DOI</a>
      </li>
      <li id="B2"><span class="label">2.</span>
        <cite>Smith ... 2018. FEMS Microbiol Ecol. doi: 10.1093/femsec/fiy090</cite>
      </li>
      <li id="B3"><span class="label">3.</span>
        <cite>Edgar ... 2007. BMC Bioinformatics.</cite>
      </li>
    </ul>
  </section>
</body>
</html>
"""
GENERIC_PAGE = """<!doctype html>
<html>
<head>
  <meta name="citation_title" content="Generic page">
  <meta name="citation_journal_title" content="Journal Y">
  <meta name="prism.publicationdate" content="2016-02-02">
</head>
<body>
  <article><p>Body.</p></article>
  <ol class="references">
    <li><cite>Eid et al. 2009.</cite><a href="https://doi.org/10.1126/science.1162986">DOI</a></li>
    <li><cite>Bland et al. 2007.</cite></li>
  </ol>
</body>
</html>
"""


class ReferenceIngestTests(TestCase):
    def _temp_dirs(self):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        arts = root / "artifacts"
        ana = root / "analysis"
        arts.mkdir(parents=True, exist_ok=True)
        ana.mkdir(parents=True, exist_ok=True)
        return tmp, arts, ana

    @override_settings()
    def test_ingest_pmc_counts_references(self):
        tmp, artifacts_dir, analysis_dir = self._temp_dirs()
        self.addCleanup(tmp.cleanup)
        with override_settings(ARTIFACTS_DIR=artifacts_dir, ANALYSIS_DIR=analysis_dir):
            client = APIClient()
            payload = {
                "source_url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC999999/",
                "dom_html": PMC_PAGE,
                "extraction": {
                    "meta": {},
                    "content_html": "<p>Hi</p>",
                    "references": [],
                },
                "rendered": {},
                "client": {"ext": "chrome", "v": "0.1.0"},
            }
            with patch(
                "captures.artifacts.build_server_parsed", return_value={"id": "stubbed"}
            ):
                resp = client.post(
                    "/api/captures/",
                    data=json.dumps(payload),
                    content_type="application/json",
                )
                self.assertEqual(resp.status_code, 201, resp.content)
                cap_id = resp.json()["capture_id"]
                cap = Capture.objects.get(pk=cap_id)
                # 3 from PMC snippet
                self.assertEqual(cap.references.count(), 3)
                # view.json includes the references list
                cap_dir = artifacts_dir / str(cap_id)
                view = json.loads((cap_dir / "view.json").read_text("utf-8"))
                self.assertEqual(len(view.get("references") or []), 3)

    @override_settings()
    def test_ingest_generic_counts_references(self):
        tmp, artifacts_dir, analysis_dir = self._temp_dirs()
        self.addCleanup(tmp.cleanup)
        with override_settings(ARTIFACTS_DIR=artifacts_dir, ANALYSIS_DIR=analysis_dir):
            client = APIClient()
            payload = {
                "source_url": "https://example.org/article/abc",
                "dom_html": GENERIC_PAGE,
                "extraction": {
                    "meta": {},
                    "content_html": "<p>Hi</p>",
                    "references": [],
                },
                "rendered": {},
                "client": {"ext": "chrome", "v": "0.1.0"},
            }
            with patch(
                "captures.artifacts.build_server_parsed", return_value={"id": "stubbed"}
            ):
                resp = client.post(
                    "/api/captures/",
                    data=json.dumps(payload),
                    content_type="application/json",
                )
                self.assertEqual(resp.status_code, 201, resp.content)
                cap_id = resp.json()["capture_id"]
                cap = Capture.objects.get(pk=cap_id)
                # 2 from generic snippet
                self.assertEqual(cap.references.count(), 2)
                cap_dir = artifacts_dir / str(cap_id)
                view = json.loads((cap_dir / "view.json").read_text("utf-8"))
                self.assertEqual(len(view.get("references") or []), 2)
