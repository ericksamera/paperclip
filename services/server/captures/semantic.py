# services/server/captures/semantic.py
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
from django.conf import settings

from analysis.graph_build import collect_docs  # reuses your doc text assembly

# sentence-transformers is optional in your repo; we load lazily.
try:
    from sentence_transformers import SentenceTransformer  # type: ignore
except Exception:
    SentenceTransformer = None  # we'll error nicely at runtime
INDEX_DIR: Path = settings.ANALYSIS_DIR / "semantic"
EMB_FILE: Path = INDEX_DIR / "embeddings.npy"
IDS_FILE: Path = INDEX_DIR / "ids.json"
MODEL_FILE: Path = INDEX_DIR / "model.txt"
DEFAULT_MODEL = os.environ.get("PAPERCLIP_EMBED_MODEL", "allenai/specter2_base")


def _need_model():
    if SentenceTransformer is None:
        raise RuntimeError("sentence-transformers not installed; pip install sentence-transformers")
    return SentenceTransformer


def _load_model(name: str):
    ST = _need_model()
    return ST(name)


def build_index(model_name: str = DEFAULT_MODEL) -> tuple[int, str]:
    """
    Build/update ANN index under data/analysis/semantic/.
    Embeddings are L2-normalized so dot = cosine.
    """
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    docs = collect_docs()
    texts = [d.text for d in docs]
    ids = [d.id for d in docs]
    if not ids:
        np.save(EMB_FILE, np.zeros((0, 1), dtype="float32"))
        IDS_FILE.write_text(json.dumps(ids), encoding="utf-8")
        MODEL_FILE.write_text(model_name, encoding="utf-8")
        return 0, model_name
    model = _load_model(model_name)
    embs = model.encode(
        texts,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    ).astype("float32")
    np.save(EMB_FILE, embs)
    IDS_FILE.write_text(json.dumps(ids), encoding="utf-8")
    MODEL_FILE.write_text(model_name, encoding="utf-8")
    return len(ids), model_name


def _ensure_index():
    if EMB_FILE.exists() and IDS_FILE.exists() and MODEL_FILE.exists():
        return
    build_index()


def _load_index() -> tuple[np.ndarray, list[str], str]:
    _ensure_index()
    embs = np.load(EMB_FILE)
    ids = json.loads(IDS_FILE.read_text(encoding="utf-8"))
    model_name = (MODEL_FILE.read_text(encoding="utf-8") or DEFAULT_MODEL).strip()
    return embs, ids, model_name


def search_ids_semantic(query: str, k: int = 200) -> list[str]:
    """
    Return capture IDs ranked by cosine similarity to the query embedding.
    """
    M, ids, model_name = _load_index()
    if M.shape[0] == 0:
        return []
    model = _load_model(model_name)
    q = model.encode(
        [query], show_progress_bar=False, convert_to_numpy=True, normalize_embeddings=True
    )
    q = q.astype("float32")[0]
    sims = (M @ q).astype("float32")
    idx = np.argsort(-sims)[:k]
    return [ids[i] for i in idx]


def rrf_hybrid_ids(query: str, limit: int = 300) -> list[str]:
    """
    Reciprocal Rank Fusion of FTS (BM25-ish) + semantic ANN.
    Falls back to pure FTS if embeddings unavailable.
    """
    from captures.search import search_ids as fts_search  # your SQLite FTS5 search

    try:
        sem = search_ids_semantic(query, k=limit)
    except Exception:
        sem = []
    fts = fts_search(query, limit=limit)
    ranks: dict[str, float] = {}

    def add(arr: list[str], w=1.0):
        for r, pk in enumerate(arr, start=1):
            ranks[pk] = ranks.get(pk, 0.0) + w * (1.0 / (60.0 + r))

    add(fts, 1.0)
    add(sem, 1.0)
    return [pk for pk, _ in sorted(ranks.items(), key=lambda kv: kv[1], reverse=True)]
