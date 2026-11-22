"""Build the training set for the local answer model.

Run:  python -m training.data

Input:  data/train/raw/batch_*.jsonl          question + answer + the section that holds it
        data/train/raw/unanswerable_*.jsonl   questions the documents do not answer
Output: data/train/train.jsonl                {"input", "target", "kind", ...}, one example per line

Every question is run through the real retriever, so the model is trained on the
same kind of context it will see when the chatbot is used: the right passage mixed
with related wrong ones, in the order retrieval returned them.

Kinds of example
  answer     the passages contain the answer        -> answer + [n] citing the passage that holds it
  shuffled   the same, passages in a random order    -> so the citation follows the passage, not the rank
  removed    the answering passage is taken out      -> NO_ANSWER (a near-miss the model must decline)
  outside    a question the documents do not cover   -> NO_ANSWER

The labelled evaluation questions (data/eval/questions.jsonl) are never used for
training; a training question that is nearly the same as one of them is dropped.
"""
from __future__ import annotations

import json
import random
import re
from collections import Counter

from app import config
from app.local_model import NO_ANSWER, build_input, passages_of
from app.pipeline import Engine
from app.textutil import tokenize

RAW_DIR = config.DATA_DIR / "train" / "raw"
TRAIN_FILE = config.DATA_DIR / "train" / "train.jsonl"
SUMMARY_FILE = config.DATA_DIR / "train" / "summary.json"
NEAR_DUPLICATE = 0.7          # word-set overlap with an evaluation question above which a training question is dropped
_NUMBER = re.compile(r"\d+(?:[.,:]\d+)*")


def _read(pattern: str) -> list[dict]:
    rows = []
    for path in sorted(RAW_DIR.glob(pattern)):
        with path.open(encoding="utf-8") as handle:
            rows += [json.loads(line) for line in handle if line.strip()]
    return rows


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace(",", "")).strip()


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _overlap(a: set[str], b: set[str]) -> float:
    return len(a & b) / max(len(a | b), 1)


def holder(hits, row: dict) -> int | None:
    """Position in `hits` of the passage that holds the answer, or None.

    A long section is split into overlapping windows, so several retrieved passages
    can come from the right section; the one sharing most of the answer's figures
    and words is the one to cite.
    """
    answer_numbers = set(_NUMBER.findall(row["answer"].replace(",", "")))
    answer_terms = set(tokenize(row["answer"]))
    best, best_score = None, 0.0
    for n, hit in enumerate(hits):
        chunk = hit.chunk
        if chunk.doc_id != row["doc_id"] or _norm(chunk.section) != _norm(row["section"]):
            continue
        text = chunk.text.replace(",", "")
        numbers = sum(1 for number in answer_numbers if number in text)
        if answer_numbers and numbers < len(answer_numbers):
            continue                                   # this window lacks one of the figures
        score = 1 + numbers + len(answer_terms & set(tokenize(chunk.text))) / max(len(answer_terms), 1)
        if score > best_score:
            best, best_score = n, score
    return best


def answer_leaks(row: dict, hits) -> bool:
    """True when the remaining passages could still answer the question (same figures elsewhere)."""
    numbers = set(_NUMBER.findall(row["answer"].replace(",", "")))
    if not numbers:
        return True            # no figure to check against: cannot be sure, so do not use as a negative
    context = " ".join(hit.chunk.text for hit in hits).replace(",", "")
    return all(number in context for number in numbers)


def build(seed: int = 7) -> dict:
    rng = random.Random(seed)
    engine = Engine()
    k = config.LOCAL_PASSAGES

    eval_words = []
    if config.EVAL_QUESTIONS.exists():
        with config.EVAL_QUESTIONS.open(encoding="utf-8") as handle:
            eval_words = [_words(json.loads(line)["question"]) for line in handle if line.strip()]

    def too_close(question: str) -> bool:
        words = _words(question)
        return any(_overlap(words, other) >= NEAR_DUPLICATE for other in eval_words)

    examples: list[dict] = []
    dropped = Counter()
    seen: set[str] = set()

    for row in _read("batch_*.jsonl"):
        question = row["question"].strip()
        if _norm(question) in seen:
            dropped["duplicate"] += 1
            continue
        seen.add(_norm(question))
        if too_close(question):
            dropped["too close to an evaluation question"] += 1
            continue
        wide = engine.index.search(question, k + 6)
        hits = wide[:k]
        at = holder(hits, row)
        meta = {"doc_id": row["doc_id"], "style": row.get("style", ""), "question": question}
        if at is None:
            dropped["answer passage not retrieved"] += 1
            continue
        answer = row["answer"].strip()
        kind = "answer"
        if rng.random() < 0.5:           # half the time the passages are handed over in a different order
            order = list(range(len(hits)))
            rng.shuffle(order)
            hits, at, kind = [hits[i] for i in order], order.index(at), "shuffled"
        examples.append({"input": build_input(question, passages_of(hits)),
                         "target": f"{answer} [{at + 1}]", "kind": kind, **meta})

        # Take every passage of the answering section out and refill from further down the ranking.
        rest = [h for h in wide if not (h.chunk.doc_id == row["doc_id"]
                                        and _norm(h.chunk.section) == _norm(row["section"]))][:k]
        if len(rest) == k and not answer_leaks(row, rest) and rng.random() < 0.5:
            examples.append({"input": build_input(question, passages_of(rest)),
                             "target": NO_ANSWER, "kind": "removed", **meta})

    for row in _read("unanswerable_*.jsonl"):
        question = row["question"].strip()
        if _norm(question) in seen:
            dropped["duplicate"] += 1
            continue
        seen.add(_norm(question))
        if too_close(question):
            dropped["too close to an evaluation question"] += 1
            continue
        hits = engine.index.search(question, k)
        examples.append({"input": build_input(question, passages_of(hits)), "target": NO_ANSWER,
                         "kind": "outside", "doc_id": "", "style": row.get("style", ""), "question": question})

    rng.shuffle(examples)
    TRAIN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with TRAIN_FILE.open("w", encoding="utf-8") as handle:
        for example in examples:
            handle.write(json.dumps(example, ensure_ascii=False) + "\n")

    summary = {
        "examples": len(examples),
        "by_kind": dict(Counter(e["kind"] for e in examples)),
        "by_style": dict(Counter(e["style"] for e in examples)),
        "by_document": dict(sorted(Counter(e["doc_id"] for e in examples if e["doc_id"]).items())),
        "questions_written": len(_read("batch_*.jsonl")) + len(_read("unanswerable_*.jsonl")),
        "dropped": dict(dropped),
        "passages_per_example": k,
        "seed": seed,
    }
    SUMMARY_FILE.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(build(), indent=1))
