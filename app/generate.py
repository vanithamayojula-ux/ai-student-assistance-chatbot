"""Generation: turn retrieved passages into an answer with citations.

Three generators share one contract (question + passages in, cited answer out):

* extractive - no language model. Picks the sentences that best answer the
               question and quotes them. Cannot hallucinate, works offline.
* gemini     - the Gemini API writes the answer from the passages.
* claude     - the Claude API writes the answer from the passages.

For the LLM generators the model is told to use only the passages and to reply
NO_ANSWER when they do not contain the answer, which is what keeps a RAG
chatbot honest.
"""
from __future__ import annotations

import json
import math
import os
import re
import time
from typing import Iterator

import numpy as np

from . import config
from .retrieval import Hit, Index
from .textutil import clean_unit, split_blocks, tokenize

NO_ANSWER = "NO_ANSWER"
CITATION = re.compile(r"\[(\d+)\]")


# --------------------------------------------------------------------------
# passages -> units
# --------------------------------------------------------------------------
def _is_question(unit: str) -> bool:
    plain = unit.replace("*", "").strip()
    return plain.lower().startswith("q:") or plain.endswith("?")


def explode(hits: list[Hit]) -> list[dict]:
    """One record per citeable unit of every retrieved passage."""
    units: list[dict] = []
    for rank, hit in enumerate(hits):
        position = 0
        for b, block in enumerate(split_blocks(hit.chunk.text)):
            header = block["units"][0] if block["kind"] == "table" else None
            for u, unit in enumerate(block["units"]):
                is_header = block["kind"] == "table" and u == 0
                units.append({
                    "source": rank, "block": b, "unit": u, "position": position,
                    "raw": unit, "kind": block["kind"], "header": header,
                    "is_header": is_header,
                    "is_question": block["kind"] == "prose" and _is_question(unit),
                    "text": clean_unit(unit, None if is_header else header),
                })
                position += 1
    return units


def _score_units(index: Index, query: str, units: list[dict], k: int) -> np.ndarray:
    """Relevance of each unit to the query: weighted keyword overlap + meaning + rank.

    Keyword weights combine corpus-wide rarity (IDF) with rarity among the
    retrieved units. In a syllabus passage every sentence says "Machine Learning
    CS301", so those words say nothing about which sentence answers "who is the
    course coordinator"; "coordinator" appears in one sentence and decides it.
    """
    terms = set(tokenize(query))
    unit_terms = [set(tokenize(u["text"])) for u in units]

    def weight(term: str) -> float:
        local = sum(1 for found in unit_terms if term in found)
        return index.bm25.term_weight(term) * math.log(1 + len(units) / (1 + local))

    weights = {t: weight(t) for t in terms}
    total = sum(weights.values()) or 1.0
    overlap = np.array([sum(weights[t] for t in terms & found) / total for found in unit_terms],
                       dtype=np.float32)
    scores = overlap.copy()
    if index.has_dense and units:
        vectors = index.encoder.sentences([u["text"] for u in units])
        # Meaning counts three times as much as shared words: of the mixes compared on
        # the labelled questions this put the most key facts into answers of the same length.
        scores = 0.25 * overlap + 0.75 * np.clip(vectors @ index.encoder.query(query), 0, 1)
    rank_bonus = np.array([0.12 * (1 - u["source"] / max(k, 1)) for u in units], dtype=np.float32)
    return scores + rank_bonus


# --------------------------------------------------------------------------
# extractive generator
# --------------------------------------------------------------------------
def extractive_answer(index: Index, query: str, hits: list[Hit]) -> tuple[str, dict[int, set[tuple[int, int]]]]:
    """Return (answer text with [n] citations, {source: {(block, unit), ...}} highlights)."""
    units = explode(hits)
    if not units:
        return "", {}
    scores = _score_units(index, query, units, len(hits))

    # An FAQ question matches the student's question best, but the *answer* is the
    # sentences after it. Pass the question's score on to its answer and drop the question.
    for i, unit in enumerate(units):
        if not unit["is_question"]:
            continue
        j = i + 1
        while j < len(units) and units[j]["source"] == unit["source"] \
                and units[j]["block"] == unit["block"] and not units[j]["is_question"]:
            scores[j] = max(scores[j], 0.95 * scores[i])
            j += 1
        scores[i] = -1.0
    for i, unit in enumerate(units):
        if unit["is_header"] or len(unit["text"].split()) < 3:
            scores[i] = -1.0

    best = int(np.argmax(scores))
    if scores[best] <= 0:
        return "", {}
    chosen = [best]
    for i in np.argsort(-scores)[1:]:
        if len(chosen) >= 3 or scores[i] < 0.72 * scores[best]:
            break
        if units[i]["source"] <= units[best]["source"] + 1:    # stay with the top passages
            chosen.append(int(i))
    chosen.sort(key=lambda i: (units[i]["source"], units[i]["position"]))

    parts: list[str] = []
    highlights: dict[int, set[tuple[int, int]]] = {}
    said: set[str] = set()
    for i in chosen:
        unit = units[i]
        sentence = unit["text"]
        if sentence.lower() in said:          # the same sentence can sit in two passages
            continue
        said.add(sentence.lower())
        if sentence and sentence[-1] not in ".!?":
            sentence += "."
        parts.append(f"{sentence} [{unit['source'] + 1}]")
        highlights.setdefault(unit["source"], set()).add((unit["block"], unit["unit"]))
    return " ".join(parts), highlights


