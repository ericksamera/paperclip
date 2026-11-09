from __future__ import annotations

import json
from pathlib import Path

FIREFOX_DIR = Path(__file__).resolve().parents[1] / "extensions" / "firefox"


def test_firefox_extension_is_mv3_with_event_page_and_click_only_access():
    manifest = json.loads((FIREFOX_DIR / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["manifest_version"] == 3
    assert manifest["background"] == {"scripts": ["background.js"]}
    assert manifest["action"]["default_title"] == "Save to Paperclip"
    assert set(manifest["permissions"]) == {"activeTab", "scripting"}
    assert set(manifest["host_permissions"]) == {
        "http://127.0.0.1/*",
        "http://localhost/*",
    }
    assert "content_scripts" not in manifest
    assert (FIREFOX_DIR / "background.js").is_file()
