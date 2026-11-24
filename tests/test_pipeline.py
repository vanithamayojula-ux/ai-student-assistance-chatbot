"""Tests for the RAG pipeline. Run:  python -m pytest -q

They use the quote-only generator, and a simulated Gemini API, so they need no
language model, API key or network.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import config
from app.ingest import build_chunks
from app.main import app
from app.pipeline import get_engine
from app.textutil import clean_unit, split_blocks, tokenize


@pytest.fixture(scope="module")
def engine():
    """One shared Engine for all tests in this file (building it is slow, so it is built once)."""
    return get_engine()


@pytest.fixture(scope="module")
def client():
    """A fake browser that calls the API in memory, without starting a real server."""
    return TestClient(app)


def test_corpus_covers_all_five_categories():
    """Ingestion: all five document categories load, and every chunk has a unique id and some text."""
    docs, chunks = build_chunks()
    assert {d.category for d in docs if d.origin == "sample"} == set(config.CATEGORIES)
    assert len({c.chunk_id for c in chunks}) == len(chunks), "chunk ids must be unique"
    assert all(c.text.strip() and c.section for c in chunks)


def test_tokenizer_matches_singular_and_plural():
    """Tokenizer: "exams" and "exam" become the same word, and filler words are removed."""
    assert tokenize("exams") == tokenize("exam")
    assert tokenize("What is the fee?") == ["fee"]          # stopwords removed


def test_blocks_keep_table_rows_and_abbreviations_whole():
    """Text splitting: "Rs." does not end a sentence, and a table row stays in one piece."""
    text = "The fee is Rs. 500 per course. Pay it online.\n\n| Grade | Points |\n|---|---|\n| A | 9 |"
    blocks = split_blocks(text)
    assert [b["kind"] for b in blocks] == ["prose", "table"]
    assert blocks[0]["units"] == ["The fee is Rs. 500 per course.", "Pay it online."]
    assert blocks[1]["units"] == ["| Grade | Points |", "| A | 9 |"]
    assert clean_unit("| A | 9 |", "| Grade | Points |") == "Grade: A, Points: 9."


def test_retrieval_finds_the_attendance_regulation(engine):
    """Retrieval: an attendance question finds the attendance regulation first, with enough confidence."""
    hits, confidence = engine.retrieve("minimum attendance required to sit the end-term exam")
    assert hits and hits[0].chunk.doc_id == "REG-01"
    assert confidence >= engine.threshold


def test_answer_is_grounded_and_cited(engine):
    """The answer contains the right fact (75%), cites the right document and highlights the sentence."""
    result = engine.answer("What is the minimum attendance required in each course?")
    assert not result["abstained"]
    assert "75%" in result["answer"]
    cited = [s for s in result["sources"] if s["cited"]]
    assert cited and cited[0]["doc_id"] == "REG-01"
    # the highlighted sentence really is in the cited passage
    marked = [u["text"] for s in cited for b in s["blocks"] for u in b["units"] if u["hit"]]
    assert marked and any("75%" in text for text in marked)


def test_out_of_scope_question_is_declined(engine):
    """A question the documents do not cover is declined instead of guessed."""
    result = engine.answer("Who won the cricket world cup?")
    assert result["abstained"]
    assert not any(s["cited"] for s in result["sources"])


def test_greeting_does_not_search(engine):
    """"hello" gets a greeting back and no document search is made."""
    result = engine.answer("hello")
    assert not result["abstained"] and result["sources"] == []


def test_follow_up_uses_the_previous_question(engine):
    """A short follow-up is joined with the previous question; a complete question is left alone."""
    history = [{"role": "user", "content": "What is the fee for re-evaluation of an answer script?"}]
    assert "re-evaluation" in engine.contextualise("and the deadline?", history)
    assert engine.contextualise("How do I get a hostel room allotted?", history) == "How do I get a hostel room allotted?"


def test_category_filter_restricts_sources(engine):
    """With a category filter, every result comes from that category only."""
    hits, _ = engine.retrieve("attendance", category="faqs")
    assert hits and all(h.chunk.category == "faqs" for h in hits)


def test_chat_endpoint_streams_meta_then_done(client):
    """The chat API streams events: first "meta", last "done" with sources."""
    response = client.post("/api/chat", json={"question": "What is the minimum attendance required?"})
    assert response.status_code == 200
    import json

    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert events[0]["type"] == "meta" and events[-1]["type"] == "done"
    assert events[-1]["sources"]


def test_chat_rejects_empty_and_oversized_questions(client):
    """Input validation: an empty question and a 1001-character question are both rejected."""
    assert client.post("/api/chat", json={"question": ""}).status_code == 422
    assert client.post("/api/chat", json={"question": "x" * 1001}).status_code == 422


def test_upload_rejects_wrong_type_and_bad_category(client):
    """Upload validation: an .exe file and an invalid category are both refused."""
    bad_type = client.post("/api/documents", data={"category": "notices"},
                           files={"file": ("evil.exe", b"MZ", "application/octet-stream")})
    assert bad_type.status_code == 400
    bad_category = client.post("/api/documents", data={"category": "../etc"},
                               files={"file": ("a.txt", b"hello", "text/plain")})
    assert bad_category.status_code == 400


def test_upload_then_ask_then_delete(client):
    """Full cycle: upload a document, get an answer from it, delete it again."""
    body = (b"# Robotics Club Notice\n\n## Membership\n\n"
            b"The Robotics Club membership fee is Rs. 444 per year and the club meets in Room Z-909 every Friday.\n")
    # a path in the file name must not escape the uploads folder
    created = client.post("/api/documents", data={"category": "notices"},
                          files={"file": ("../../robotics club notice.md", body, "text/markdown")})
    assert created.status_code == 200, created.text
    doc_id = created.json()["doc_id"]
    try:
        stored = list((config.UPLOAD_DIR / "notices").glob("*robotics*"))
        assert len(stored) == 1 and stored[0].parent == config.UPLOAD_DIR / "notices"
        result = get_engine().answer("What is the Robotics Club membership fee?")
        assert not result["abstained"] and "444" in result["answer"]
    finally:
        assert client.delete(f"/api/documents/{doc_id}").status_code == 200
    assert not list((config.UPLOAD_DIR / "notices").glob("*robotics*"))


def test_sample_documents_cannot_be_deleted(client):
    """The sample documents shipped with the project are protected from deletion."""
    assert client.delete("/api/documents/REG-01").status_code == 403


# --- Gemini generator, against a simulated API (no key or network needed) -----------------
def _fake_gemini(monkeypatch, handler):
    """Replace the real Gemini API with a pretend one, so tests need no key and no internet."""
    import httpx

    from app import generate

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(generate, "_http_client",
                        lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    generate.available_generators(force=True)      # availability is cached for 30 s


def _sse(*events) -> bytes:
    """Build a pretend streamed reply in the format the Gemini API uses (server-sent events)."""
    import json

    lines = []
    for event in events:
        lines.append(f"event: {event['event_type']}\ndata: {json.dumps(event)}\n\n")
    return ("".join(lines) + "event: done\ndata: [DONE]\n\n").encode("utf-8")


def test_gemini_answer_is_streamed_and_cited(engine, monkeypatch):
    """A Gemini answer arrives in pieces, is joined correctly and keeps its citation."""
    import httpx
    import json

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        """The pretend Gemini server: note what was sent, then reply with a streamed answer."""
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-goog-api-key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=_sse(
            {"event_type": "interaction.created"},
            {"event_type": "step.delta", "index": 0, "delta": {"type": "thought_summary", "content": {"text": "thinking"}}},
            {"event_type": "step.delta", "index": 1, "delta": {"type": "text", "text": "You need at least 75% "}},
            {"event_type": "step.delta", "index": 1, "delta": {"type": "text", "text": "attendance in each course. [1]"}},
            {"event_type": "interaction.completed", "interaction": {"status": "completed"}},
        ))

    _fake_gemini(monkeypatch, handler)
    result = engine.answer("What is the minimum attendance required in each course?", generator="gemini")
    assert result["generator"] == "gemini" and not result["abstained"]
    assert result["answer"] == "You need at least 75% attendance in each course. [1]"
    assert any(source["cited"] for source in result["sources"])
    assert seen["key"] == "test-key" and "/interactions" in seen["url"]
    body = seen["body"]
    assert body["stream"] is True and body["model"] == config.GEMINI_MODEL
    assert "Passages:" in body["input"] and "NO_ANSWER" in body["system_instruction"]


def test_gemini_no_answer_becomes_a_decline(engine, monkeypatch):
    """When the model replies NO_ANSWER, the student sees a polite decline."""
    import httpx

    _fake_gemini(monkeypatch, lambda request: httpx.Response(200, content=_sse(
        {"event_type": "step.delta", "index": 0, "delta": {"type": "text", "text": "NO_ANSWER"}})))
    result = engine.answer("What is the minimum attendance required in each course?", generator="gemini")
    assert result["abstained"]


def test_gemini_failure_falls_back_to_quoting(engine, monkeypatch):
    """When the Gemini API fails, the chatbot still answers by quoting the documents."""
    import httpx

    _fake_gemini(monkeypatch, lambda request: httpx.Response(
        403, json={"error": {"code": 403, "message": "API key not valid."}}))
    result = engine.answer("What is the minimum attendance required in each course?", generator="gemini")
    assert result["generator"] == "extractive" and "75%" in result["answer"]


def test_gemini_is_listed_and_needs_a_key(monkeypatch):
    """Gemini is shown as "not ready" without an API key and "ready" with one."""
    from app.generate import available_generators

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    listed = {g["id"]: g for g in available_generators(force=True)}
    assert "ollama" not in listed and listed["gemini"]["ready"] is False
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    assert {g["id"]: g for g in available_generators(force=True)}["gemini"]["ready"] is True


# --- Hindi-English questions and reranking --------------------------------------------------
def test_hinglish_is_rewritten_and_english_is_left_alone():
    """A Hindi-English question is rewritten to English; an English one is not touched."""
    from app.hinglish import to_search_english

    assert to_search_english("What is the minimum attendance required?") == "What is the minimum attendance required?"
    rewritten = to_search_english("hostel ka gate kitne baje band hota hai").lower()
    assert "hostel" in rewritten and "gate" in rewritten and "close" in rewritten
    assert " ka " not in f" {rewritten} " and "hai" not in rewritten.split()


def test_hinglish_question_finds_the_right_document(engine):
    """A Hindi-English hostel question still finds the hostel document."""
    hits = engine.index.search("hostel ka gate raat ko kitne baje band hota hai", k=3)
    assert any("hostel" in hit.chunk.title.lower() for hit in hits)


def test_reranker_reorders_when_asked(engine):
    """The reranker, when requested, returns passages sorted by its own score."""
    index = engine.index
    assert index.best_method == "hybrid"          # off by default: slower, and answers were no better
    if not index.can_rerank:
        pytest.skip("reranker model not available: " + index.reranker.error)
    hits = index.search("What is the minimum attendance required in each course?", k=4, method="rerank")
    assert hits[0].rerank is not None and hits[0].chunk.doc_id == "REG-01"
    assert [h.rerank for h in hits] == sorted((h.rerank for h in hits), reverse=True)


def test_corpus_changes_need_no_login(client):
    """Uploading and deleting work without a login; deleting an unknown id gives 404."""
    upload = {"file": ("open-note.txt", b"# Open note\n\nThe reading room opens at 9 am on Sundays.", "text/plain")}
    added = client.post("/api/documents", data={"category": "notices"}, files=upload)
    assert added.status_code == 200
    assert client.delete(f"/api/documents/{added.json()['doc_id']}").status_code == 200
    assert client.delete("/api/documents/anything").status_code == 404


def test_feedback_is_rate_limited(client, tmp_path, monkeypatch):
    """Rate limit: with a limit of 2 per minute, the third request gets error 429."""
    monkeypatch.setattr(config, "FEEDBACK_LOG", tmp_path / "feedback.jsonl")
    saved = config.FEEDBACK_PER_MINUTE
    config.FEEDBACK_PER_MINUTE = 2
    visitor = TestClient(app, headers={"X-Forwarded-For": "198.51.100.7"})
    body = {"question": "q", "answer": "a", "helpful": True}
    try:
        codes = [visitor.post("/api/feedback", json=body).status_code for _ in range(3)]
    finally:
        config.FEEDBACK_PER_MINUTE = saved
    assert codes[:2] == [200, 200] and codes[2] == 429


def test_security_headers_and_hidden_api_docs(client):
    """Every reply carries the security headers, and the API docs page is hidden by default."""
    response = client.get("/api/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["Cache-Control"] == "no-store"
    assert client.get("/api/openapi.json").status_code == 404     # API_DOCS is off by default
