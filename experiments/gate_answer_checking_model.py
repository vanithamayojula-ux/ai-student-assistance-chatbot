"""Scratch experiment 2: does a QNLI cross-encoder ("does this sentence answer the question?") gate better?"""
import json, math, sys, time
import numpy as np
sys.path.insert(0, ".")
from app import config
from app.evaluate import load_questions
from app.generate import explode
from app.hinglish import to_search_english
from app.pipeline import get_engine
from app.textutil import tokenize
from fastembed.rerank.cross_encoder import TextCrossEncoder
from huggingface_hub import hf_hub_download
import onnxruntime as ort
from tokenizers import Tokenizer

REPO = sys.argv[1] if len(sys.argv) > 1 else "cross-encoder/qnli-distilroberta-base"
cache = str(config.INDEX_DIR / "models")
model_path = hf_hub_download(REPO, "onnx/model.onnx", cache_dir=cache)
tok = Tokenizer.from_file(hf_hub_download(REPO, "tokenizer.json", cache_dir=cache))
tok.enable_truncation(max_length=256); tok.enable_padding()
sess = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
names = [i.name for i in sess.get_inputs()]

def qnli(question, sentences):
    if not sentences: return []
    enc = tok.encode_batch([(question, s) for s in sentences])
    feed = {"input_ids": np.array([e.ids for e in enc], dtype=np.int64),
            "attention_mask": np.array([e.attention_mask for e in enc], dtype=np.int64)}
    if "token_type_ids" in names: feed["token_type_ids"] = np.array([e.type_ids for e in enc], dtype=np.int64)
    logits = sess.run(None, feed)[0]
    return (1 / (1 + np.exp(-logits[:, 0]))).tolist() if logits.shape[1] == 1 else logits.tolist()

e = get_engine(); idx = e.index
ce = TextCrossEncoder(model_name="Xenova/ms-marco-MiniLM-L-6-v2", cache_dir=cache)
qs = load_questions()
rows = []; t0 = time.time()
for q in qs:
    text = to_search_english(q["question"])
    hits = idx.search(text, 10)
    sc = list(ce.rerank(text, [h.chunk.index_text for h in hits]))
    order = np.argsort(-np.array(sc)); top = [hits[i] for i in order[:4]]; cemax = sc[order[0]]
    units = [u for u in explode(top) if not u["is_header"] and not u["is_question"] and len(u["text"].split()) >= 3]
    probs = qnli(text, [u["text"] for u in units])
    terms = set(tokenize(text)); found = set()
    for h in top: found.update(tokenize(h.chunk.index_text))
    total = sum(idx.bm25.term_weight(t) for t in terms) or 1
    rows.append({"q": q, "cov": sum(idx.bm25.term_weight(t) for t in terms if t in found) / total,
                 "sim": float(np.clip((max(h.dense for h in top) - 0.45) / 0.40, 0, 1)),
                 "ce": 1 / (1 + math.exp(-cemax / 3)), "qnli": max(probs) if probs else 0.0,
                 "qnli_top1": max([p for p, u in zip(probs, units) if u["source"] == 0], default=0.0)})
print("seconds per question", round((time.time() - t0) / len(qs), 2), "| sample logits shape ok")

def ba(rs, conf, t):
    a = [r for r in rs if r["q"]["type"] == "answerable"]; u = [r for r in rs if r["q"]["type"] != "answerable"]
    ans = sum(conf(r) >= t for r in a) / len(a); dec = sum(conf(r) < t for r in u) / len(u)
    return (ans + dec) / 2, ans, dec
dev = [r for r in rows if r["q"]["split"] == "dev"]; test = [r for r in rows if r["q"]["split"] == "test"]
combos = {
    "cov+sim": lambda r: .5*r["cov"] + .5*r["sim"],
    "qnli": lambda r: r["qnli"],
    "qnli_top1": lambda r: r["qnli_top1"],
    "qnli+cov": lambda r: .5*r["qnli"] + .5*r["cov"],
    "qnli+ce": lambda r: .5*r["qnli"] + .5*r["ce"],
    "qnli+cov+sim": lambda r: (r["qnli"] + r["cov"] + r["sim"]) / 3,
    "qnli+cov+sim+ce": lambda r: (r["qnli"] + r["cov"] + r["sim"] + r["ce"]) / 4,
    "2qnli+cov+sim": lambda r: (2*r["qnli"] + r["cov"] + r["sim"]) / 4,
}
for name, conf in combos.items():
    grid = [round(0.05 + 0.01*i, 2) for i in range(94)]
    scored = [(ba(dev, conf, t)[0], t) for t in grid]
    best = max(s for s, _ in scored); plateau = [t for s, t in scored if s == best]; t = plateau[len(plateau)//2]
    print("gate %-16s t=%.2f  dev BA %.3f (ans %.2f dec %.2f) | test BA %.3f (ans %.2f dec %.2f)" % (name, t, *ba(dev, conf, t), *ba(test, conf, t)))
json.dump([{"id": r["q"]["id"], "type": r["q"]["type"], "style": r["q"]["style"], "split": r["q"]["split"],
            **{k: round(r[k], 3) for k in ("cov", "sim", "ce", "qnli", "qnli_top1")}} for r in rows], open(sys.argv[2], "w"))
