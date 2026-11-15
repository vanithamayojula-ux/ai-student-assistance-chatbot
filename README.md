# AI Student Assistance Chatbot (P08)

A RAG (retrieval-augmented generation) chatbot that answers students' academic and
institutional questions from a university knowledge corpus, and shows the passage
each answer came from.

| Project brief (P08, SIH 2024 - SIH1631) | Where it is in this project |
|---|---|
| Students need reliable answers to academic and institutional queries | Every answer is built only from retrieved passages, cites them, and the assistant declines when the documents do not cover the question |
| Build a RAG chatbot over a university knowledge corpus | `app/` - ingest, retrieve (BM25 + embeddings, fused), generate, cite |
| Dataset: syllabus, regulations, notices, FAQs, academic policies | `data/corpus/` - 18 documents in those five categories |
| A labelled student-question evaluation set | `data/eval/questions.jsonl` - 80 labelled questions, scored by `app/evaluate.py` |

> **About the data.** The corpus is sample data for a fictional university
> ("Sutlej Valley University"), written for this project. No real university's rules
> are in it. To use real documents, add them on the Library page or put files in
> `data/corpus/<category>/`.

## Run it

Double-click `run.bat`, or:

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

Then open http://127.0.0.1:8000. The first start downloads a small embedding model
(about 70 MB) once; after that it works offline.

Other commands:

```
.venv\Scripts\python -m pytest -q                          # tests
.venv\Scripts\python -m app.evaluate                       # evaluation, quote-only answers
.venv\Scripts\python -m app.evaluate --generator ollama    # also score local-model answers
```

## How it works

```
                 ingest (once)                         answer (every question)

  documents ──> split at section headings ──> passages
                                                 │
                              ┌──────────────────┴──────────────────┐
                              ▼                                     ▼
                     BM25 keyword index                 sentence embeddings
                              │                                     │
   question ─────────────────>├── rank ──┐               ┌── rank ──┤
                                         ▼               ▼
                                 reciprocal rank fusion (hybrid)
                                              │ top 4 passages
                                              ▼
                              confidence gate: enough evidence?
                                   │ no                  │ yes
                                   ▼                     ▼
                         "not in the documents"   generator writes the answer
                                                  from the passages, with [n] citations
                                                         │
                                                         ▼
                                       answer + passages, supporting sentence marked
```

1. **Ingest** (`app/ingest.py`). Each document is cut at its section headings, so one
   passage is about one topic. Sections over 220 words are split into overlapping
   160-word windows.
2. **Retrieve** (`app/retrieval.py`). Two retrievers rank the passages. BM25 matches
   words, which is strong for exact terms such as course codes. A sentence-embedding
   model (`BAAI/bge-small-en-v1.5`) matches meaning, which is strong for paraphrases.
   Reciprocal rank fusion merges the two ranked lists.
3. **Decide whether to answer** (`Index.confidence`). A score from 0 to 1 combines how
   many of the question's important words appear in the retrieved passages with the
   best embedding similarity. Below a threshold the assistant declines.
4. **Generate** (`app/generate.py`). Three interchangeable generators:
   - *Quote the documents*: no language model. Picks the sentences that best answer
     the question and quotes them. It cannot invent anything and needs no internet.
   - *Local model*: an Ollama model on this computer writes the answer from the
     passages (default `qwen3.5:4b`).
   - *Claude*: the Claude API writes the answer (needs `ANTHROPIC_API_KEY`).

   The language models are instructed to use only the passages, cite them, and reply
   `NO_ANSWER` when the passages do not contain the answer.
5. **Cite**. The interface shows each cited passage with the supporting sentence
   highlighted, so a student can check the answer against the source.

## Project layout

```
app/
  config.py      settings and paths
  ingest.py      read .md/.txt/.pdf/.docx, split into passages
  textutil.py    tokenizer, sentence and table-row splitting
  retrieval.py   BM25, dense embeddings, hybrid fusion, confidence
  generate.py    quote-only, Ollama and Claude answer generators
  pipeline.py    the RAG pipeline (retrieve, gate, generate, cite)
  evaluate.py    evaluation on the labelled question set
  main.py        FastAPI server and API
web/             the interface (plain HTML, CSS, JavaScript)
data/corpus/     the knowledge corpus, one folder per category
data/eval/       questions.jsonl (labels), results.json (last evaluation)
tests/           automated tests
```

