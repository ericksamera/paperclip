from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable, Union

Pathish = Union[str, Path]


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
