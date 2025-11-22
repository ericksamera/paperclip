# services/server/captures/semantic.py
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
from django.conf import settings

from captures.models import Capture
from captures.text_assembly import build_doc_text

# sentence-transformers is optional; we load lazily and fail nicely.
try:
    from sentence_transformers import SentenceTransformer  # type: ignore
except Exception:  # pragma: no cover - optional dep
    SentenceTransformer = None

INDEX_DIR: Path = settings.ANALYSIS_DIR / "semantic"
EMB_FILE: Path = INDEX_DIR / "embeddings.npy"
IDS_FILE: Path = INDEX_DIR / "ids.json"
MODEL_FILE: Path = INDEX_DIR / "model.txt"
DEFAULT_MODEL = os.environ.get("PAPERCLIP_EMBED_MODEL", "allenai/specter2_base")


def _need_model():
    if SentenceTransformer is None:
        raise RuntimeError(
            "sentence-transformers not installed; pip install sentence-transformers"
        )
    return SentenceTransformer


def _load_model(name: str):
    ST = _need_model()
    return ST(name)


def _collect_docs() -> tuple[list[str], list[str]]:
    """
    Collect (ids, texts) for all captures, using the canonical build_doc_text().
    Skips captures whose text is empty after normalization.
    """
    ids: list[str] = []
    texts: list[str] = []
    # Newest first so incremental rebuilds feel natural
    for cap in Capture.objects.all().order_by("-created_at"):
        pk = str(cap.id)
        text = build_doc_text(cap).strip()
        if not text:
            continue
        ids.append(pk)
        texts.append(text)
    return ids, texts


def build_index(model_name: str = DEFAULT_MODEL) -> tuple[int, str]:
    """
    Build/update ANN index under data/analysis/semantic/.
    Embeddings are L2-normalized so dot = cosine.
    """
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    ids, texts = _collect_docs()
    if not ids:
        # Empty index
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


def _ensure_index() -> None:
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
        [query],
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    ).astype("float32")[0]
    sims = (M @ q).astype("float32")
    idx = np.argsort(-sims)[:k]
    return [ids[i] for i in idx]


def rrf_hybrid_ids(query: str, limit: int = 300) -> list[str]:
    """
    Reciprocal Rank Fusion of FTS (BM25-ish) + semantic ANN.
    Falls back to pure FTS if embeddings unavailable.
    """
    from captures.search import search_ids as fts_search

    try:
        sem = search_ids_semantic(query, k=limit)
    except Exception:
        sem = []
    fts = fts_search(query, limit=limit)

    ranks: dict[str, float] = {}

    def _add(arr: list[str], weight: float = 1.0) -> None:
        for r, pk in enumerate(arr, start=1):
            ranks[pk] = ranks.get(pk, 0.0) + weight * (1.0 / (60.0 + r))

    _add(fts, 1.0)
    _add(sem, 1.0)

    return [pk for pk, _ in sorted(ranks.items(), key=lambda kv: kv[1], reverse=True)]
