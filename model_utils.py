"""
embedding helpers for the travel planner: encode text and score how close things are to a query.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

#lazy load so importing this module does not download weights until you actually encode
_model: SentenceTransformer | None = None

EMBED_DIR = Path(__file__).resolve().parent / "data" / "embeddings"


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_texts(texts: Sequence[str]) -> np.ndarray:
    #one row per string; normalize so dot product equals cosine similarity
    if not texts:
        return np.zeros((0, 384), dtype=np.float32)
    model = _get_model()
    return np.asarray(
        model.encode(list(texts), normalize_embeddings=True, show_progress_bar=False),
        dtype=np.float32,
    )


def rank_by_similarity(query: str, texts: Sequence[str]) -> list[tuple[int, float]]:
    #returns (index in texts, cosine sim) sorted best match first
    if not texts:
        return []
    q = embed_texts([query])
    mat = embed_texts(texts)
    scores = (mat @ q.T).flatten()
    order = np.argsort(-scores)
    return [(int(i), float(scores[i])) for i in order]


def save_embeddings(name: str, matrix: np.ndarray) -> Path:
    EMBED_DIR.mkdir(parents=True, exist_ok=True)
    path = EMBED_DIR / f"{name}.npy"
    np.save(path, matrix)
    return path


def load_embeddings(name: str) -> np.ndarray:
    path = EMBED_DIR / f"{name}.npy"
    return np.load(path)
