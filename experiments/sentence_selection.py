"""Scratch experiment 4: how should the quote-only generator pick sentences? Chosen on DEV only."""
import sys, itertools, time
sys.path.insert(0, ".")
from app import config
from app.evaluate import load_questions, _norm
from app.generate import extractive_answer
from app.pipeline import get_engine
e = get_engine()
qs = [q for q in load_questions() if q["type"] == "answerable"]
cache = {q["id"]: e.index.search(q["question"], config.TOP_K) for q in qs}
# Score one settings combination on one split ("dev" or "test"). Returns:
# share of answers containing every key fact, average sentences quoted, seconds per question.
def run(split):
    ok = n = sents = 0; t = time.time()
    for q in qs:
        if q["split"] != split: continue
        ans, hl = extractive_answer(e.index, q["question"], cache[q["id"]])
        n += 1; ok += all(_norm(f) in _norm(ans) for f in q["key_facts"]); sents += sum(len(v) for v in hl.values())
    return ok / n, sents / n, (time.time() - t) / n
grid = [("mix", w, r, 3) for w in (0.25, 0.5) for r in (0.6, 0.72, 0.85)]
out = []
for scorer, w, r, m in grid:
    config.SENTENCE_SCORER, config.SENTENCE_OVERLAP_WEIGHT, config.SENTENCE_KEEP_RATIO, config.SENTENCE_MAX = scorer, w, r, m
    d = run("dev"); t = run("test")
    out.append((d[0], -d[1], scorer, w, r, m, d, t))
    print("%-5s w=%.2f keep=%.2f max=%d | dev facts-all %.3f sents %.2f %4.0fms | test %.3f sents %.2f" % (scorer, w, r, m, d[0], d[1], d[2]*1000, t[0], t[1]))
