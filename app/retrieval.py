"""Retrieval: find the passages most likely to contain the answer.

Three retrievers, so the evaluation can compare them:

* BM25   - keyword matching. Great when the student uses the document's words
           ("re-evaluation fee"), blind to synonyms ("recheck my paper cost").
* Dense  - sentence embeddings. Matches by meaning, so paraphrases work, but
           can miss exact codes and numbers ("CSE-204").
* Hybrid - both ranked lists merged with reciprocal rank fusion (RRF). A
           passage ranked high by either retriever rises to the top.
"""
from __future__ import annotations

import hashlib
import math
from collections import Counter
from dataclasses import dataclass

import numpy as np

from . import config
from .ingest import Chunk
from .textutil import tokenize


@dataclass
class Hit:
    chunk: Chunk
    score: float            # fused score used for ranking
    bm25: float = 0.0
    dense: float = 0.0      # cosine similarity to the query, 0 when dense is off


class BM25:
    """Okapi BM25 over a small corpus, in plain Python + numpy."""

    def __init__(self, texts: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        docs = [tokenize(t) for t in texts]
        self.n = len(docs)
        self.lengths = np.array([len(d) for d in docs], dtype=np.float32)
        self.avg_len = float(self.lengths.mean()) if self.n else 0.0
        self.postings: dict[str, list[tuple[int, int]]] = {}
        for i, doc in enumerate(docs):
            for term, freq in Counter(doc).items():
                self.postings.setdefault(term, []).append((i, freq))
        self.idf = {
            term: math.log(1 + (self.n - len(post) + 0.5) / (len(post) + 0.5))
            for term, post in self.postings.items()
        }

    def scores(self, query: str) -> np.ndarray:
        out = np.zeros(self.n, dtype=np.float32)
        for term in set(tokenize(query)):
            post = self.postings.get(term)
            if not post:
                continue
            idf = self.idf[term]
            for i, freq in post:
                norm = freq + self.k1 * (1 - self.b + self.b * self.lengths[i] / self.avg_len)
                out[i] += idf * freq * (self.k1 + 1) / norm
        return out

    def term_weight(self, term: str) -> float:
        """IDF of a term; unseen terms get the maximum weight (they are the rarest)."""
        return self.idf.get(term, math.log(1 + (self.n + 0.5) / 0.5))


class DenseEncoder:
    """Sentence embeddings through fastembed (ONNX, CPU). Optional: if the model
    cannot be loaded the app keeps working on BM25 alone and says so."""

    def __init__(self) -> None:
        self.model = None
        self.error = ""
        try:
            from fastembed import TextEmbedding

            cache = config.INDEX_DIR / "models"
            cache.mkdir(parents=True, exist_ok=True)
            self.model = TextEmbedding(model_name=config.EMBED_MODEL, cache_dir=str(cache))
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"

    @property
    def ready(self) -> bool:
        return self.model is not None

    @staticmethod
    def _normalise(matrix: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        return matrix / np.clip(norms, 1e-9, None)

    def passages(self, texts: list[str]) -> np.ndarray:
        return self._normalise(np.array(list(self.model.embed(texts, batch_size=32)), dtype=np.float32))

    def query(self, text: str) -> np.ndarray:
        return self._normalise(np.array(list(self.model.query_embed([text])), dtype=np.float32))[0]

    def sentences(self, texts: list[str]) -> np.ndarray:
        return self.passages(texts)


_ENCODER: DenseEncoder | None = None


def get_encoder() -> DenseEncoder:
    global _ENCODER
    if _ENCODER is None:
        _ENCODER = DenseEncoder()
    return _ENCODER


class Index:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        texts = [c.index_text for c in chunks]
        self.bm25 = BM25(texts)
        self.encoder = get_encoder()
        self.vectors: np.ndarray | None = None
        if self.encoder.ready and chunks:
            self.vectors = self._load_or_embed(texts)

    def _load_or_embed(self, texts: list[str]) -> np.ndarray | None:
        digest = hashlib.sha1((config.EMBED_MODEL + "\x00" + "\x00".join(texts)).encode("utf-8")).hexdigest()[:16]
        path = config.INDEX_DIR / f"vectors-{digest}.npy"
        if path.exists():
            return np.load(path)
        try:
            vectors = self.encoder.passages(texts)
        except Exception as exc:
            self.encoder.error = f"{type(exc).__name__}: {exc}"
            self.encoder.model = None
            return None
        config.INDEX_DIR.mkdir(parents=True, exist_ok=True)
        for stale in config.INDEX_DIR.glob("vectors-*.npy"):
            stale.unlink(missing_ok=True)
        np.save(path, vectors)
        return vectors

    @property
    def has_dense(self) -> bool:
        return self.vectors is not None

    @property
    def methods(self) -> list[str]:
        return ["bm25", "dense", "hybrid"] if self.has_dense else ["bm25"]

    def search(self, query: str, k: int = config.TOP_K, method: str = "hybrid",
               category: str | None = None) -> list[Hit]:
        if not self.chunks:
            return []
        if method != "bm25" and not self.has_dense:
            method = "bm25"

        allowed = None
        if category:
            allowed = np.array([c.category == category for c in self.chunks])

        bm25 = self.bm25.scores(query)
        dense = self.vectors @ self.encoder.query(query) if self.has_dense else np.zeros_like(bm25)
        if allowed is not None:
            bm25 = np.where(allowed, bm25, -1.0)
            dense = np.where(allowed, dense, -1.0)

        if method == "bm25":
            fused = bm25.astype(np.float64)
        elif method == "dense":
            fused = dense.astype(np.float64)
        else:
            # Reciprocal rank fusion: score = sum over retrievers of 1 / (RRF_K + rank).
            # It uses ranks, not raw scores, so BM25's unbounded scores and cosine
            # similarities never have to be put on a common scale.
            fused = np.zeros(len(self.chunks), dtype=np.float64)
            for scores in (bm25, dense):
                order = np.argsort(-scores)[: config.CANDIDATES]
                for rank, idx in enumerate(order, start=1):
                    if scores[idx] > 0:
                        fused[idx] += 1.0 / (config.RRF_K + rank)

        order = np.argsort(-fused)[:k]
        return [
            Hit(chunk=self.chunks[i], score=float(fused[i]), bm25=float(max(bm25[i], 0.0)),
                dense=float(max(dense[i], 0.0)))
            for i in order if fused[i] > 0
        ]

    def confidence(self, query: str, hits: list[Hit]) -> float:
        """How sure are we that the retrieved passages actually cover the question? 0..1.

        Two signals are averaged:
        * coverage - the IDF-weighted share of the question's content words that
          occur in the retrieved passages. "phd stipend" scores low when no
          passage mentions either word, however similar the topic looks.
        * similarity - the best cosine similarity, rescaled from the 0.45-0.85
          band the embedding model actually uses into 0..1.
        The assistant declines to answer when this falls below ABSTAIN_THRESHOLD.
        """
        if not hits:
            return 0.0
        terms = set(tokenize(query))
        if not terms:
            return 0.0
        found = set()
        for hit in hits:
            found.update(tokenize(hit.chunk.index_text))
        total = sum(self.bm25.term_weight(t) for t in terms)
        covered = sum(self.bm25.term_weight(t) for t in terms if t in found)
        coverage = covered / total if total else 0.0
        if not self.has_dense:
            return round(coverage, 4)
        best = max(h.dense for h in hits)
        similarity = float(np.clip((best - 0.45) / 0.40, 0.0, 1.0))
        return round(0.5 * coverage + 0.5 * similarity, 4)
