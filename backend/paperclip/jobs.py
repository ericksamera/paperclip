# services/server/paperclip/jobs.py
from __future__ import annotations

import inspect
import logging
import os
import threading
from importlib import import_module
from typing import Any, Callable, Optional

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
it "guesses" likely functions and adapts to their accepted parameters.
"""

log = logging.getLogger(__name__)

__all__ = [
    "submit_enrichment",
    "submit_analysis",
    # legacy aliases
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
      - if function takes *zero* parameters, call it with no args
      - otherwise pass capture_id as a single positional argument
    """
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        # builtins / C callables may not have a signature; try positional
        fn(str(capture_id))
        return

    params = list(sig.parameters.keys())
    # ZERO-ARG FIX: call with no arguments if the function accepts none
    if len(params) == 0:
        fn()
        return

    kwargs: dict[str, Any] = {}

    for key in ("capture_id", "id", "pk", "capture"):
        if key in params:
            kwargs[key] = capture_id
            break

    if "tool" in params and tool is not None:
        kwargs["tool"] = tool

    if kwargs:
        fn(**kwargs)
    else:
        # fallback: pass capture_id positionally if at least one param exists
        fn(str(capture_id))


# ======================================================================================
# Guessers
# ======================================================================================


def _maybe(module_name: str, func_name: str) -> Optional[Callable[..., Any]]:
    try:
        mod = import_module(module_name)
        return getattr(mod, func_name, None)
    except Exception:
        return None


def _guess_enrichment_builder() -> Optional[Callable[..., Any]]:
    # try most specific first; tolerate refactors
    candidates = [
        ("paperclip.captures.reduced_view", "ensure_reduced_view"),
        ("paperclip.captures.reduced_view", "rebuild_reduced_view"),
        ("paperclip.captures.reduced_view", "build_reduced_view"),
        ("captures.reduced_view", "ensure_reduced_view"),
        ("captures.reduced_view", "rebuild_reduced_view"),
        ("captures.reduced_view", "build_reduced_view"),
        ("paperclip.enrich", "enrich_capture"),
        ("paperclip.jobs_impl", "build_reduced_view"),
    ]
    for mod, fn in candidates:
        f = _maybe(mod, fn)
        if callable(f):
            return f
    return None


def _guess_analysis_runner() -> Optional[Callable[..., Any]]:
    candidates = [
        ("paperclip.analysis", "run_analysis"),
        ("paperclip.analysis", "start_analysis"),
        ("analysis.runner", "run"),
    ]
    for mod, fn in candidates:
        f = _maybe(mod, fn)
        if callable(f):
            return f
    return None


# ======================================================================================
# Entrypoints
# ======================================================================================


def _run_enrichment(capture_id: str) -> None:
    builder = _guess_enrichment_builder()
    if not builder:
        log.warning("No enrichment builder found; skipping.")
        return
    try:
        _call_fn_adapting_args(builder, capture_id)
    except Exception:
        log.exception("Enrichment failed for capture %s", capture_id)


def _run_analysis(capture_id: str, *, tool: str | None = None) -> None:
    runner = _guess_analysis_runner()
    if not runner:
        log.warning("No analysis runner found; skipping.")
        return
    try:
        _call_fn_adapting_args(runner, capture_id, tool=tool)
    except Exception:
        log.exception("Analysis failed for capture %s", capture_id)


def submit_enrichment(capture_id: str, *, immediate: bool | None = None) -> None:
    mode = (immediate is True) or (
        os.getenv("PAPERCLIP_ENRICH_MODE", "thread") == "sync"
    )
    if mode:
        _run_enrichment(capture_id)
    else:
        _spawn_thread("pc-enrich", _run_enrichment, capture_id)


def submit_analysis(
    capture_id: str, *, tool: str | None = None, immediate: bool | None = None
) -> None:
    mode = (immediate is True) or (
        os.getenv("PAPERCLIP_ANALYSIS_MODE", "thread") == "sync"
    )
    if mode:
        _run_analysis(capture_id, tool=tool)
    else:
        _spawn_thread("pc-analysis", _run_analysis, capture_id, tool=tool)


# legacy names still imported by some modules in older layouts
schedule_analysis = submit_analysis
queue_analysis = submit_analysis
start_analysis = submit_analysis
