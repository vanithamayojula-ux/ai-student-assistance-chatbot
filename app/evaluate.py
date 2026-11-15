"""Evaluation against the labelled student-question set.

Run:  python -m app.evaluate                      (retrieval + extractive answers)
      python -m app.evaluate --generator ollama   (also score LLM-written answers)

What is measured, and why:

Retrieval (answerable questions only), per retriever
  Hit@k   - share of questions whose gold passage is in the top k results.
            If the right passage is not retrieved, no generator can answer.
  MRR     - mean of 1/rank of the gold passage: rewards ranking it first.

Abstention
  The confidence threshold is chosen on the DEV half of the questions and
  reported on the held-out TEST half, so the number is not flattered by
  tuning on the questions it is scored on.

Answers, per generator
  Fact coverage - share of the labelled key facts (dates, amounts, numbers)
                  present in the answer.
  Correct       - answerable: answered with every key fact;
                  unanswerable: the assistant declined.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from datetime import datetime

from . import config
from .pipeline import Engine

KS = (1, 3, 5)


def load_questions() -> list[dict]:
    """Read the labelled questions and give each a dev/test split.

    The split is stratified and deterministic: within each question type the
    questions alternate dev, test, dev, test in file order, so both halves get
    the same mix of answerable and out-of-scope questions.
    """
    questions = []
    seen: dict[str, int] = {}
    with config.EVAL_QUESTIONS.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            question = json.loads(line)
            count = seen.get(question["type"], 0)
            question["split"] = "dev" if count % 2 == 0 else "test"
            seen[question["type"]] = count + 1
            questions.append(question)
    return questions


def split_of(question: dict) -> str:
    return question["split"]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace(",", "")).strip()


def _rank_of_gold(hits, question: dict, level: str) -> int | None:
    for rank, hit in enumerate(hits, start=1):
        if hit.chunk.doc_id not in question["gold_doc_ids"]:
            continue
        if level == "document" or _norm(hit.chunk.section) == _norm(question.get("gold_section", "")):
            return rank
    return None


def _summarise_ranks(ranks: list[int | None]) -> dict:
    n = len(ranks) or 1
    out = {f"hit@{k}": round(sum(1 for r in ranks if r and r <= k) / n, 4) for k in KS}
    out["mrr"] = round(sum(1 / r for r in ranks if r) / n, 4)
    out["n"] = len(ranks)
    return out


def evaluate_retrieval(engine: Engine, questions: list[dict]) -> dict:
    answerable = [q for q in questions if q["type"] == "answerable"]
    report: dict = {}
    for method in engine.index.methods:
        rows = []
        started = time.perf_counter()
        for q in answerable:
            hits = engine.index.search(q["question"], max(KS), method)
            rows.append((q, _rank_of_gold(hits, q, "passage"), _rank_of_gold(hits, q, "document")))
        elapsed = (time.perf_counter() - started) * 1000 / max(len(answerable), 1)
        entry = {
            "passage": _summarise_ranks([r[1] for r in rows]),
            "document": _summarise_ranks([r[2] for r in rows]),
            "ms_per_query": round(elapsed, 1),
            "by_style": {}, "by_category": {},
        }
        for field, bucket in (("style", "by_style"), ("category", "by_category")):
            for value in sorted({q[field] for q in answerable}):
                entry[bucket][value] = _summarise_ranks([r[1] for r in rows if r[0][field] == value])
        report[method] = entry
    return report


def _balanced(records: list[dict], threshold: float) -> dict:
    answerable = [r for r in records if r["type"] == "answerable"]
    unanswerable = [r for r in records if r["type"] == "unanswerable"]
    answered = sum(1 for r in answerable if r["confidence"] >= threshold) / max(len(answerable), 1)
    declined = sum(1 for r in unanswerable if r["confidence"] < threshold) / max(len(unanswerable), 1)
    return {
        "answered_when_answerable": round(answered, 4),
        "declined_when_unanswerable": round(declined, 4),
        "balanced_accuracy": round((answered + declined) / 2, 4),
        "n_answerable": len(answerable), "n_unanswerable": len(unanswerable),
    }


def tune_threshold(engine: Engine, questions: list[dict]) -> dict:
    records = []
    for q in questions:
        _, confidence = engine.retrieve(q["question"])
        records.append({"id": q["id"], "type": q["type"], "split": split_of(q), "confidence": confidence})
    dev = [r for r in records if r["split"] == "dev"]
    test = [r for r in records if r["split"] == "test"]

    candidates = [round(0.20 + 0.01 * i, 2) for i in range(61)]
    scored = [(_balanced(dev, t)["balanced_accuracy"], t) for t in candidates]
    best_score = max(score for score, _ in scored)
    # Several thresholds usually tie; take the middle of the best plateau, the most
    # robust choice (furthest from both failure modes).
    plateau = [t for score, t in scored if score == best_score]
    threshold = plateau[len(plateau) // 2]
    # A second, looser gate for when a language model writes the answer: the model
    # can itself say "the passages do not answer this", so the gate only needs to
    # stop questions with no related passage at all. It is set just below the
    # least confident answerable dev question, so no answerable dev question is
    # blocked before the model has seen the passages.
    lowest = min((r["confidence"] for r in dev if r["type"] == "answerable"), default=threshold)
    loose = round(max(0.05, min(lowest - 0.02, threshold)), 2)
    return {
        "threshold": threshold,
        "loose_threshold": loose,
        "loose_dev": _balanced(dev, loose),
        "loose_test": _balanced(test, loose),
        "dev": _balanced(dev, threshold),
        "test": _balanced(test, threshold),
        "all": _balanced(records, threshold),
        "curve": [{"threshold": t, **_balanced(records, t)} for t in candidates[::5]],
        "confidences": records,
    }


def evaluate_answers(engine: Engine, questions: list[dict], generator: str) -> dict:
    rows = []
    for i, q in enumerate(questions, start=1):
        result = engine.answer(q["question"], generator=generator)
        answer = result.get("answer", "")
        facts = q.get("key_facts", [])
        found = [f for f in facts if _norm(f) in _norm(answer)]
        cited_docs = {s["doc_id"] for s in result.get("sources", []) if s["cited"]}
        if q["type"] == "answerable":
            correct = (not result["abstained"]) and len(found) == len(facts)
        else:
            correct = bool(result["abstained"])
        rows.append({
            "id": q["id"], "question": q["question"], "type": q["type"], "style": q["style"],
            "category": q["category"], "split": split_of(q), "answer": answer,
            "abstained": result["abstained"], "confidence": result["confidence"],
            "facts_total": len(facts), "facts_found": len(found), "correct": correct,
            "cited_gold": bool(cited_docs & set(q["gold_doc_ids"])) if q["type"] == "answerable" else None,
            "latency_ms": result["latency_ms"], "generator_used": result["generator"],
        })
        print(f"\r  {generator}: {i}/{len(questions)}", end="", flush=True)
    print()

    answerable = [r for r in rows if r["type"] == "answerable"]
    unanswerable = [r for r in rows if r["type"] == "unanswerable"]
    answered = [r for r in answerable if not r["abstained"]]
    latencies = sorted(r["latency_ms"] for r in rows)

    def rate(items, key) -> float:
        return round(sum(1 for r in items if r[key]) / max(len(items), 1), 4)

    summary = {
        "n": len(rows),
        "accuracy": rate(rows, "correct"),
        "accuracy_test_split": rate([r for r in rows if r["split"] == "test"], "correct"),
        "answerable_correct": rate(answerable, "correct"),
        "answerable_declined": rate(answerable, "abstained"),
        "fact_coverage": round(sum(r["facts_found"] for r in answered) /
                               max(sum(r["facts_total"] for r in answered), 1), 4),
        "cited_gold_document": rate(answered, "cited_gold"),
        "unanswerable_declined": rate(unanswerable, "abstained"),
        "latency_ms": {
            "mean": round(statistics.mean(latencies)) if latencies else 0,
            "median": round(statistics.median(latencies)) if latencies else 0,
            "p95": latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))] if latencies else 0,
        },
        "by_style": {s: rate([r for r in answerable if r["style"] == s], "correct")
                     for s in sorted({r["style"] for r in answerable})},
        "by_category": {c: rate([r for r in answerable if r["category"] == c], "correct")
                        for c in sorted({r["category"] for r in answerable})},
    }
    return {"summary": summary, "rows": rows}


def run(generators: list[str], limit: int | None = None, engine: Engine | None = None) -> dict:
    engine = engine or Engine()
    questions = load_questions()

    print(f"Corpus: {len(engine.documents)} documents, {len(engine.index.chunks)} passages. "
          f"Questions: {len(questions)}. Retrievers: {', '.join(engine.index.methods)}")
    retrieval = evaluate_retrieval(engine, questions)
    abstention = tune_threshold(engine, questions)
    engine.threshold = abstention["threshold"]
    engine.loose_threshold = abstention["loose_threshold"]
    (config.EVAL_DIR / "threshold.json").write_text(
        json.dumps({"threshold": abstention["threshold"],
                    "loose_threshold": abstention["loose_threshold"]}), encoding="utf-8")

    previous = {}
    if config.EVAL_RESULTS.exists():
        try:
            previous = json.loads(config.EVAL_RESULTS.read_text(encoding="utf-8")).get("answers", {})
        except (json.JSONDecodeError, OSError):
            previous = {}
    answers = {k: v for k, v in previous.items() if k not in generators}
    subset = questions[:limit] if limit else questions
    for generator in generators:
        answers[generator] = evaluate_answers(engine, subset, generator)

    results = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "corpus": {"documents": len(engine.documents), "passages": len(engine.index.chunks)},
        "questions": {
            "total": len(questions),
            "answerable": sum(1 for q in questions if q["type"] == "answerable"),
            "unanswerable": sum(1 for q in questions if q["type"] == "unanswerable"),
        },
        "settings": {"embed_model": config.EMBED_MODEL if engine.index.has_dense else None,
                     "top_k": config.TOP_K, "rrf_k": config.RRF_K},
        "retrieval": retrieval,
        "abstention": abstention,
        "answers": answers,
    }
    config.EVAL_RESULTS.write_text(json.dumps(results, indent=1), encoding="utf-8")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the chatbot on the labelled question set.")
    parser.add_argument("--generator", action="append", choices=["extractive", "ollama", "claude"],
                        help="generator(s) to score; default: extractive")
    parser.add_argument("--limit", type=int, default=None, help="score only the first N questions")
    args = parser.parse_args()
    results = run(args.generator or ["extractive"], args.limit)

    print("\nRetrieval (gold passage in top k)")
    print(f"  {'retriever':<8} {'Hit@1':>7} {'Hit@3':>7} {'Hit@5':>7} {'MRR':>7}")
    for method, entry in results["retrieval"].items():
        p = entry["passage"]
        print(f"  {method:<8} {p['hit@1']:>7.3f} {p['hit@3']:>7.3f} {p['hit@5']:>7.3f} {p['mrr']:>7.3f}")
    ab = results["abstention"]
    print(f"\nLoose gate for LLM answers {ab['loose_threshold']}: held-out test lets through "
          f"{ab['loose_test']['answered_when_answerable']:.0%} of answerable, stops "
          f"{ab['loose_test']['declined_when_unanswerable']:.0%} of unanswerable")
    print(f"Abstention threshold {ab['threshold']} (chosen on dev). Held-out test: "
          f"answered {ab['test']['answered_when_answerable']:.0%} of answerable, "
          f"declined {ab['test']['declined_when_unanswerable']:.0%} of unanswerable")
    for generator, entry in results["answers"].items():
        s = entry["summary"]
        print(f"\nAnswers [{generator}] n={s['n']}: accuracy {s['accuracy']:.1%}, "
              f"fact coverage {s['fact_coverage']:.1%}, median latency {s['latency_ms']['median']} ms")
    print(f"\nSaved to {config.EVAL_RESULTS}")


if __name__ == "__main__":
    main()
