"""Paths and tunable settings. Every setting can be overridden with an environment variable."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Read KEY=VALUE lines from a .env file in the project folder (real env vars win)."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv()
DATA_DIR = ROOT / "data"
CORPUS_DIR = DATA_DIR / "corpus"        # the sample corpus shipped with the project
UPLOAD_DIR = DATA_DIR / "uploads"       # documents added through the Library page
INDEX_DIR = DATA_DIR / "index"          # cached embeddings
EVAL_DIR = DATA_DIR / "eval"
EVAL_QUESTIONS = EVAL_DIR / "questions.jsonl"
EVAL_RESULTS = EVAL_DIR / "results.json"
FEEDBACK_LOG = DATA_DIR / "feedback.jsonl"
WEB_DIR = ROOT / "web"

CATEGORIES = ["syllabus", "regulations", "notices", "faqs", "policies"]
CATEGORY_LABELS = {
    "syllabus": "Syllabus",
    "regulations": "Regulations",
    "notices": "Notices",
    "faqs": "FAQs",
    "policies": "Academic policies",
}

UNIVERSITY_NAME = os.getenv("UNIVERSITY_NAME", "Sutlej Valley University")

# Security for a public deployment (see app/security.py).
CHAT_PER_MINUTE = int(os.getenv("CHAT_PER_MINUTE", "20"))     # per client; 0 turns the limit off
FEEDBACK_PER_MINUTE = int(os.getenv("FEEDBACK_PER_MINUTE", "30"))
WRITES_PER_MINUTE = int(os.getenv("WRITES_PER_MINUTE", "10"))   # uploads, deletes and evaluation runs
API_DOCS = os.getenv("API_DOCS", "0") == "1"                  # serve /api/docs (OpenAPI UI)

# --- chunking -------------------------------------------------------------
MAX_CHUNK_WORDS = 220      # a section longer than this is split into windows
WINDOW_WORDS = 160
WINDOW_OVERLAP = 40

# --- retrieval ------------------------------------------------------------
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
# Cross-encoder that re-reads the best candidates together with the question.
# The evaluation always measures it. The assistant uses it only when RERANK_ANSWERS=1:
# on the labelled questions it ranks passages better but does not make the final
# answers more correct, and it adds roughly half a second or more per question on a CPU.
RERANK_MODEL = os.getenv("RERANK_MODEL", "Xenova/ms-marco-MiniLM-L-6-v2")
RERANK_ANSWERS = os.getenv("RERANK_ANSWERS", "0") == "1"
RERANK_CANDIDATES = int(os.getenv("RERANK_CANDIDATES", "10"))   # fused passages the reranker reads
TOP_K = int(os.getenv("TOP_K", "4"))            # passages handed to the generator
CANDIDATES = 20                                 # passages each retriever contributes to fusion
RRF_K = 60                                      # reciprocal-rank-fusion constant

# Below this confidence the assistant declines to answer instead of guessing.
# The value is chosen on the dev split of the evaluation set by `python -m app.evaluate`.
ABSTAIN_THRESHOLD = float(os.getenv("ABSTAIN_THRESHOLD", "0.50"))
# A looser gate used when a language model writes the answer (it can decline by itself).
LOOSE_THRESHOLD = float(os.getenv("LOOSE_THRESHOLD", "0.35"))

# --- quote-only answers ----------------------------------------------------
# How sentences are chosen from the retrieved passages. "cross" scores each sentence
# together with the question using the reranker; "mix" blends shared words with
# embedding similarity. Values chosen on the dev half of the labelled questions.
SENTENCE_SCORER = os.getenv("SENTENCE_SCORER", "mix")
SENTENCE_OVERLAP_WEIGHT = float(os.getenv("SENTENCE_OVERLAP_WEIGHT", "0.25"))   # "mix" only: share given to shared words, the rest to meaning
SENTENCE_KEEP_RATIO = float(os.getenv("SENTENCE_KEEP_RATIO", "0.72"))   # extra sentences must score this share of the best
SENTENCE_MAX = int(os.getenv("SENTENCE_MAX", "3"))

# --- generation -----------------------------------------------------------
# Gemini is called through the Interactions API; the key comes from GEMINI_API_KEY.
GEMINI_URL = os.getenv("GEMINI_URL", "https://generativelanguage.googleapis.com/v1beta/interactions")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_API_REVISION = os.getenv("GEMINI_API_REVISION", "2026-05-20")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")

# The locally trained model (app/local_model.py, trained by training/train.py).
LOCAL_MODEL_DIR = Path(os.getenv("LOCAL_MODEL_DIR", str(ROOT / "models" / "svu-flan-t5")))
LOCAL_PASSAGES = int(os.getenv("LOCAL_PASSAGES", "3"))                  # top passages the model reads (4 costs a third more CPU time)
LOCAL_MAX_INPUT_TOKENS = int(os.getenv("LOCAL_MAX_INPUT_TOKENS", "1024"))
LOCAL_BEAMS = int(os.getenv("LOCAL_BEAMS", "4"))
LOCAL_NUMBER_CHECK = os.getenv("LOCAL_NUMBER_CHECK", "1") == "1"        # reject answers with figures not in the passages

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_UPLOAD_EXT = {".md", ".txt", ".pdf", ".docx"}
