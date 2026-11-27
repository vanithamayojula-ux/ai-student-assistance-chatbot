"""Smoke test for the LPU and AICTE documents: 27 answerable questions and 5 out-of-scope ones.

Run:  python -m experiments.lpu_smoke_check                       (quote-only answers -> data/eval/lpu_smoke_results.json)
      python -m experiments.lpu_smoke_check --generator local     (the trained local model -> lpu_smoke_results_local.json)

Marking is the same as in app/evaluate.py: an answerable question is correct when the
chatbot answers and the answer contains every key fact; an out-of-scope question is correct
when the chatbot declines. It also records whether the first cited document is the expected one.
These questions are NOT used to tune anything; they only measure.
"""
import argparse
import json
import sys
from collections import Counter

sys.path.insert(0, ".")
from app import config  # noqa: E402
from app.evaluate import _norm  # noqa: E402
from app.pipeline import Engine  # noqa: E402

QUESTIONS = config.EVAL_DIR / "lpu_smoke_questions.jsonl"
RESULTS_DIR = config.EVAL_DIR


def main() -> None:
    """Ask every question for real and save a row per question plus a summary."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--generator", default="extractive", choices=["extractive", "local", "gemini", "claude"])
    generator = parser.parse_args().generator
    results_file = RESULTS_DIR / ("lpu_smoke_results.json" if generator == "extractive" else f"lpu_smoke_results_{generator}.json")
    engine = Engine()
    rows = []
    for line in QUESTIONS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        q = json.loads(line)
        result = engine.answer(q["question"], generator=generator)
        cited = [s["doc_id"] for s in result["sources"] if s["cited"]]
        found = [f for f in q["key_facts"] if _norm(f) in _norm(result["answer"])]
        answerable = q["type"] == "answerable"
        correct = (not result["abstained"] and len(found) == len(q["key_facts"])) if answerable else result["abstained"]
        rows.append({**q, "abstained": result["abstained"], "confidence": result["confidence"], "cited": cited,
                     "facts_found": len(found), "correct": correct, "generator_used": result["generator"],
                     "right_document": bool(cited and cited[0] in q["gold_doc_ids"]) if answerable else None,
                     "answer": result["answer"]})
    ans = [r for r in rows if r["type"] == "answerable"]
    out = [r for r in rows if r["type"] != "answerable"]
    summary = {
        "n": len(rows), "n_answerable": len(ans), "n_unanswerable": len(out),
        "answerable_correct": sum(r["correct"] for r in ans) / len(ans),
        "answerable_declined": sum(r["abstained"] for r in ans) / len(ans),
        "right_first_document": sum(bool(r["right_document"]) for r in ans) / len(ans),
        "unanswerable_declined": sum(r["correct"] for r in out) / len(out),
        "overall": sum(r["correct"] for r in rows) / len(rows),
        "by_style": {s: sum(r["correct"] for r in ans if r["style"] == s) / n for s, n in Counter(r["style"] for r in ans).items()},
        "generator": generator, "threshold": engine.threshold, "documents": len(engine.documents), "passages": len(engine.index.chunks),
    }
    results_file.write_text(json.dumps({"summary": summary, "rows": rows}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    for r in rows:
        if not r["correct"] or r["right_document"] is False:
            print(f"- {r['id']} {'WRONG' if not r['correct'] else 'ok-but-other-doc'}: {r['question']}\n    cited={r['cited']} conf={r['confidence']} facts={r['facts_found']}/{len(r['key_facts'])}\n    A: {r['answer'][:200]}")


if __name__ == "__main__":
    main()
