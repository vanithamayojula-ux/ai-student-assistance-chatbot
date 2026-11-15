"""Tests for the RAG pipeline. Run:  python -m pytest -q

They use the quote-only generator, so they need no language model.
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
    return get_engine()


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_corpus_covers_all_five_categories():
    docs, chunks = build_chunks()
    assert {d.category for d in docs if d.origin == "sample"} == set(config.CATEGORIES)
    assert len({c.chunk_id for c in chunks}) == len(chunks), "chunk ids must be unique"
    assert all(c.text.strip() and c.section for c in chunks)


def test_tokenizer_matches_singular_and_plural():
    assert tokenize("exams") == tokenize("exam")
    assert tokenize("What is the fee?") == ["fee"]          # stopwords removed


def test_blocks_keep_table_rows_and_abbreviations_whole():
    text = "The fee is Rs. 500 per course. Pay it online.\n\n| Grade | Points |\n|---|---|\n| A | 9 |"
    blocks = split_blocks(text)
    assert [b["kind"] for b in blocks] == ["prose", "table"]
    assert blocks[0]["units"] == ["The fee is Rs. 500 per course.", "Pay it online."]
    assert blocks[1]["units"] == ["| Grade | Points |", "| A | 9 |"]
    assert clean_unit("| A | 9 |", "| Grade | Points |") == "Grade: A, Points: 9."


def test_retrieval_finds_the_attendance_regulation(engine):
    hits, confidence = engine.retrieve("minimum attendance required to sit the end-term exam")
    assert hits and hits[0].chunk.doc_id == "REG-01"
    assert confidence >= engine.threshold


def test_answer_is_grounded_and_cited(engine):
    result = engine.answer("What is the minimum attendance required in each course?")
    assert not result["abstained"]
    assert "75%" in result["answer"]
    cited = [s for s in result["sources"] if s["cited"]]
    assert cited and cited[0]["doc_id"] == "REG-01"
    # the highlighted sentence really is in the cited passage
    marked = [u["text"] for s in cited for b in s["blocks"] for u in b["units"] if u["hit"]]
    assert marked and any("75%" in text for text in marked)


def test_out_of_scope_question_is_declined(engine):
    result = engine.answer("Who won the cricket world cup?")
    assert result["abstained"]
    assert not any(s["cited"] for s in result["sources"])


def test_greeting_does_not_search(engine):
    result = engine.answer("hello")
    assert not result["abstained"] and result["sources"] == []


def test_follow_up_uses_the_previous_question(engine):
    history = [{"role": "user", "content": "What is the fee for re-evaluation of an answer script?"}]
    assert "re-evaluation" in engine.contextualise("and the deadline?", history)
    assert engine.contextualise("How do I get a hostel room allotted?", history) == "How do I get a hostel room allotted?"


def test_category_filter_restricts_sources(engine):
    hits, _ = engine.retrieve("attendance", category="faqs")
    assert hits and all(h.chunk.category == "faqs" for h in hits)


def test_chat_endpoint_streams_meta_then_done(client):
    response = client.post("/api/chat", json={"question": "What is the minimum attendance required?"})
    assert response.status_code == 200
    import json

    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert events[0]["type"] == "meta" and events[-1]["type"] == "done"
    assert events[-1]["sources"]


def test_chat_rejects_empty_and_oversized_questions(client):
    assert client.post("/api/chat", json={"question": ""}).status_code == 422
    assert client.post("/api/chat", json={"question": "x" * 1001}).status_code == 422


def test_upload_rejects_wrong_type_and_bad_category(client):
    bad_type = client.post("/api/documents", data={"category": "notices"},
                           files={"file": ("evil.exe", b"MZ", "application/octet-stream")})
    assert bad_type.status_code == 400
    bad_category = client.post("/api/documents", data={"category": "../etc"},
                               files={"file": ("a.txt", b"hello", "text/plain")})
    assert bad_category.status_code == 400


def test_upload_then_ask_then_delete(client):
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
    assert client.delete("/api/documents/REG-01").status_code == 403
