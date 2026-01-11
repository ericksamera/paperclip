from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Iterable, Union

Pathish = Union[str, Path]


def as_dict(v: Any) -> dict[str, Any]:
    """Return *v* if it's a dict, otherwise an empty dict."""
    return v if isinstance(v, dict) else {}


def ensure_dir(p: Path) -> None:
    """Create directory *p* (including parents) if it doesn't exist."""
    p.mkdir(parents=True, exist_ok=True)


def ensure_dirs(*paths: Path) -> None:
    """Create multiple directories (including parents) if they don't exist."""
    for p in paths:
        ensure_dir(p)


def rmtree_best_effort(paths: Iterable[Pathish]) -> None:
    """Delete directories/files best-effort; never raises."""
    for p in paths:
        try:
            shutil.rmtree(Path(p))
        except FileNotFoundError:
            pass
        except NotADirectoryError:
            try:
                Path(p).unlink(missing_ok=True)  # type: ignore[arg-type]
            except Exception:
                pass
        except Exception:
            pass
