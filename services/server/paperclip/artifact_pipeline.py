# services/server/paperclip/artifact_pipeline.py
from __future__ import annotations
from typing import Dict, Any
from paperclip.artifacts import write_text_artifact, write_json_artifact
from captures.parsing_bridge import robust_parse
from captures.artifacts import build_server_parsed
from captures.reduced_view import build_reduced_view

def build_and_write_all(capture_id: str, *, url: str | None,
                        dom_html: str, extraction: Dict[str, Any]) -> Dict[str, Any]:
    # 1) Verbatim inputs
    if dom_html:
        write_text_artifact(capture_id, "page.html", dom_html)
    if extraction.get("content_html"):
        write_text_artifact(capture_id, "content.html", extraction["content_html"])

    # 2) Bridge: strong head meta + preview paragraphs (no reparse later)
    bridge = robust_parse(url=url, content_html=extraction.get("content_html") or "", dom_html=dom_html)

    # 3) Canonical normalization (single parse into typed schema)
    server_parsed = build_server_parsed(_capture_stub(capture_id, extraction), extraction)

    write_json_artifact(capture_id, "server_parsed.json", server_parsed)  # canonical

    # 4) Reduced projection for the UI (and legacy alias parsed.json)
    reduced = build_reduced_view(
        content=bridge.get("content_sections"),
        meta=server_parsed.get("metadata") or {},
        references=server_parsed.get("references") or [],
        title=server_parsed.get("title") or ""
    )
    write_json_artifact(capture_id, "server_output_reduced.json", reduced)
    write_json_artifact(capture_id, "parsed.json", reduced)  # keep until clients stop reading it

    return {"bridge": bridge, "server_parsed": server_parsed, "reduced": reduced}

def _capture_stub(capture_id: str, extraction: Dict[str, Any]):
    """
    Minimal object with attributes the parser package expects: id, title/url/doi/year, references manager.
    The parser only reads attributes; keep it tiny.
    """
    class _C:
        id = capture_id
        title = (extraction.get("meta") or {}).get("title") or ""
        url   = (extraction.get("meta") or {}).get("url") or ""
        doi   = (extraction.get("meta") or {}).get("doi") or ""
        year  = str((extraction.get("meta") or {}).get("issued_year") or "")
        def __getattr__(self, name):
            if name == "references":
                class _R:
                    def all(self): return []
                return _R()
            raise AttributeError(name)
    return _C()
