"""Scratch experiment 3: cheaper gate signals (no extra model), and a small fitted gate."""
import json, math, sys
import numpy as np
sys.path.insert(0, ".")
from app.evaluate import load_questions
from app.hinglish import to_search_english
from app.pipeline import get_engine
from app.textutil import tokenize

e = get_engine(); idx = e.index
qs = load_questions()
rows = []
for q in qs:
    text = to_search_english(q["question"])
    hits = idx.search(text, 4, "rerank")            # reranked passages, so the reranker score is a signal
    terms = set(tokenize(text))
    w = {t: idx.bm25.term_weight(t) for t in terms}; total = sum(w.values()) or 1
    per = [set(tokenize(h.chunk.index_text)) for h in hits]
    union = set().union(*per) if per else set()
    cov = lambda found: sum(w[t] for t in terms if t in found) / total
    oov = sum(w[t] for t in terms if t not in idx.bm25.postings) / total
    ce = [h.rerank for h in hits if h.rerank is not None]
    rows.append({"q": q, "cov": cov(union), "cov1": cov(per[0]) if per else 0, "covmax": max((cov(p) for p in per), default=0),
                 "oov": oov, "sim": float(np.clip((max(h.dense for h in hits) - 0.45) / 0.40, 0, 1)) if hits else 0,
                 "sim1": float(np.clip((hits[0].dense - 0.45) / 0.40, 0, 1)) if hits else 0,
                 "ce": 1 / (1 + math.exp(-(ce[0] if ce else 0) / 3)),
                 "gap": 1 / (1 + math.exp(-((ce[0] - ce[1]) if len(ce) > 1 else 0) / 3)),
                 "nterms": min(len(terms), 10) / 10})

# Balanced accuracy of a gate: the average of "answerable questions let through" and
# "unanswerable questions stopped", when the confidence formula `conf` is cut at threshold t.
def ba(rs, conf, t):
    a = [r for r in rs if r["q"]["type"] == "answerable"]; u = [r for r in rs if r["q"]["type"] != "answerable"]
    ans = sum(conf(r) >= t for r in a) / len(a); dec = sum(conf(r) < t for r in u) / len(u)
    return (ans + dec) / 2, ans, dec
dev = [r for r in rows if r["q"]["split"] == "dev"]; test = [r for r in rows if r["q"]["split"] == "test"]

# Try every threshold for one confidence formula on DEV, pick the best, print dev and test scores.
def report(name, conf):
    grid = [round(0.02 + 0.01*i, 2) for i in range(97)]
    scored = [(ba(dev, conf, t)[0], t) for t in grid]
    best = max(s for s, _ in scored); plateau = [t for s, t in scored if s == best]; t = plateau[len(plateau)//2]
    print("gate %-22s t=%.2f  dev BA %.3f (ans %.2f dec %.2f) | test BA %.3f (ans %.2f dec %.2f)" % (name, t, *ba(dev, conf, t), *ba(test, conf, t)))

for name, conf in {
    "cov+sim (current)": lambda r: .5*r["cov"] + .5*r["sim"],
    "cov1": lambda r: r["cov1"], "covmax": lambda r: r["covmax"], "1-oov": lambda r: 1 - r["oov"],
    "cov1+sim1": lambda r: .5*r["cov1"] + .5*r["sim1"],
    "cov1+ce": lambda r: .5*r["cov1"] + .5*r["ce"],
    "cov1+sim1+ce": lambda r: (r["cov1"] + r["sim1"] + r["ce"]) / 3,
    "cov1*(1-oov)": lambda r: r["cov1"] * (1 - r["oov"]),
    "covmax+sim+ce": lambda r: (r["covmax"] + r["sim"] + r["ce"]) / 3,
}.items():
    report(name, conf)

# a small logistic regression fitted on dev only (class-balanced, L2), scored on test
feats = ["cov", "cov1", "oov", "sim1", "ce", "gap", "nterms"]
X = lambda rs: np.array([[r[f] for f in feats] for r in rs]); Y = lambda rs: np.array([1.0 if r["q"]["type"] == "answerable" else 0.0 for r in rs])
Xd, yd = X(dev), Y(dev); mu, sd = Xd.mean(0), Xd.std(0) + 1e-6
# Train a tiny logistic-regression classifier by gradient descent: it learns one weight per
# signal to predict "answerable or not". l2 keeps the weights small so it does not overfit.
def fit(Xs, y, l2=1.0, steps=4000, lr=0.1):
    wts = np.zeros(Xs.shape[1]); b = 0.0
    cw = np.where(y == 1, 0.5 / y.mean(), 0.5 / (1 - y.mean()))
    for _ in range(steps):
        p = 1 / (1 + np.exp(-(Xs @ wts + b))); g = (p - y) * cw
        wts -= lr * (Xs.T @ g / len(y) + l2 * wts / len(y)); b -= lr * g.mean()
    return wts, b
for l2 in (0.3, 1.0, 3.0, 10.0):
    wts, b = fit((Xd - mu) / sd, yd, l2)
    conf = lambda r, wts=wts, b=b: float(1 / (1 + np.exp(-((np.array([r[f] for f in feats]) - mu) / sd @ wts + b))))
    report(f"logistic l2={l2}", conf)
    print("     weights", dict(zip(feats, np.round(wts, 2))))
by = {}
for r in rows:
    if r["q"]["type"] != "answerable": continue
    by.setdefault(r["q"]["style"], []).append(.5*r["cov"] + .5*r["sim"])
print({k: round(float(np.mean(v)), 2) for k, v in by.items()}, "| OOS mean", round(float(np.mean([.5*r['cov']+.5*r['sim'] for r in rows if r['q']['type'] != 'answerable'])), 2))
