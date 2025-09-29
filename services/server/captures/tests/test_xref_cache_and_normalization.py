# services/server/captures/tests/test_xref_cache_and_normalization.py
from __future__ import annotations
import json, tempfile, shutil
from pathlib import Path
from unittest.mock import patch, Mock
from django.test import TestCase, override_settings

from captures.models import Capture, Reference
from captures import xref as xref_mod

class XrefCacheNormalizationTests(TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="pc-xref-cache-"))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @override_settings(DATA_DIR=None)  # we will patch _CACHE_DIR directly
    def test_xref_uses_disk_cache_and_mem_cache(self):
        # Point xref cache dir to temp path
        with patch.object(xref_mod, "_CACHE_DIR", self.tmpdir / "cache"):
            (self.tmpdir / "cache").mkdir(parents=True, exist_ok=True)

            cap = Capture.objects.create(url="u", title="t")
            ref = Reference.objects.create(capture=cap, raw="r", doi="HTTPS://DOI.ORG/10.77/ABC")

            # First call hits network, writes cache
            fake_csl = {"title": "X Title", "issued": {"date-parts": [[2023]]}, "container-title": ["J"]}
            m = Mock()
            m.ok = True
            m.json.return_value = fake_csl

            with patch("captures.xref.requests.get", return_value=m) as mock_get:
                upd1 = xref_mod.enrich_reference_via_crossref(ref)
                self.assertIsNotNone(upd1)
                self.assertIn("title", upd1)
                self.assertTrue(any(self.tmpdir.glob("cache/*.json")))
                mock_get.assert_called_once()

            # Second call should NOT hit network (mem/disk cache), still returns updates
            with patch("captures.xref.requests.get", side_effect=RuntimeError("should not be called")) as mock_get2:
                upd2 = xref_mod.enrich_reference_via_crossref(ref)
                self.assertIsNotNone(upd2)
                mock_get2.assert_not_called()
