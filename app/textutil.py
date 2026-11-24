"""Small text helpers shared by retrieval and generation."""
from __future__ import annotations

import re

TOKEN = re.compile(r"[a-z0-9]+(?:\.\d+)?")

STOPWORDS = frozenset("""
a about above after again all am an and any are as at be because been before being below
between both but by can could did do does doing down during each few for from further had
has have having he her here hers him his how i if in into is it its itself just me more most
my no nor not now of off on once only or other our out over own same she should so some such
than that the their them then there these they this those through to too under until up very
was we were what when where which while who whom why will with would you your yours
please tell know want need get kindly sir mam maam hi hello hey thanks thank
""".split())

_SUFFIXES = ("ations", "ation", "ments", "ment", "ings", "ing", "ied", "ies", "ed", "es", "s")


def stem(word: str) -> str:
    """A deliberately light stemmer: 'exams' and 'exam' should match, nothing clever."""
    if len(word) <= 3 or word[0].isdigit():
        return word
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            base = word[: -len(suffix)]
            if suffix in ("ied", "ies"):
                return base + "y"
            return base
    return word


def tokenize(text: str, keep_stopwords: bool = False) -> list[str]:
    """Break text into the words that matter for searching.

    Lower-cases the text, splits it into words and numbers, removes filler words
    ("the", "is", "please" - called stopwords) and trims word endings (stemming).
    Example: "What are the exam fees?" -> ["exam", "fee"].
    """
    tokens = TOKEN.findall(text.lower())
    if keep_stopwords:
        return [stem(t) for t in tokens]
    return [stem(t) for t in tokens if t not in STOPWORDS]


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(*])")
_ABBREV = re.compile(r"\b(?:Rs|No|Dr|Mr|Mrs|Ms|Prof|Sec|Reg|vs|etc|e\.g|i\.e|B\.Tech|M\.Tech|Ph\.D)\.$", re.I)


_LIST_ITEM = re.compile(r"(?:[-+]|\*(?!\*)|\d+[.)])\s+")


def _sentences(paragraph: str) -> list[str]:
    """Split a paragraph into sentences, without breaking after short forms like "Rs." or "Dr."."""
    merged: list[str] = []
    for piece in _SENTENCE_END.split(paragraph):
        if merged and _ABBREV.search(merged[-1]):
            merged[-1] = merged[-1] + " " + piece     # "Rs." did not end the sentence
        else:
            merged.append(piece)
    return [p.strip() for p in merged if p.strip()]


def split_blocks(text: str) -> list[dict]:
    """Split a chunk into blocks of citeable units.

    Returns [{"kind": "prose" | "list" | "table", "units": [str, ...]}]. A unit is
    a sentence, a list item or a table row: a table row or a bullet is kept
    whole, because half a row of a grade table is not evidence of anything.
    For a table the first unit is the header row.
    """
    blocks: list[dict] = []

    def add(kind: str, units: list[str]) -> None:
        """Add units to the result; consecutive list items or table rows stay in one block."""
        if not units:
            return
        if blocks and blocks[-1]["kind"] == kind and kind != "prose":
            blocks[-1]["units"].extend(units)
        else:
            blocks.append({"kind": kind, "units": units})

    for para in re.split(r"\n\s*\n", text):
        prose: list[str] = []
        for line in (ln.strip() for ln in para.splitlines()):
            if not line:
                continue
            if line.startswith("|"):
                kind = "table"
            elif _LIST_ITEM.match(line):
                kind = "list"
            else:
                prose.append(line)
                continue
            if prose:
                add("prose", _sentences(" ".join(prose)))
                prose = []
            if kind == "table" and re.fullmatch(r"\|?[\s:|-]+\|?", line):
                continue                              # the |---|---| separator row
            add(kind, [line])
        if prose:
            add("prose", _sentences(" ".join(prose)))
    return blocks


def table_cells(row: str) -> list[str]:
    """Split one table row "| A | 80-89 |" into its cells ["A", "80-89"]."""
    return [c.strip() for c in row.strip().strip("|").split("|")]


def clean_unit(unit: str, header: str | None = None) -> str:
    """Turn a markdown unit into plain prose for an answer.

    A table row is read out against its header: "Grade: A, Marks: 80-89".
    """
    text = unit.strip()
    if text.startswith("|"):
        cells = table_cells(text)
        heads = table_cells(header) if header else []
        if heads and len(heads) == len(cells):
            text = ", ".join(f"{h}: {c}" for h, c in zip(heads, cells) if c) + "."
        else:
            text = ", ".join(c for c in cells if c) + "."
    text = _LIST_ITEM.sub("", text, count=1) if _LIST_ITEM.match(text) else text
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*", r"\1", text)
    text = re.sub(r"^(?:Q|A)\s*[:.]\s*", "", text)
    return text.strip()
