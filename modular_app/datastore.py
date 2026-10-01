from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


class DataStore:
    """In-process singleton store for DataFrames, paths, and retrieval indices.

    Includes a cross-run file-level cache so that the same source file
    (e.g. the 23 MB Online Retail.xlsx) is parsed only once per server
    process lifetime, regardless of how many times run_pipeline() is called.
    """

    # ── Class-level cache shared across all reset() calls ──────────────────
    # Key: str(resolved_path)  →  Value: pd.DataFrame
    _FILE_CACHE: dict[str, pd.DataFrame] = {}
    _CACHE_LOCK: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        """Reset per-run state. The file-level cache is preserved."""
        self._raw_sales: pd.DataFrame | None = None
        self._clean_sales: pd.DataFrame | None = None
        self._paths: dict[str, Any] = {}
        self._retriever: Any = None
        self._vectorizer: Any = None
        self._matrix: Any = None
        self._chunks: list[dict[str, Any]] = []

    # ── File cache helpers ──────────────────────────────────────────────────

    @classmethod
    def get_cached_file(cls, path: str | Path) -> pd.DataFrame | None:
        key = str(Path(path).resolve())
        with cls._CACHE_LOCK:
            return cls._FILE_CACHE.get(key)

    @classmethod
    def set_cached_file(cls, path: str | Path, df: pd.DataFrame) -> None:
        key = str(Path(path).resolve())
        with cls._CACHE_LOCK:
            cls._FILE_CACHE[key] = df

    @classmethod
    def invalidate_cache(cls, path: str | Path | None = None) -> None:
        """Clear one entry (or the whole cache if path is None)."""
        with cls._CACHE_LOCK:
            if path is None:
                cls._FILE_CACHE.clear()
            else:
                cls._FILE_CACHE.pop(str(Path(path).resolve()), None)

    # ── Per-run DataFrame access ────────────────────────────────────────────

    def set_sales_data(
        self,
        raw: pd.DataFrame | None = None,
        clean: pd.DataFrame | None = None,
    ) -> None:
        if raw is not None:
            self._raw_sales = raw
        if clean is not None:
            self._clean_sales = clean

    def get_sales_data(self, clean: bool = True) -> pd.DataFrame | None:
        return self._clean_sales if clean else self._raw_sales

    # ── Path registry ───────────────────────────────────────────────────────

    def set_path(self, key: str, path: Any) -> None:
        self._paths[key] = path

    def get_path(self, key: str) -> Any | None:
        return self._paths.get(key)

    # ── Retriever / TF-IDF index ────────────────────────────────────────────

    def set_retriever(self, retriever: Any) -> None:
        self._retriever = retriever

    def set_tfidf(
        self,
        vectorizer: Any,
        matrix: Any,
        chunks: list[dict[str, Any]],
    ) -> None:
        self._vectorizer = vectorizer
        self._matrix = matrix
        self._chunks = chunks

    def retrieve(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        if self._retriever and hasattr(self._retriever, "retrieve"):
            return self._retriever.retrieve(query, top_k=top_k)
        if self._vectorizer is not None and self._matrix is not None and self._chunks:
            try:
                from sklearn.metrics.pairwise import cosine_similarity

                vec = self._vectorizer.transform([query])
                scores = cosine_similarity(vec, self._matrix).flatten()
                top_indices = np.argsort(scores)[::-1][:top_k]
                results = []
                for idx in top_indices:
                    if scores[idx] > 0:
                        item = dict(self._chunks[idx])
                        item["score"] = float(scores[idx])
                        item["citation"] = f"[Page {item.get('page', 1)}]"
                        results.append(item)
                return results
            except Exception:
                pass
        return []


STORE = DataStore()