## Settings

Set these as environment variables before starting the server.

| Variable | Default | Meaning |
|---|---|---|
| `UNIVERSITY_NAME` | Sutlej Valley University | Name shown in the interface and given to the language model |
| `OLLAMA_MODEL` | qwen3.5:4b | Local model used by "Local model" |
| `ANTHROPIC_API_KEY` | not set | Turns on the Claude generator |
| `CLAUDE_MODEL` | claude-opus-5-5 | Claude model |
| `TOP_K` | 4 | Passages given to the generator |
| `ABSTAIN_THRESHOLD` | from the last evaluation | Confidence below which the assistant declines |

## The evaluation set

`data/eval/questions.jsonl` has 80 questions: 68 answerable and 12 out of scope.
Each answerable question is labelled with the document and section that contain the
answer, a reference answer, and the key facts (dates, amounts, numbers) a correct
answer must contain. Questions come in three wordings:

- **direct** (22): uses the document's own words;
- **paraphrase** (26): same meaning, different words;
- **colloquial** (20): how students type, including Hindi-English mixes.

The out-of-scope questions include near misses such as "What is the PhD stipend?"
when the corpus only covers B.Tech.

Questions are split into dev and test halves, stratified by type. Thresholds are
chosen on dev and reported on test.

## Results

Measured by `python -m app.evaluate` on the sample corpus (18 documents, 160
passages) and the 80 labelled questions. The full numbers are in
`data/eval/results.json` and on the Evaluation page.

**Retrieval** - is the labelled passage in the top k? (68 answerable questions)

| Retriever | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---|---|---|
| BM25 (keywords) | 0.721 | 0.897 | 0.941 | 0.815 |
| Dense (embeddings) | 0.779 | 0.912 | 0.956 | 0.848 |
| **Hybrid (fused)** | **0.779** | **0.941** | **0.971** | **0.862** |

**Declining out-of-scope questions** - threshold 0.59, chosen on the dev half.

| Split | Answered when answerable | Declined when out of scope |
|---|---|---|
| Dev (34 + 6) | 85.3% | 83.3% |
| Test (34 + 6) | 85.3% | 66.7% |

**Answers, quote-only generator** (all 80 questions)

| Metric | Value |
|---|---|
| Correct (right answer, or correctly declined) | 77.5% (75.0% on the test half) |
| Key facts present in the answers given | 92.8% |
| Answer cites the labelled document | 94.8% |
| Out-of-scope questions declined | 75.0% |
| Median latency | 180 ms |
| By wording: direct / paraphrase / colloquial | 95.5% / 80.8% / 55.0% |

## Limitations

- **Colloquial and Hindi-English questions are the weak spot** (55% correct). The
  embedding model is English-only and the keyword index cannot match Hinglish words.
  A multilingual embedding model is the first thing to try.
- **The confidence gate is imperfect.** A retrieval score cannot fully separate a
  paraphrased answerable question from a near-miss out-of-scope one: on the test half
  it wrongly declines 15% of answerable questions and lets through a third of the
  out-of-scope ones. With a language model the gate is loosened (0.31) and the model's
  own `NO_ANSWER` reply is the second check.
- **The out-of-scope set is small** (12 questions, 6 per half), so those percentages
  move in steps of 17 points.
- **Sentence-selection weights were chosen on all answerable questions**, not on the
  dev half only, so the quote-only answer accuracy is slightly optimistic.
- **Language-model answers are not scored here.** The local model (`qwen3.5:4b`) gave
  good grounded answers in manual checks but takes about 30 s per answer on a CPU; a
  full scored run (`--generator ollama`) takes around 40 minutes and was not completed.
  The Claude generator is implemented but has not been run (no API key was available).
- **The corpus is fictional sample data.** Numbers will differ on real documents.
- Scanned PDFs need OCR before upload; there are no user accounts, and conversations
  are stored only in the browser.

## Using your own documents

Use the Library page to upload `.pdf`, `.docx`, `.md` or `.txt` files (up to 10 MB),
or copy files into `data/corpus/<category>/` and restart. Markdown files may start
with a front-matter block (`title`, `doc_id`, `updated`). To evaluate on your own
documents, write questions in the same format as `data/eval/questions.jsonl`.
