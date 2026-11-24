"""Test the trained local answer model. Writes data/eval/local_model_test.json.

Run:  python -m training.test_model

Tests (the TEST half of the labelled questions was never used in training or tuning):
  1. model only      the model reads the retrieved passages and answers; no confidence gate
  2. before training the same questions put to the untrained base model, to show what training added
  3. full chatbot    question -> retrieval -> gate -> local model, beside the quote-only generator
  4. unseen document a document that is not in the corpus and that no training question came from
  5. faithfulness    are the figures in each answer present in the passages it was given
  6. speed           seconds per answer on this computer's CPU
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from datetime import datetime

from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

from app import config, evaluate, local_model
from app.ingest import chunk_document, load_document
from app.pipeline import Engine
from app.retrieval import Index
from training.train import answer_all, labelled_examples, score_answer

RESULTS = config.EVAL_DIR / "local_model_test.json"
UNSEEN_DIR = config.EVAL_DIR / "unseen"
CITED = re.compile(r"\[(\d+)\]")
ZERO_SHOT = ("Answer the question using only the context. Cite the passage number like [1]. "
             "If the context does not contain the answer, reply NO_ANSWER.\n\n{input}")


def _words(text: str) -> list[str]:
    """The words of a text, lower-cased, with citations like [1] and commas removed."""
    return re.findall(r"[a-z0-9%]+", CITED.sub(" ", text).lower().replace(",", ""))


def token_f1(answer: str, reference: str) -> float:
    """Word-overlap score (0..1) between the model's answer and the reference answer.

    precision = share of the answer's words that are in the reference
    recall    = share of the reference's words that are in the answer
    F1 combines the two, so an answer must be both correct and complete to score high.
    """
    a, r = _words(answer), _words(reference)
    common = sum(min(a.count(w), r.count(w)) for w in set(a))
    if not common:
        return 0.0
    precision, recall = common / len(a), common / len(r)
    return 2 * precision * recall / (precision + recall)


def rouge_l(answer: str, reference: str) -> float:
    """ROUGE-L: a standard score (0..1) for comparing a written answer with a reference.

    It finds the longest run of words that appear in the SAME ORDER in both texts
    (the longest common subsequence), so word order counts, unlike token_f1.
    """
    a, r = _words(answer), _words(reference)
    if not a or not r:
        return 0.0
    row = [0] * (len(r) + 1)
    for word in a:                                   # longest common subsequence
        previous = 0
        for j, other in enumerate(r, start=1):
            current = row[j]
            row[j] = previous + 1 if word == other else max(row[j], row[j - 1])
            previous = current
    lcs = row[-1]
    if not lcs:
        return 0.0
    precision, recall = lcs / len(a), lcs / len(r)
    return 2 * precision * recall / (precision + recall)


def rate(flags: list[bool]) -> float:
    """Share of True values in a list, e.g. [True, True, False, False] -> 0.5."""
    return round(sum(flags) / max(len(flags), 1), 4)


def summarise(questions: list[dict], answers: list[str], hits_of: list | None = None) -> dict:
    """Score raw model answers. `hits_of[i]` (optional) are the passages question i was given."""
    rows = []
    for i, (q, answer) in enumerate(zip(questions, answers)):
        answerable = q["type"] == "answerable"
        facts = q.get("key_facts", [])
        norm = evaluate._norm
        found = [f for f in facts if norm(f) in norm(answer)]
        row = {"id": q["id"], "question": q["question"], "type": q["type"], "style": q.get("style", ""),
               "category": q.get("category", ""), "answer": answer, "declined": local_model.declined(answer),
               "correct": score_answer(q, answer), "facts_total": len(facts), "facts_found": len(found)}
        if answerable and q.get("reference_answer") and not row["declined"]:
            row["token_f1"] = round(token_f1(answer, q["reference_answer"]), 4)
            row["rouge_l"] = round(rouge_l(answer, q["reference_answer"]), 4)
        if hits_of is not None:
            passages = local_model.passages_of(hits_of[i])
            row["unsupported_numbers"] = [] if row["declined"] else local_model.unsupported_numbers(answer, passages)
            if answerable and not row["declined"]:
                cited = [int(n) - 1 for n in CITED.findall(answer)]
                row["has_citation"] = bool(cited)
                row["cites_gold_passage"] = any(
                    0 <= n < len(hits_of[i]) and hits_of[i][n].chunk.doc_id in q.get("gold_doc_ids", [])
                    and norm(hits_of[i][n].chunk.section) == norm(q.get("gold_section", ""))
                    for n in cited)
        rows.append(row)

    answerable = [r for r in rows if r["type"] == "answerable"]
    outside = [r for r in rows if r["type"] != "answerable"]
    answered = [r for r in answerable if not r["declined"]]
    summary = {
        "n": len(rows), "n_answerable": len(answerable), "n_unanswerable": len(outside),
        "accuracy": rate([r["correct"] for r in rows]),
        "answerable_correct": rate([r["correct"] for r in answerable]),
        "answerable_declined": rate([r["declined"] for r in answerable]),
        "answerable_wrong": rate([not r["correct"] and not r["declined"] for r in answerable]),
        "unanswerable_declined": rate([r["declined"] for r in outside]),
        "fact_coverage": round(sum(r["facts_found"] for r in answered) / max(sum(r["facts_total"] for r in answered), 1), 4),
        "token_f1": round(statistics.mean([r["token_f1"] for r in answered if "token_f1" in r] or [0]), 4),
        "rouge_l": round(statistics.mean([r["rouge_l"] for r in answered if "rouge_l" in r] or [0]), 4),
        "by_style": {s: rate([r["correct"] for r in answerable if r["style"] == s])
                     for s in sorted({r["style"] for r in answerable})},
        "by_category": {c: rate([r["correct"] for r in answerable if r["category"] == c])
                        for c in sorted({r["category"] for r in answerable if r["category"]})},
    }
    if hits_of is not None:
        not_declined = [r for r in rows if not r["declined"]]
        summary["has_citation"] = rate([r.get("has_citation", False) for r in answered])
        summary["cites_gold_passage"] = rate([r.get("cites_gold_passage", False) for r in answered])
        summary["answers_with_unsupported_number"] = rate([bool(r["unsupported_numbers"]) for r in not_declined])
    return {"summary": summary, "rows": rows}


def pipeline_summary(engine: Engine, questions: list[dict], generator: str) -> dict:
    """Score the WHOLE chatbot (search + gate + generator), not the model on its own.

    Adds two rates: answerable questions answered wrongly, and answers where the
    chatbot fell back to quoting the documents.
    """
    result = evaluate.evaluate_answers(engine, questions, generator)
    answerable = [r for r in result["rows"] if r["type"] == "answerable"]
    result["summary"]["answerable_wrong"] = rate([not r["correct"] and not r["abstained"] for r in answerable])
    result["summary"]["fell_back_to_quotes"] = rate([r["generator_used"] != generator for r in result["rows"]])
    return result


def main() -> None:
    """Run the six tests listed at the top of this file and save the results as JSON."""
    parser = argparse.ArgumentParser(description="Test the trained local answer model.")
    parser.add_argument("--limit", type=int, default=None,
                        help="quick check on the first N questions of each set; results go to a separate file")
    limit = parser.parse_args().limit
    results_file = RESULTS.with_suffix(".quick.json") if limit else RESULTS
    started = time.time()
    if not local_model.is_trained():
        raise SystemExit("No trained model found. Run: python -m training.train")
    log = json.loads((config.LOCAL_MODEL_DIR / "training_log.json").read_text(encoding="utf-8"))
    engine = Engine()
    tokenizer, model = local_model.load()
    questions = evaluate.load_questions()
    test_q = [q for q in questions if q["split"] == "test"][:limit]
    dev_q = [q for q in questions if q["split"] == "dev"][:limit]
    out: dict = {"generated_at": datetime.now().isoformat(timespec="seconds"),
                 "model": {"base_model": log["base_model"], "parameters": log["parameters"],
                           "best_epoch": log.get("best_epoch"), "beams": config.LOCAL_BEAMS,
                           "passages": config.LOCAL_PASSAGES}}

    # 1. model only, held-out test questions -------------------------------------------------
    test = labelled_examples(engine, "test")[:limit]
    hits = [engine.index.search(q["question"], config.TOP_K) for q in test]
    print("1/6 model only")
    clock = time.time()
    answers = answer_all(model, tokenizer, [t["input"] for t in test], batch_size=1, beams=config.LOCAL_BEAMS)
    out["model_only_test"] = summarise(test, answers, hits)
    out["model_only_test"]["summary"]["seconds_per_answer"] = round((time.time() - clock) / len(test), 2)
    out["retrieval_ceiling_test"] = rate([
        any(h.chunk.doc_id in q["gold_doc_ids"] and evaluate._norm(h.chunk.section) == evaluate._norm(q.get("gold_section", ""))
            for h in hs) for q, hs in zip(test, hits) if q["type"] == "answerable"])

    # 2. the untrained base model on the same questions ---------------------------------------
    print("2/6 before training")
    base_tokenizer = AutoTokenizer.from_pretrained(log["base_model"])
    base = AutoModelForSeq2SeqLM.from_pretrained(log["base_model"])
    base_answers = answer_all(base, base_tokenizer, [ZERO_SHOT.format(input=t["input"]) for t in test],
                              batch_size=1, beams=config.LOCAL_BEAMS)
    out["base_model_test"] = summarise(test, base_answers, hits)
    del base

    # 3. the whole chatbot ------------------------------------------------------------------
    # Which gate suits the local model is decided on DEV, then both are reported on TEST.
    print("3/6 full chatbot")
    # The local model runs behind the loose gate. A stricter gate only turns some of those
    # answers into declines, so its result is derived from the same run.
    strict = engine.threshold
    runs = {"dev": pipeline_summary(engine, dev_q, "local"), "test": pipeline_summary(engine, test_q, "local")}

    def with_strict_gate(result: dict) -> dict:
        """Work out the scores the same run would get behind the stricter confidence gate."""
        rows = [{**r, "abstained": True, "correct": r["type"] != "answerable"} if r["confidence"] < strict else r
                for r in result["rows"]]
        answerable = [r for r in rows if r["type"] == "answerable"]
        return {"accuracy": rate([r["correct"] for r in rows]),
                "answerable_correct": rate([r["correct"] for r in answerable]),
                "answerable_declined": rate([r["abstained"] for r in answerable]),
                "unanswerable_declined": rate([r["abstained"] for r in rows if r["type"] != "answerable"])}

    keep = ("accuracy", "answerable_correct", "answerable_declined", "unanswerable_declined")
    gates = {"loose": {"threshold": engine.loose_threshold,
                       **{split: {k: runs[split]["summary"][k] for k in keep} for split in runs}},
             "strict": {"threshold": strict, **{split: with_strict_gate(runs[split]) for split in runs}}}
    out["pipeline"] = {
        "gate_chosen_on_dev": max(gates, key=lambda name: gates[name]["dev"]["accuracy"]),
        "gates": gates,
        "local_test": runs["test"],
        "extractive_test": pipeline_summary(engine, test_q, "extractive"),
    }

    # 4. a document the model has never seen ---------------------------------------------------
    print("4/6 unseen document")
    path = next(UNSEEN_DIR.glob("*.md"))
    doc = load_document(path, "policies", "upload")
    index = Index(engine.index.chunks + chunk_document(doc))         # as if it had just been uploaded
    with (UNSEEN_DIR / "questions.jsonl").open(encoding="utf-8") as handle:
        unseen = [json.loads(line) for line in handle if line.strip()]
    if limit:
        unseen = unseen[:limit // 2] + unseen[-(limit - limit // 2):]      # keep both kinds of question
    unseen_hits = [index.search(q["question"], config.TOP_K) for q in unseen]
    unseen_inputs = [local_model.build_input(q["question"], local_model.passages_of(h)) for q, h in zip(unseen, unseen_hits)]
    unseen_answers = answer_all(model, tokenizer, unseen_inputs, batch_size=1, beams=config.LOCAL_BEAMS)
    out["unseen_document"] = summarise(unseen, unseen_answers, unseen_hits)
    out["unseen_document"]["document"] = doc.title
    out["unseen_document"]["retrieved"] = rate([any(h.chunk.doc_id == doc.doc_id for h in hs)
                                                for q, hs in zip(unseen, unseen_hits) if q["type"] == "answerable"])

    # 5. faithfulness: does the number check catch wrong answers? -----------------------------
    print("5/6 faithfulness")
    rows = out["model_only_test"]["rows"] + out["unseen_document"]["rows"]
    answered = [r for r in rows if not r["declined"]]
    flagged = [r for r in answered if r["unsupported_numbers"]]
    out["faithfulness"] = {
        "answers_checked": len(answered),
        "flagged": len(flagged),
        "flagged_that_were_wrong": sum(1 for r in flagged if not r["correct"]),
        "flagged_that_were_right": sum(1 for r in flagged if r["correct"]),
        "wrong_answers_not_flagged": sum(1 for r in answered if not r["correct"] and not r["unsupported_numbers"]),
        "examples": [{"question": r["question"], "answer": r["answer"], "not_in_passages": r["unsupported_numbers"]}
                     for r in flagged[:6]],
    }

    # 6. speed --------------------------------------------------------------------------------
    print("6/6 speed")
    out["speed"] = {
        "local_pipeline_ms": out["pipeline"]["local_test"]["summary"]["latency_ms"],
        "extractive_pipeline_ms": out["pipeline"]["extractive_test"]["summary"]["latency_ms"],
        "model_only_seconds_per_answer": out["model_only_test"]["summary"]["seconds_per_answer"],
    }
    out["minutes"] = round((time.time() - started) / 60, 1)
    results_file.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")

    s = out["model_only_test"]["summary"]
    print(f"\nModel only, test split (n={s['n']}): accuracy {s['accuracy']:.1%}, "
          f"answerable correct {s['answerable_correct']:.1%}, declined out-of-scope {s['unanswerable_declined']:.1%}")
    print(f"Before training: accuracy {out['base_model_test']['summary']['accuracy']:.1%}")
    print(f"Full chatbot, test split: local {out['pipeline']['local_test']['summary']['accuracy']:.1%} "
          f"(loose gate), quote-only {out['pipeline']['extractive_test']['summary']['accuracy']:.1%}")
    print(f"Unseen document: accuracy {out['unseen_document']['summary']['accuracy']:.1%}")
    print(f"Saved to {results_file}")


if __name__ == "__main__":
    main()
