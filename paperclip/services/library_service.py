from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ..present import present_capture_for_api, present_capture_for_library
from ..queryparams import LibraryParams, library_params_from_args
from ..repo import collections_repo, library_repo


@dataclass(frozen=True)
class LibraryPageModel:
    q: str
    selected_col: str
    collections: list[dict[str, Any]]
    total_all: int
    captures: list[dict[str, Any]]
    page: int
    page_size: int
    total: int
    has_more: bool
    fts_enabled: bool


@dataclass(frozen=True)
class ApiLibraryPayload:
    captures: list[dict[str, Any]]
    rows_html: str
    page: int
    page_size: int
    total: int
    has_more: bool


def build_library_page_model(
    db,
    *,
    params: LibraryParams,
    fts_enabled: bool,
) -> LibraryPageModel:
    collections = collections_repo.list_collections_with_counts(db)
    total_all = library_repo.count_all_captures(db)

    captures, total, has_more = library_repo.search_captures(
        db,
        q=params.q,
        selected_col=params.selected_col,
        page=params.page,
        page_size=params.page_size,
        fts_enabled=fts_enabled,
    )

    out_caps = [present_capture_for_library(c) for c in captures]

    return LibraryPageModel(
        q=params.q,
        selected_col=params.selected_col,
        collections=collections,
        total_all=total_all,
        captures=out_caps,
        page=params.page,
        page_size=params.page_size,
        total=total,
        has_more=has_more,
        fts_enabled=fts_enabled,
    )


def build_api_library_payload(
    db,
    *,
    params: LibraryParams,
    fts_enabled: bool,
    render_rows: Callable[[list[dict[str, Any]]], str],
) -> ApiLibraryPayload:
    captures, total, has_more = library_repo.search_captures(
        db,
        q=params.q,
        selected_col=params.selected_col,
        page=params.page,
        page_size=params.page_size,
        fts_enabled=fts_enabled,
    )

    rows_caps = [present_capture_for_library(c) for c in captures]
    out_caps = [present_capture_for_api(c) for c in captures]

    rows_html = render_rows(rows_caps)

    return ApiLibraryPayload(
        captures=out_caps,
        rows_html=rows_html,
        page=params.page,
        page_size=params.page_size,
        total=total,
        has_more=has_more,
    )


# --- Thin-route helpers (service returns ready-to-render dicts) ---


def library_page_context_from_args(
    db,
    *,
    args: Mapping[str, Any],
    fts_enabled: bool,
    default_page_size: int = 50,
) -> dict[str, Any]:
    p = library_params_from_args(args, default_page_size=default_page_size)
    model = build_library_page_model(db, params=p, fts_enabled=fts_enabled)
    return {
        "q": model.q,
        "selected_col": model.selected_col,
        "collections": model.collections,
        "total_all": model.total_all,
        "captures": model.captures,
        "page": model.page,
        "page_size": model.page_size,
        "total": model.total,
        "has_more": model.has_more,
        "fts_enabled": model.fts_enabled,
    }


def api_library_response_from_args(
    db,
    *,
    args: Mapping[str, Any],
    fts_enabled: bool,
    render_rows: Callable[[list[dict[str, Any]]], str],
    default_page_size: int = 50,
) -> dict[str, Any]:
    p = library_params_from_args(args, default_page_size=default_page_size)
    payload = build_api_library_payload(
        db,
        params=p,
        fts_enabled=fts_enabled,
        render_rows=render_rows,
    )
    return {
        "captures": payload.captures,
        "rows_html": payload.rows_html,
        "page": payload.page,
        "page_size": payload.page_size,
        "total": payload.total,
        "has_more": payload.has_more,
    }
