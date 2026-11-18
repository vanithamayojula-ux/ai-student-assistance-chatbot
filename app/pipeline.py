"""The RAG pipeline: question -> retrieve -> decide whether to answer -> generate -> cite."""
from __future__ import annotations

import re
import threading
import time
from typing import Iterator

from . import config
from .generate import (CITATION, NO_ANSWER, STREAMS, available_generators, extractive_answer,
                       support_highlights)
from .ingest import Document, build_chunks
from .retrieval import Hit, Index
from .textutil import split_blocks, tokenize

GREETING = ("Hi! Ask me about the syllabus, exam and attendance regulations, notices, "
            "fees, hostel and campus services, or academic policies. I answer from the "
            "university's documents and show you the passage each answer comes from.")
ABSTAIN = ("I could not find this in the university documents I have, so I will not guess. "
           "Try rephrasing, or check with the concerned office.")
_FOLLOW_UP = re.compile(r"\b(it|its|that|this|those|these|they|them|same|above|also|then)\b|^(and|what about|how about|aur)\b", re.I)


class Engine:
    """Holds the index and answers questions. One instance per server process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.documents: list[Document] = []
        self.index: Index | None = None
        # threshold: gate when answers are quoted from the documents.
        # loose_threshold: gate when a language model writes the answer (it can
        # decline by itself, so the gate only has to stop clearly off-topic questions).
        self.threshold, self.loose_threshold = self._load_thresholds()
        self.rebuild()

    @staticmethod
    def _load_thresholds() -> tuple[float, float]:
        """Use the thresholds the evaluation chose, unless the environment overrides them."""
        import json
        import os

        strict, loose = config.ABSTAIN_THRESHOLD, config.LOOSE_THRESHOLD
        tuned = config.EVAL_DIR / "threshold.json"
        if "ABSTAIN_THRESHOLD" not in os.environ and tuned.exists():
            try:
                saved = json.loads(tuned.read_text(encoding="utf-8"))
                strict = float(saved["threshold"])
                loose = float(saved.get("loose_threshold", loose))
            except (ValueError, KeyError, OSError):
                pass
        return strict, min(loose, strict)

    def rebuild(self) -> None:
        with self._lock:
            documents, chunks = build_chunks()
            self.documents, self.index = documents, Index(chunks)

    # ------------------------------------------------------------------
    def contextualise(self, question: str, history: list[dict]) -> str:
        """Make a follow-up searchable on its own.

        "and for the hostel?" retrieves nothing useful by itself, so a short or
        pronoun-led follow-up is searched together with the previous question.
        """
        previous = [t["content"] for t in history if t.get("role") == "user" and t.get("content")]
        if not previous:
            return question
        if len(tokenize(question)) <= 2 or _FOLLOW_UP.search(question):
            return f"{previous[-1]} {question}"
        return question

    def retrieve(self, query: str, k: int | None = None, method: str | None = None,
                 category: str | None = None) -> tuple[list[Hit], float]:
        hits = self.index.search(query, k or config.TOP_K, method, category)
        return hits, self.index.confidence(query, hits)

    @staticmethod
    def _sources(hits: list[Hit], highlights: dict[int, set[tuple[int, int]]] | None = None) -> list[dict]:
        highlights = highlights or {}
        out = []
        for n, hit in enumerate(hits):
            marked = highlights.get(n, set())
            blocks = [
                {"kind": block["kind"],
                 "units": [{"text": unit, "hit": (b, u) in marked} for u, unit in enumerate(block["units"])]}
                for b, block in enumerate(split_blocks(hit.chunk.text))
            ]
            out.append({
                "n": n + 1,
                "chunk_id": hit.chunk.chunk_id,
                "doc_id": hit.chunk.doc_id,
                "title": hit.chunk.title,
                "category": hit.chunk.category,
                "section": hit.chunk.section,
                "updated": hit.chunk.updated,
                "origin": hit.chunk.origin,
                "cited": n in highlights,
                "blocks": blocks,
            })
        return out

    # ------------------------------------------------------------------
    def answer_stream(self, question: str, history: list[dict] | None = None,
                      generator: str = "extractive", category: str | None = None,
                      method: str | None = None) -> Iterator[dict]:
        """Yield events: one "meta", zero or more "token", then one "done"."""
        started = time.perf_counter()
        history = history or []
        question = question.strip()

        def done(answer: str, hits: list[Hit], highlights, abstained: bool, used: str,
                 confidence: float, note: str = "") -> dict:
            return {
                "type": "done", "answer": answer, "abstained": abstained, "generator": used,
                "confidence": confidence, "note": note,
                "sources": self._sources(hits, highlights),
                "latency_ms": round((time.perf_counter() - started) * 1000),
            }

        if not tokenize(question):                      # "hi", "thanks", empty
            yield done(GREETING, [], {}, False, "none", 1.0)
            return

        query = self.contextualise(question, history)
        hits, confidence = self.retrieve(query, method=method, category=category)
        yield {"type": "meta", "confidence": confidence, "query": query,
               "sources": self._sources(hits)}

        note = ""
        ready = {g["id"] for g in available_generators() if g["ready"]}
        if generator in STREAMS and generator not in ready:
            note = "The selected language model is not available, so this answer quotes the documents directly."
            generator = "extractive"

        gate = self.loose_threshold if generator in STREAMS else self.threshold
        if not hits or confidence < gate:
            yield done(ABSTAIN, hits, {}, True, generator, confidence, note)
            return

        if generator in STREAMS:
            buffer, released = "", False
            try:
                for piece in STREAMS[generator](question, hits, history):
                    buffer += piece
                    # Hold back the first few characters: if the model is saying
                    # NO_ANSWER the student should see the abstain message, not the token.
                    if not released and len(buffer.strip()) < len(NO_ANSWER) + 2:
                        continue
                    if not released:
                        if NO_ANSWER in buffer.upper().replace(" ", "_"):
                            continue
                        released = True
                        yield {"type": "token", "text": buffer}
                    else:
                        yield {"type": "token", "text": piece}
                answer = buffer.strip()
                if not answer or NO_ANSWER in answer.upper().replace(" ", "_")[:40]:
                    yield done(ABSTAIN, hits, {}, True, generator, confidence)
                    return
                if not CITATION.search(answer):
                    # The model forgot to cite. Attribute the answer to the passages that support it.
                    backing = support_highlights(self.index, answer + " " + " ".join(
                        f"[{n}]" for n in range(1, len(hits) + 1)), question, hits)
                    backing = {n: marks for n, marks in backing.items() if marks}
                else:
                    backing = support_highlights(self.index, answer, question, hits)
                yield done(answer, hits, backing, False, generator, confidence)
                return
            except Exception as exc:
                note = f"The language model failed ({exc}). This answer quotes the documents directly."
                if released:
                    yield {"type": "reset"}             # discard the half-written answer on screen
                if confidence < self.threshold:         # quoted answers use the stricter gate
                    yield done(ABSTAIN, hits, {}, True, "extractive", confidence, note)
                    return

        answer, highlights = extractive_answer(self.index, query, hits)
        if not answer:
            yield done(ABSTAIN, hits, {}, True, "extractive", confidence, note)
            return
        yield done(answer, hits, highlights, False, "extractive", confidence, note)

    def answer(self, question: str, **kwargs) -> dict:
        """Non-streaming convenience wrapper (used by the evaluation and the tests)."""
        final: dict = {}
        for event in self.answer_stream(question, **kwargs):
            if event["type"] == "done":
                final = event
        return final


_engine: Engine | None = None
_engine_lock = threading.Lock()


def get_engine() -> Engine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = Engine()
        return _engine