def support_highlights(index: Index, answer: str, question: str, hits: list[Hit]) -> dict[int, set[tuple[int, int]]]:
    """For an LLM-written answer, find the units in each cited passage that back it up."""
    cited = {int(n) - 1 for n in CITATION.findall(answer)}
    cited = {n for n in cited if 0 <= n < len(hits)}
    units = explode(hits)
    answer_terms = set(tokenize(CITATION.sub(" ", answer)))
    if not answer_terms or not units:
        return {n: set() for n in cited}
    total = sum(index.bm25.term_weight(t) for t in answer_terms) or 1.0
    highlights: dict[int, set[tuple[int, int]]] = {n: set() for n in cited}
    for source in cited:
        scored = []
        for unit in units:
            if unit["source"] != source or unit["is_header"] or unit["is_question"]:
                continue
            shared = answer_terms & set(tokenize(unit["text"]))
            scored.append((sum(index.bm25.term_weight(t) for t in shared) / total, unit))
        scored.sort(key=lambda pair: -pair[0])
        for score, unit in scored[:2]:
            if score >= 0.12 and (score >= 0.6 * scored[0][0]):
                highlights[source].add((unit["block"], unit["unit"]))
    return highlights


# --------------------------------------------------------------------------
# LLM generators
# --------------------------------------------------------------------------
SYSTEM_PROMPT = """You are the student help desk assistant for {university}. Students ask you about \
syllabus, regulations, notices, FAQs and academic policies.

You are given numbered passages retrieved from the university's official documents. They are the \
only source you may use: a wrong answer about a deadline, a fee or an exam rule can cost a student \
marks or money, so nothing may come from general knowledge or guesswork.

How to answer:
- Answer the question directly in the first sentence, then add only the conditions or exceptions \
a student would need. Keep it under 120 words. Plain sentences; a short list only for steps or \
several parallel items.
- After each claim, cite the passage it came from as [1], [2]. Cite only passages you used.
- Quote numbers, dates, amounts and names exactly as written in the passage.
- If the passages do not contain the answer, reply with exactly {no_answer} and nothing else. \
A passage on a nearby topic is not an answer.
- Students may write casually or mix Hindi and English. Understand them, and reply in simple English."""


def build_messages(question: str, hits: list[Hit], history: list[dict]) -> list[dict]:
    passages = "\n\n".join(
        f"[{n}] {hit.chunk.title} > {hit.chunk.section}"
        + (f" (updated {hit.chunk.updated})" if hit.chunk.updated else "")
        + f"\n{hit.chunk.text}"
        for n, hit in enumerate(hits, start=1)
    )
    earlier = ""
    turns = [t for t in history[-4:] if t.get("content")]
    if turns:
        lines = [f"{'Student' if t['role'] == 'user' else 'Assistant'}: {t['content'][:400]}" for t in turns]
        earlier = "Earlier in this conversation:\n" + "\n".join(lines) + "\n\n"
    user = f"Passages:\n\n{passages}\n\n{earlier}Student's question: {question}"
    return [{"role": "user", "content": user}]


def _system() -> str:
    return SYSTEM_PROMPT.format(university=config.UNIVERSITY_NAME, no_answer=NO_ANSWER)


def gemini_api_key() -> str:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""


def _http_client():
    import httpx

    return httpx.Client(timeout=httpx.Timeout(90.0, connect=10.0))


