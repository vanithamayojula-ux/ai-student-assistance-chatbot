"""Ingestion: read documents from disk and cut them into retrievable chunks.

Why chunk at all? A retriever ranks *passages*, not whole files. If a 2,000-word
regulation is one unit, the generator gets a wall of text and the citation is
vague. Cutting at section headings keeps each chunk about one topic, so the
passage that is retrieved is also the passage that is cited.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from pathlib import Path

from . import config

FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
HEADING = re.compile(r"^(#{1,3})\s+(.*\S)\s*$")


@dataclass
class Chunk:
    """One passage: a small piece of a document that can be searched and cited.

    The chatbot never searches whole files. It searches chunks, and the chunk that is
    found is also the one shown to the student as the source.
    """
    chunk_id: str      # e.g. "REG-01#3"
    doc_id: str
    title: str
    category: str
    section: str       # heading of the section this chunk came from
    text: str
    updated: str
    origin: str        # "sample" (shipped, fictional), "official" (shipped, from real public pages) or "upload"

    def to_dict(self) -> dict:
        """The chunk as a plain dictionary (easy to turn into JSON)."""
        return asdict(self)

    @property
    def index_text(self) -> str:
        """Text the retrievers see: the heading gives a short chunk its context."""
        return f"{self.title}. {self.section}. {self.text}"


@dataclass
class Document:
    """One whole file from the knowledge base, already split into its sections."""
    doc_id: str
    title: str
    category: str
    updated: str
    origin: str
    path: Path
    sections: list[tuple[str, str]]   # (heading, body)


# --------------------------------------------------------------------------
# reading files
# --------------------------------------------------------------------------
def _read_pdf(path: Path) -> str:
    """Pull the text out of a PDF, page by page (a scanned PDF has no text to pull)."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n\n".join((page.extract_text() or "") for page in reader.pages)


def _read_docx(path: Path) -> str:
    """Pull the text out of a Word file.

    Word headings are turned into "## heading" lines and tables into "| a | b |" rows,
    so a Word file ends up looking like the markdown files and can be chunked the same way.
    """
    import docx

    document = docx.Document(str(path))
    lines: list[str] = []
    for para in document.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = (para.style.name or "").lower() if para.style is not None else ""
        if style.startswith("heading") or style == "title":
            lines.append(f"## {text}")
        else:
            lines.append(text)
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip().replace("\n", " ") for c in row.cells]
            lines.append("| " + " | ".join(cells) + " |")
    return "\n\n".join(lines)


def read_text(path: Path) -> str:
    """Read any supported file as text, choosing the right reader by file extension."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _read_pdf(path)
    if ext == ".docx":
        return _read_docx(path)
    return path.read_text(encoding="utf-8", errors="replace")


def _parse_front_matter(raw: str) -> tuple[dict, str]:
    """Separate a document's "label" from its text.

    Our sample documents start with a small block between --- lines holding details
    such as doc_id, title, category and updated date (called front matter). This returns
    those details as a dictionary, plus the remaining text.
    """
    match = FRONT_MATTER.match(raw)
    if not match:
        return {}, raw
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip().lower()] = value.strip().strip('"').strip("'")
    return meta, raw[match.end():]


def _split_sections(body: str, fallback_title: str) -> tuple[str, list[tuple[str, str]]]:
    """Split markdown-ish text into (heading, body) sections at #/##/### headings."""
    title = ""
    sections: list[tuple[str, str]] = []
    heading = "Overview"
    buffer: list[str] = []

    def flush() -> None:
        """Save the lines collected so far as one finished section."""
        text = "\n".join(buffer).strip()
        if text:
            sections.append((heading, text))

    for line in body.splitlines():
        match = HEADING.match(line)
        if match:
            level, text = len(match.group(1)), match.group(2).strip()
            if level == 1 and not title:
                title = text
                continue
            flush()
            heading, buffer = text, []
        else:
            buffer.append(line)
    flush()
    return title or fallback_title, sections


