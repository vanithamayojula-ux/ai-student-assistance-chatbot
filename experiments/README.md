# Experiments

Scripts behind design decisions that are not part of the application. Each one makes its
choice on the **dev half** of `data/eval/questions.jsonl` and prints the **test half**
next to it, so a result that only holds on the questions it was tuned on is visible.

Run them from the project folder, for example:

```
.venv\Scripts\python experiments\sentence_selection.py
.venv\Scripts\python experiments\gate_signals_and_fitted_gate.py
.venv\Scripts\python experiments\gate_answer_checking_model.py cross-encoder/qnli-distilroberta-base out.json
```

| Script | Question | What it found |
|---|---|---|
| `sentence_selection.py` | Which weights should the quote-only generator use to pick sentences? | 0.25 word overlap + 0.75 embedding similarity, keeping sentences that score at least 72% of the best, gave the most complete answers on dev. These are the defaults in `app/config.py`. |
| `gate_signals_and_fitted_gate.py` | Can other retrieval signals (coverage in the best passage, unknown words, the reranker score) or a logistic regression over them decide better when to decline? | No. Every variant scored between 0.49 and 0.65 balanced accuracy on the test half. The fitted model reached 0.91 on dev and 0.61 on test, which is over-fitting. |
| `gate_answer_checking_model.py` | Does a cross-encoder trained to judge "does this sentence answer the question" (QNLI) decide better? It downloads a 330 MB model. | No. Best test balanced accuracy was 0.66, at about 1.7 s per question. |

The conclusion from the two gate experiments: a near-miss question (right topic, missing
fact) cannot be told from an answerable one by a retrieval score. That decision needs a
model that reads the passage, which is the language model's own `NO_ANSWER` reply.

The Hindi-English rewrite and the reranker are measured by the application's own
evaluation: `python -m app.evaluate --design-choices`.
