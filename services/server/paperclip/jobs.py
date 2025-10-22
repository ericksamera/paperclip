# services/server/paperclip/jobs.py
from __future__ import annotations

"""
Job helpers for Paperclip (dev-friendly, Black/Ruff clean).

Public API
----------
- submit_enrichment(capture_id: str, *, immediate: bool | None = None) -> None
- submit_analysis(capture_id: str, *, tool: str | None = None, immediate: bool | None = None) -> None

Behavior
--------
- In development, jobs run in a background thread by default.
- Set PAPERCLIP_ENRICH_MODE=sync   to run enrichment inline (good for debugging).
- Set PAPERCLIP_ANALYSIS_MODE=sync to run analysis inline.
- Never raises ImportError at import time (callers can unconditionally import).

This module is intentionally resilient to internal refactors:
it "guesses" the right underlying functions by checking several likely
modules and function names, and adapts to their accepted parameters.
"""

from importlib import import_module
import inspect
import logging
import os
import threading
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)

__all__ = [
    "submit_enrichment",
    "submit_analysis",
    # back-compat aliases some codebases have imported in the past:
    "schedule_analysis",
    "queue_analysis",
    "start_analysis",
]

# ======================================================================================
# Utilities
# ======================================================================================


def _spawn_thread(
    name: str, target: Callable[..., Any], *args: Any, **kwargs: Any
) -> None:
    t = threading.Thread(
        target=target, name=name, args=args, kwargs=kwargs, daemon=True
    )
    t.start()


def _call_fn_adapting_args(
    fn: Callable[..., Any], capture_id: str, *, tool: str | None = None
) -> None:
    """
    Call `fn` with whatever parameters it supports.

    Preference order:
      - keyword arg named one of: capture_id | id | pk | capture
      - include 'tool' kwarg only if `fn` accepts it
      - otherwise pass capture_id as a single positional argument
    """
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        # builtins / C callables may not have a signature; try positional
        fn(str(capture_id))
        return

    params = list(sig.parameters.keys())
    kwargs: dict[str, Any] = {}

    for key in ("capture_id", "id", "pk", "capture"):
        if key in params:
            kwargs[key] = str(capture_id)
            break

    if "tool" in params and tool is not None:
        kwargs["tool"] = tool

    try:
        if kwargs:
            fn(**kwargs)
        else:
            fn(str(capture_id))
    except TypeError:
        # last-chance positional call if signature probing went sideways
        fn(str(capture_id))


# ======================================================================================
# Enrichment (reduced view builder)
# ======================================================================================


def _guess_enrichment_builder() -> Optional[Callable[[str], None]]:
    """
    Try to locate the reduced-view builder in captures.reduced_view.
    Accept several possible names to tolerate refactors.
    """
    try:
        rv = import_module("captures.reduced_view")
    except Exception as exc:  # noqa: BLE001
        log.debug("jobs: could not import captures.reduced_view (%s)", exc)
        return None

    for name in (
        "rebuild_reduced_view",
        "build_reduced_view",
        "generate_reduced_view",
        "write_reduced_view",
        "ensure_reduced_view",
    ):
        fn = getattr(rv, name, None)
        if callable(fn):
            return fn
    return None


def _run_enrichment(capture_id: str) -> None:
    builder = _guess_enrichment_builder()
    if not builder:
        log.info(
            "jobs: no reduced-view builder found; skipping enrichment for %s",
            capture_id,
        )
        return
    try:
        _call_fn_adapting_args(builder, capture_id)
        log.info("jobs: enrichment completed for %s", capture_id)
    except Exception as exc:  # noqa: BLE001
        log.exception("jobs: enrichment failed for %s: %s", capture_id, exc)


def submit_enrichment(capture_id: str, *, immediate: bool | None = None) -> None:
    """
    Schedule enrichment for a capture (build server_output_reduced.json, etc.).

    Modes (env)
    -----------
    PAPERCLIP_ENRICH_MODE=sync   -> run inline (default if immediate=True)
    PAPERCLIP_ENRICH_MODE=thread -> background thread (default)
    """
    mode = (os.getenv("PAPERCLIP_ENRICH_MODE") or "thread").lower()
    if immediate is True:
        mode = "sync"
    if mode not in {"sync", "thread"}:
        mode = "thread"

    if mode == "sync":
        _run_enrichment(capture_id)
    else:
        _spawn_thread(f"pc-enrich-{capture_id}", _run_enrichment, str(capture_id))


# ======================================================================================
# Analysis
# ======================================================================================


def _guess_analysis_runner() -> Optional[Callable[..., Any]]:
    """
    Try to locate a capture analysis runner. We probe a few likely modules/names
    so this works across refactors without touching callers.

    The runner is expected to accept at least the capture id, and MAY accept `tool`.
    """
    candidates = [
        (
            "analysis.jobs",
            ("run_capture_analysis", "run_analysis", "run", "analyze_capture"),
        ),
        (
            "analysis.pipeline",
            ("run_capture_analysis", "run_analysis", "run", "process"),
        ),
        ("analysis.runner", ("run_capture_analysis", "run_analysis", "run")),
        (
            "paperclip.analysis",
            ("run_capture_analysis", "run_analysis", "analyze", "run"),
        ),
    ]
    for mod_name, names in candidates:
        try:
            mod = import_module(mod_name)
        except Exception:
            continue
        for name in names:
            fn = getattr(mod, name, None)
            if callable(fn):
                return fn
    return None


def _run_analysis(capture_id: str, *, tool: str | None = None) -> None:
    runner = _guess_analysis_runner()
    if not runner:
        log.info("jobs: no analysis runner found; skipping analysis for %s", capture_id)
        return
    try:
        _call_fn_adapting_args(runner, capture_id, tool=tool)
        log.info("jobs: analysis completed for %s", capture_id)
    except Exception as exc:  # noqa: BLE001
        log.exception("jobs: analysis failed for %s: %s", capture_id, exc)


def submit_analysis(
    capture_id: str, *, tool: str | None = None, immediate: bool | None = None
) -> None:
    """
    Schedule analysis for a capture.

    Parameters
    ----------
    capture_id:
        Capture primary key (UUID/str).
    tool:
        Optional tool/strategy hint; passed only if the runner supports it.
    immediate:
        If True, forces inline execution (blocking). Otherwise obeys env mode.

    Modes (env)
    -----------
    PAPERCLIP_ANALYSIS_MODE=sync   -> run inline (default if immediate=True)
    PAPERCLIP_ANALYSIS_MODE=thread -> background thread (default)
    """
    mode = (os.getenv("PAPERCLIP_ANALYSIS_MODE") or "thread").lower()
    if immediate is True:
        mode = "sync"
    if mode not in {"sync", "thread"}:
        mode = "thread"

    if mode == "sync":
        _run_analysis(capture_id, tool=tool)
    else:
        _spawn_thread(
            f"pc-analysis-{capture_id}", _run_analysis, str(capture_id), tool=tool
        )


# Back-compat aliases some code might import
def schedule_analysis(
    capture_id: str, *, tool: str | None = None, immediate: bool | None = None
) -> None:  # pragma: no cover
    submit_analysis(capture_id, tool=tool, immediate=immediate)


def queue_analysis(
    capture_id: str, *, tool: str | None = None, immediate: bool | None = None
) -> None:  # pragma: no cover
    submit_analysis(capture_id, tool=tool, immediate=immediate)


def start_analysis(
    capture_id: str, *, tool: str | None = None, immediate: bool | None = None
) -> None:  # pragma: no cover
    submit_analysis(capture_id, tool=tool, immediate=immediate)