def _slug_id(path: Path) -> str:
    """Make an id for an uploaded file from its name, e.g. "hostel rules.pdf" -> "UP-HOSTEL-RULES"."""
    return "UP-" + re.sub(r"[^A-Za-z0-9]+", "-", path.stem).strip("-").upper()[:40]


def load_document(path: Path, category: str, origin: str) -> Document | None:
    """Turn one file into a Document: read it, read its label, split it into sections.

    Returns None when the file has no text.
    """
    raw = read_text(path)
    if not raw.strip():
        return None
    meta, body = _parse_front_matter(raw)
    fallback_title = path.stem.replace("-", " ").replace("_", " ").strip().title()
    title, sections = _split_sections(body, fallback_title)
    return Document(
        doc_id=meta.get("doc_id") or _slug_id(path),
        title=meta.get("title") or title,
        category=meta.get("category") or category,
        updated=meta.get("updated", ""),
        # A shipped document taken from a real institution's public pages says
        # "origin: official" in its front matter, so it is not labelled as sample data.
        origin="official" if origin == "sample" and meta.get("origin") == "official" else origin,
        path=path,
        sections=sections,
    )


def load_all_documents() -> list[Document]:
    """Load every document: the sample corpus (data/corpus) and the uploads (data/uploads).

    The folder a file sits in gives its category (syllabus, notices ...). A file that
    cannot be read is skipped with a message, so one bad upload never breaks the chatbot.
    """
    docs: list[Document] = []
    seen: set[str] = set()
    for base, origin in ((config.CORPUS_DIR, "sample"), (config.UPLOAD_DIR, "upload")):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in config.ALLOWED_UPLOAD_EXT:
                continue
            category = path.parent.name if path.parent.name in config.CATEGORIES else "policies"
            try:
                doc = load_document(path, category, origin)
            except Exception as exc:  # a broken upload must not take the whole index down
                print(f"[ingest] skipped {path.name}: {exc}")
                continue
            if doc is None or not doc.sections:
                continue
            if doc.doc_id in seen:      # keep ids unique so citations stay unambiguous
                doc.doc_id = f"{doc.doc_id}-{len(seen)}"
            seen.add(doc.doc_id)
            docs.append(doc)
    return docs


# --------------------------------------------------------------------------
# chunking
# --------------------------------------------------------------------------
def _windows(text: str) -> list[str]:
    """Split an over-long section into overlapping word windows.

    The overlap means a sentence that straddles a boundary is still whole in
    one of the two windows.
    """
    words = text.split()
    if len(words) <= config.MAX_CHUNK_WORDS:
        return [text]
    step = config.WINDOW_WORDS - config.WINDOW_OVERLAP
    out = []
    for start in range(0, len(words), step):
        piece = words[start:start + config.WINDOW_WORDS]
        if len(piece) < config.WINDOW_OVERLAP and out:
            break
        out.append(" ".join(piece))
    return out


def chunk_document(doc: Document) -> list[Chunk]:
    """CHUNKING: cut one document into passages.

    Rule: one section (the text under one heading) = one chunk. Only a section longer
    than MAX_CHUNK_WORDS (220 words) is cut further, into overlapping windows of 160
    words. Each chunk gets an id like "REG-01#3" (document id + running number).
    """
    chunks: list[Chunk] = []
    n = 0
    for heading, body in doc.sections:
        # Tables and lists keep their line breaks (they carry the structure);
        # only over-long prose sections are windowed.
        pieces = [body] if len(body.split()) <= config.MAX_CHUNK_WORDS else _windows(body)
        for piece in pieces:
            n += 1
            chunks.append(Chunk(
                chunk_id=f"{doc.doc_id}#{n}",
                doc_id=doc.doc_id,
                title=doc.title,
                category=doc.category,
                section=heading,
                text=piece.strip(),
                updated=doc.updated,
                origin=doc.origin,
            ))
    return chunks


def build_chunks() -> tuple[list[Document], list[Chunk]]:
    """The whole ingestion step in one call: load all documents, then chunk each one."""
    docs = load_all_documents()
    chunks = [chunk for doc in docs for chunk in chunk_document(doc)]
    return docs, chunks
