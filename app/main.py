"""HTTP API and static frontend.

Run:  python -m uvicorn app.main:app --port 8000      then open http://127.0.0.1:8000
"""
from __future__ import annotations

import json
import logging
import re
import time
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, evaluate
from .generate import available_generators
from .pipeline import get_engine
from .security import HEADERS, limiter

log = logging.getLogger("app")

@asynccontextmanager
async def lifespan(_: FastAPI):
    get_engine()     # build the index before the first request, not during it
    yield


app = FastAPI(title="AI Student Assistance Chatbot", docs_url="/api/docs" if config.API_DOCS else None,
              redoc_url=None, openapi_url="/api/openapi.json" if config.API_DOCS else None, lifespan=lifespan)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for name, value in HEADERS.items():
        response.headers.setdefault(name, value)
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[Turn] = Field(default_factory=list, max_length=20)
    generator: Literal["extractive", "local", "gemini", "claude"] = "extractive"
    category: Literal["syllabus", "regulations", "notices", "faqs", "policies"] | None = None


class Feedback(BaseModel):
    question: str = Field(max_length=1000)
    answer: str = Field(max_length=6000)
    helpful: bool
    generator: str = Field(default="", max_length=40)


@app.get("/api/health")
def health() -> dict:
    engine = get_engine()
    index = engine.index
    return {
        "university": config.UNIVERSITY_NAME,
        "documents": len(engine.documents),
        "passages": len(index.chunks),
        "retrievers": index.methods,
        "answers_with": index.best_method,
        "embedding_model": config.EMBED_MODEL if index.has_dense else None,
        "embedding_error": "" if index.has_dense else "Embedding model unavailable; using keyword search.",
        "threshold": engine.threshold,
        "generators": available_generators(),
        "categories": [{"id": c, "label": config.CATEGORY_LABELS[c]} for c in config.CATEGORIES],
        "sample_corpus": any(d.origin == "sample" for d in engine.documents),
    }


@app.post("/api/chat")
def chat(request: ChatRequest, http: Request) -> StreamingResponse:
    limiter.check(http, "chat", config.CHAT_PER_MINUTE)
    engine = get_engine()
    history = [turn.model_dump() for turn in request.history]

    def events():
        try:
            for event in engine.answer_stream(request.question, history=history,
                                              generator=request.generator, category=request.category):
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except Exception:  # never leave the browser waiting on a dead stream
            log.exception("chat failed")
            yield json.dumps({"type": "error", "message": "The server hit an error while answering. Try again."}) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.get("/api/documents")
def documents() -> dict:
    engine = get_engine()
    passages = Counter(chunk.doc_id for chunk in engine.index.chunks)
    return {"documents": [
        {"doc_id": d.doc_id, "title": d.title, "category": d.category, "updated": d.updated,
         "origin": d.origin, "sections": len(d.sections), "passages": passages[d.doc_id],
         "file": d.path.name}
        for d in engine.documents
    ]}


@app.get("/api/documents/{doc_id}")
def document(doc_id: str) -> dict:
    from .textutil import split_blocks

    for d in get_engine().documents:
        if d.doc_id == doc_id:
            return {
                "doc_id": d.doc_id, "title": d.title, "category": d.category, "updated": d.updated,
                "origin": d.origin, "file": d.path.name,
                "sections": [
                    {"heading": heading,
                     "blocks": [{"kind": b["kind"], "units": [{"text": u, "hit": False} for u in b["units"]]}
                                for b in split_blocks(body)]}
                    for heading, body in d.sections
                ],
            }
    raise HTTPException(404, "No document with that id.")


def _safe_name(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(name).stem).strip("-.")[:80] or "document"
    return stem + Path(name).suffix.lower()


@app.post("/api/documents")
async def upload(http: Request, file: UploadFile = File(...), category: str = Form(...)) -> dict:
    limiter.check(http, "write", config.WRITES_PER_MINUTE)
    if category not in config.CATEGORIES:
        raise HTTPException(400, "Choose one of the five document categories.")
    name = _safe_name(file.filename or "document.txt")
    if Path(name).suffix not in config.ALLOWED_UPLOAD_EXT:
        raise HTTPException(400, "Upload a .pdf, .docx, .md or .txt file.")
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, "The file is larger than 10 MB.")
    if not data.strip():
        raise HTTPException(400, "The file is empty.")

    folder = config.UPLOAD_DIR / category
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / name
    target.write_bytes(data)

    engine = get_engine()
    before = {d.path for d in engine.documents}
    engine.rebuild()
    added = [d for d in engine.documents if d.path == target]
    if not added:
        target.unlink(missing_ok=True)
        engine.rebuild()
        raise HTTPException(422, "No text could be read from this file. Scanned PDFs need OCR first.")
    doc = added[0]
    return {"doc_id": doc.doc_id, "title": doc.title, "sections": len(doc.sections),
            "replaced": target in before}


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str, http: Request) -> dict:
    limiter.check(http, "write", config.WRITES_PER_MINUTE)
    engine = get_engine()
    for d in engine.documents:
        if d.doc_id == doc_id:
            if d.origin != "upload":
                raise HTTPException(403, "Sample documents are part of the project. Remove them from data/corpus by hand.")
            if config.UPLOAD_DIR.resolve() not in d.path.resolve().parents:
                raise HTTPException(403, "That file is outside the uploads folder.")
            d.path.unlink(missing_ok=True)
            engine.rebuild()
            return {"removed": doc_id}
    raise HTTPException(404, "No document with that id.")


@app.get("/api/eval/results")
def eval_results() -> dict:
    if not config.EVAL_RESULTS.exists():
        return {"available": False}
    return {"available": True, **json.loads(config.EVAL_RESULTS.read_text(encoding="utf-8"))}


@app.post("/api/eval/run")
def eval_run(http: Request) -> dict:
    """Re-run retrieval, abstention and extractive-answer evaluation (a few seconds)."""
    limiter.check(http, "write", config.WRITES_PER_MINUTE)
    if not config.EVAL_QUESTIONS.exists():
        raise HTTPException(404, "data/eval/questions.jsonl is missing.")
    results = evaluate.run(["extractive"], engine=get_engine())
    return {"available": True, **results}


@app.post("/api/feedback")
def feedback(item: Feedback, http: Request) -> dict:
    limiter.check(http, "feedback", config.FEEDBACK_PER_MINUTE)
    record = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **item.model_dump()}
    with config.FEEDBACK_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"saved": True}


@app.get("/")
def home() -> FileResponse:
    return FileResponse(config.WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})


app.mount("/", StaticFiles(directory=config.WEB_DIR), name="web")
