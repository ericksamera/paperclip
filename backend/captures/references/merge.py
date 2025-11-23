from __future__ import annotations

from captures.models import Capture, Reference
from captures.reduced_view import CANONICAL_REDUCED_BASENAME
from paperclip.artifacts import artifact_path
from paperclip.utils import norm_doi


def _merge_references_into(winner: Capture, from_cap: Capture) -> None:
    """
    Move references from 'from_cap' to 'winner', deduping on normalized DOI then raw.
    """
    existing = Reference.objects.filter(capture=winner).only("id", "doi", "raw")
    existing_doi = {norm_doi(r.doi) for r in existing if r.doi}
    existing_raw = {(r.raw or "").strip().lower() for r in existing if r.raw}

    to_create: list[Reference] = []
    for r in Reference.objects.filter(capture=from_cap).order_by("id"):
        doi_key = norm_doi(r.doi)
        raw_key = (r.raw or "").strip().lower()
        if (doi_key and doi_key in existing_doi) or (
            not doi_key and raw_key in existing_raw
        ):
            continue
        to_create.append(
            Reference(
                capture=winner,
                ref_id=r.ref_id,
                raw=r.raw,
                doi=r.doi,
                title=r.title,
                issued_year=r.issued_year,
                container_title=r.container_title,
                authors=r.authors,
                csl=r.csl,
                volume=r.volume,
                issue=r.issue,
                pages=r.pages,
                publisher=r.publisher,
                issn=r.issn,
                isbn=r.isbn,
                bibtex=r.bibtex,
                apa=r.apa,
                url=r.url,
            )
        )

    if to_create:
        Reference.objects.bulk_create(to_create, batch_size=200)


def _copy_artifact_if_missing(winner: Capture, donor: Capture, basename: str) -> None:
    """
    Copy donor's artifact into winner if winner lacks it.
    """
    w_p = artifact_path(str(winner.id), basename)
    if w_p.exists():
        return
    d_p = artifact_path(str(donor.id), basename)
    if not d_p.exists():
        return
    # Simple byte copy
    w_p.parent.mkdir(parents=True, exist_ok=True)
    w_p.write_bytes(d_p.read_bytes())


def merge_captures(winner: Capture, loser: Capture) -> None:
    """
    Merge `loser` into `winner` without deleting `loser`.

    Shared between:
      - automatic ingest duplicate handling
      - manual Dedup UI merges

    Responsibilities:
      - union references from loser into winner (dedup by DOI/raw)
      - copy canonical artifacts if winner lacks them
      - ensure winner belongs to all collections loser belonged to
    """
    # Union references (deduping by DOI/raw)
    _merge_references_into(winner, loser)

    # Copy canonical artifacts the winner lacks
    for base in (
        "server_parsed.json",
        CANONICAL_REDUCED_BASENAME,
        "page.html",
        "content.html",
        "bridge.json",
        "extraction.json",
        "dom.html",
    ):
        _copy_artifact_if_missing(winner, loser, base)

    # Ensure winner is in all of loser's collections
    for col in loser.collections.all():
        col.captures.add(winner)