def gemini_stream(question: str, hits: list[Hit], history: list[dict]) -> Iterator[str]:
    """Stream an answer from the Gemini API (Interactions API, server-sent events)."""
    import httpx

    key = gemini_api_key()
    if not key:
        raise RuntimeError("Gemini needs an API key. Set GEMINI_API_KEY.")
    payload = {
        "model": config.GEMINI_MODEL,
        "system_instruction": _system(),
        "input": build_messages(question, hits, history)[0]["content"],
        "stream": True,
        "store": False,                       # nothing is kept on the server after the reply
        # Short grounded answers need little reasoning. The output cap includes thinking tokens.
        "generation_config": {"thinking_level": "low", "max_output_tokens": 2000},
    }
    headers = {"x-goog-api-key": key, "Api-Revision": config.GEMINI_API_REVISION}
    try:
        with _http_client() as client:
            with client.stream("POST", config.GEMINI_URL, params={"alt": "sse"},
                               json=payload, headers=headers) as response:
                if response.status_code != 200:
                    detail = response.read().decode("utf-8", "replace")
                    try:
                        detail = json.loads(detail)["error"]["message"]
                    except Exception:
                        detail = detail[:300]
                    if response.status_code in (401, 403):
                        raise RuntimeError(f"Gemini API key was rejected. Check GEMINI_API_KEY. ({detail})")
                    if response.status_code == 429:
                        raise RuntimeError("Gemini API rate limit reached. Try again in a minute.")
                    raise RuntimeError(f"Gemini API error {response.status_code}: {detail}")
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    event = json.loads(data)
                    kind = event.get("event_type", "")
                    if kind == "error" or "error" in event:
                        message = (event.get("error") or {}).get("message", "unknown error")
                        raise RuntimeError(f"Gemini: {message}")
                    if kind == "step.delta":
                        delta = event.get("delta") or {}
                        if delta.get("type") == "text" and delta.get("text"):
                            yield delta["text"]
    except httpx.HTTPError as exc:
        raise RuntimeError("Could not reach the Gemini API. Check the internet connection.") from exc


def claude_stream(question: str, hits: list[Hit], history: list[dict]) -> Iterator[str]:
    import anthropic

    client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY from the environment
    try:
        with client.beta.messages.stream(
            model=config.CLAUDE_MODEL,
            max_tokens=8000,
            system=_system(),
            messages=build_messages(question, hits, history),
            output_config={"effort": "low"},          # short grounded answers; no deep reasoning needed
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",                      # if a request is declined, retry on a fallback model
        ) as stream:
            for text in stream.text_stream:
                yield text
            final = stream.get_final_message()
        if final.stop_reason == "refusal":
            raise RuntimeError("Claude declined to answer this request.")
    except anthropic.AuthenticationError as exc:
        raise RuntimeError("Claude API key was rejected. Check ANTHROPIC_API_KEY.") from exc
    except anthropic.RateLimitError as exc:
        raise RuntimeError("Claude API rate limit reached. Try again in a minute.") from exc
    except anthropic.APIStatusError as exc:
        raise RuntimeError(f"Claude API error {exc.status_code}: {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise RuntimeError("Could not reach the Claude API. Check the internet connection.") from exc


# --------------------------------------------------------------------------
# which generators can run right now
# --------------------------------------------------------------------------
_availability: dict = {"at": 0.0, "value": None}


def available_generators(force: bool = False) -> list[dict]:
    if not force and _availability["value"] is not None and time.time() - _availability["at"] < 30:
        return _availability["value"]

    generators = [{
        "id": "extractive", "label": "Quote the documents", "ready": True,
        "detail": "Answers with the exact sentences from the documents. No language model.",
    }]

    gemini = {"id": "gemini", "label": f"Gemini ({config.GEMINI_MODEL})", "ready": False,
              "detail": "Set GEMINI_API_KEY (environment variable or .env file) to turn this on."}
    if gemini_api_key():
        gemini.update(ready=True, detail="Gemini writes the answer from the documents.")
    generators.append(gemini)

    claude = {"id": "claude", "label": f"Claude ({config.CLAUDE_MODEL})", "ready": False,
              "detail": "Set the ANTHROPIC_API_KEY environment variable to turn this on."}
    if os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"):
        try:
            import anthropic  # noqa: F401

            claude.update(ready=True, detail="Claude writes the answer from the documents.")
        except ImportError:
            claude["detail"] = "Install the anthropic package to turn this on."
    generators.append(claude)

    _availability.update(at=time.time(), value=generators)
    return generators


STREAMS = {"gemini": gemini_stream, "claude": claude_stream}
