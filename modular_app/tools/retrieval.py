"""Lightweight annual-report RAG and Open-Meteo API integration."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Optional
import io, time
import pandas as pd
import requests
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel
from pypdf import PdfReader

# التعديل: استخدام Absolute Import بدلاً من Relative Import (..)
from modular_app.datastore import STORE

class PDFRetriever:
    """Extract, chunk, index, and retrieve page-cited PDF passages."""
    def __init__(self, pdf_path: str | Path, chunk_words: int = 180, overlap: int = 40):
        self.pdf_path = Path(pdf_path)
        self.chunk_words = chunk_words
        self.overlap = overlap
        self.chunks = []
        self.vectorizer = None
        self.matrix = None

    def build(self) -> "PDFRetriever":
        if not self.pdf_path.exists():
            raise FileNotFoundError(self.pdf_path)
        reader = PdfReader(str(self.pdf_path))
        for page_no, page in enumerate(reader.pages, 1):
            text = " ".join((page.extract_text() or "").split())
            words = text.split()
            stride = max(1, self.chunk_words - self.overlap)
            for start in range(0, len(words), stride):
                piece = words[start:start + self.chunk_words]
                if len(piece) >= 10:
                    self.chunks.append({"page": page_no, "text": " ".join(piece)})
        if not self.chunks:
            raise ValueError("PDF contains no extractable text.")
        texts = [c["text"] for c in self.chunks]
        self.vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_df=0.9)
        try:
            self.matrix = self.vectorizer.fit_transform(texts)
        except ValueError:
            self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_df=1.0)
            self.matrix = self.vectorizer.fit_transform(texts)
        STORE.set_tfidf(self.vectorizer, self.matrix, self.chunks)
        STORE.set_path("report", self.pdf_path)
        return self

    def retrieve(self, query: str, top_k: int = 3) -> list[dict]:
        if not query or not query.strip():
            raise ValueError("query must not be empty")
        if self.vectorizer is None:
            self.build()
        scores = linear_kernel(self.vectorizer.transform([query]), self.matrix).ravel()
        order = scores.argsort()[::-1][:max(1, int(top_k))]
        return [
            {
                "page": int(self.chunks[i]["page"]),
                "score": round(float(scores[i]), 4),
                "text": self.chunks[i]["text"],
                "citation": f"[Page {self.chunks[i]['page']}]"
            }
            for i in order
        ]

class WeatherAPICaller:
    """Call Open-Meteo current weather with local CSV fallback."""
    URL = "https://api.open-meteo.com/v1/forecast"
    def __init__(self, cache_path: str | Path = "data/weather_cache.csv", timeout: int = 15):
        self.cache_path = Path(cache_path)
        self.timeout = timeout

    def _cache(self) -> dict:
        if not self.cache_path.exists():
            return {"source": "unavailable", "rows": 0, "data": []}
        df = pd.read_csv(self.cache_path)
        return {"source": "local_cache", "rows": int(len(df)), "data": df.head(100).to_dict("records")}

    def fetch(self, latitude: float = 52.52, longitude: float = 13.42) -> dict:
        try:
            r = requests.get(
                self.URL,
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": "temperature_2m,precipitation,rain,wind_speed_10m",
                    "timezone": "auto"
                },
                timeout=self.timeout
            )
            r.raise_for_status()
            payload = r.json()
            if not payload.get("current"):
                raise ValueError("empty current weather payload")
            return {"source": "open_meteo_api", "fallback_used": False, "current": payload["current"]}
        except Exception as exc:
            out = self._cache()
            out.update({"fallback_used": True, "api_error": f"{type(exc).__name__}: {exc}"})
            return out
