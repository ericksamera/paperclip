# services/server/paperclip/artifact_pipeline.py
from __future__ import annotations

from typing import Any

from captures.models import Capture
from paperclip.artifacts import write_json_artifact, write_text_artifact
from paperclip.ingest import _robust_parse, _write_canonical_artifacts


def build_and_write_all(
    capture_id: str,
    *,
    url: str | None,
    dom_html: str,
    extraction: dict[str, Any],
) -> dict[str, Any]:
    """
    Dev/CLI helper for (re)building artifacts for an *existing* Capture.

    This is a thin wrapper around the same helpers used by ingest_capture, so
    it writes the same artifact set:

      - page.html / dom.html / content.html
      - extraction.json / bridge.json
      - server_parsed.json + doc.json
      - server_output_reduced.json (CANONICAL_REDUCED_BASENAME) + view.json

    It assumes a Capture row already exists with this id.
    """
    cap = Capture.objects.filter(pk=capture_id).first()
    if cap is None:
        raise ValueError(f"No Capture found with id={capture_id!r}")

    # Optionally refresh URL/meta/CSL from the provided payload
    if url:
        cap.url = url

    meta_in = extraction.get("meta") or {}
    csl_in = extraction.get("csl") or {}

    if meta_in:
        cap.meta = meta_in
    if csl_in:
        cap.csl = csl_in

    cap.save(update_fields=["url", "meta", "csl"])

    # 1) Verbatim artifacts (HTML snapshots + raw extraction)
    if dom_html:
        # Original snapshot
        write_text_artifact(capture_id, "page.html", dom_html)
        # Parser-friendly alias used by rebuild_reduced_view
        write_text_artifact(capture_id, "dom.html", dom_html)

    content_html = extraction.get("content_html") or ""
    if content_html:
        write_text_artifact(capture_id, "content.html", content_html)

    write_json_artifact(capture_id, "extraction.json", extraction)

    # 2) Bridge: strong head meta + preview/sections (same as ingest_capture)
    bridge = _robust_parse(
        url=cap.url or "",
        content_html=content_html,
        dom_html=dom_html or "",
    )
    write_json_artifact(capture_id, "bridge.json", bridge)

    # 3) Canonical parse + reduced view + legacy aliases
    server_parsed = _write_canonical_artifacts(cap, bridge, extraction)

    return {
        "bridge": bridge,
        "server_parsed": server_parsed,
    }
