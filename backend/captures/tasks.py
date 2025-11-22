from __future__ import annotations

from contextlib import suppress

from celery import shared_task

from captures.models import Capture
from captures.xref import enrich_capture_via_crossref, enrich_reference_via_crossref
from paperclip.conf import MAX_REFS_TO_ENRICH


@shared_task(name="captures.enrich_refs")
def enrich_refs_task(capture_id: str) -> None:
    cap = Capture.objects.filter(pk=capture_id).first()
    if not cap:
        return
    # Capture-level enrichment
    with suppress(Exception):
        upd = enrich_capture_via_crossref(cap)
        if upd:
            for k, v in upd.items():
                setattr(cap, k, v)
            cap.save(update_fields=list(upd.keys()))
    # Reference-level enrichment (capped)
    count = 0
    for r in cap.references.all().order_by("id"):
        if count >= MAX_REFS_TO_ENRICH:
            break
        if not r.doi:
            continue
        with suppress(Exception):
            upd = enrich_reference_via_crossref(r)
            if upd:
                for k, v in upd.items():
                    setattr(r, k, v)
                r.save(update_fields=list(upd.keys()))
        count += 1
