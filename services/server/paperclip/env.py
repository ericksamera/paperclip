# services/server/paperclip/env.py
from __future__ import annotations

import os
import re
from pathlib import Path


def _find_dotenv_candidates() -> list[Path]:
    """
    Search in this order:
      1) DOTENV_PATH / ENV_FILE / PAPERCLIP_ENV_FILE (if set)
      2) repo root:       <repo>/.env
      3) service folder:  <repo>/services/server/.env
      4) app folder:      <repo>/services/server/paperclip/.env
    """
    here = Path(__file__).resolve()
    project = here.parent  # .../paperclip
    service = project.parent  # .../services/server
    repo = service.parent.parent  # .../<repo root>

    env_from_env = (
        os.getenv("DOTENV_PATH")
        or os.getenv("ENV_FILE")
        or os.getenv("PAPERCLIP_ENV_FILE")
    )

    paths: list[Path] = []
    if env_from_env:
        paths.append(Path(env_from_env))
    paths.extend([repo / ".env", service / ".env", project / ".env"])

    seen, uniq = set(), []
    for p in paths:
        try:
            rp = p.resolve()
        except Exception:
            rp = p
        if rp not in seen:
            seen.add(rp)
            uniq.append(rp)
    return uniq


def _parse_dotenv_line(line: str) -> tuple[str, str] | None:
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    if s.lower().startswith("export "):
        s = s[7:].lstrip()
    if "=" not in s:
        return None
    key, val = s.split("=", 1)
    key = key.strip()

    # Trim surrounding quotes
    if (val.startswith('"') and val.endswith('"')) or (
        val.startswith("'") and val.endswith("'")
    ):
        val = val[1:-1]

    # Expand ${VAR} using existing environment
    val = re.sub(r"\$\{([^}]+)\}", lambda m: os.environ.get(m.group(1), ""), val)
    return key, val.strip()


def load_env() -> None:
    """
    Load variables from a .env file into os.environ (without overwriting ones already set).
    Will use python-dotenv if installed; otherwise uses a tiny built-in parser.
    """
    try:
        from dotenv import load_dotenv as _load  # optional dependency
    except Exception:
        _load = None

    for path in _find_dotenv_candidates():
        if not path.exists():
            continue
        if _load:
            _load(dotenv_path=str(path), override=False)
        else:
            try:
                for raw in path.read_text(encoding="utf-8").splitlines():
                    pair = _parse_dotenv_line(raw)
                    if not pair:
                        continue
                    k, v = pair
                    os.environ.setdefault(k, v)
            except Exception:
                # Never break startup on a bad .env
                pass
        break  # stop after first existing .env is processed
