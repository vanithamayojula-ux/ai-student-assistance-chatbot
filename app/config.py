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

# --- chunking -------------------------------------------------------------
MAX_CHUNK_WORDS = 220      # a section longer than this is split into windows
WINDOW_WORDS = 160
WINDOW_OVERLAP = 40

# --- retrieval ------------------------------------------------------------
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
TOP_K = int(os.getenv("TOP_K", "4"))            # passages handed to the generator
CANDIDATES = 20                                 # passages each retriever contributes to fusion
RRF_K = 60                                      # reciprocal-rank-fusion constant

# Below this confidence the assistant declines to answer instead of guessing.
# The value is chosen on the dev split of the evaluation set by `python -m app.evaluate`.
ABSTAIN_THRESHOLD = float(os.getenv("ABSTAIN_THRESHOLD", "0.50"))
# A looser gate used when a language model writes the answer (it can decline by itself).
LOOSE_THRESHOLD = float(os.getenv("LOOSE_THRESHOLD", "0.35"))

# --- generation -----------------------------------------------------------
# Gemini is called through the Interactions API; the key comes from GEMINI_API_KEY.
GEMINI_URL = os.getenv("GEMINI_URL", "https://generativelanguage.googleapis.com/v1beta/interactions")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_API_REVISION = os.getenv("GEMINI_API_REVISION", "2026-05-20")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_UPLOAD_EXT = {".md", ".txt", ".pdf", ".docx"}
