from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .httputil import parse_page_size
from .parseutil import safe_int


def get_collection_arg(args: Mapping[str, Any]) -> str:
    """
    Back-compat:
      - preferred: ?collection=<id>
      - legacy:    ?col=<id>
    Returns a trimmed string (may be empty).
    """
    return (str(args.get("collection") or args.get("col") or "")).strip()


def get_q_arg(args: Mapping[str, Any]) -> str:
    return (str(args.get("q") or "")).strip()


def get_page_arg(args: Mapping[str, Any], default: int = 1) -> int:
    p = safe_int(args.get("page"))
    if p is None:
        p = default
    return max(1, int(p))


def get_page_size_arg(args: Mapping[str, Any], default: int = 50) -> int:
    return parse_page_size(args.get("page_size"), default)


@dataclass(frozen=True)
class LibraryParams:
    q: str
    selected_col: str
    page: int
    page_size: int


def library_params_from_args(
    args: Mapping[str, Any], *, default_page_size: int = 50
) -> LibraryParams:
    return LibraryParams(
        q=get_q_arg(args),
        selected_col=get_collection_arg(args),
        page=get_page_arg(args, default=1),
        page_size=get_page_size_arg(args, default=default_page_size),
    )
