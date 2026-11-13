import os
import pytest
from pathlib import Path
from app.rag import search_docs, get_vector_store
from scripts.ingest_docs import ingest_documents
from app.config import DOCS_DIR

def test_rag_known_question_returns_correct_source():
    """Verify that a known policy question retrieves the correct document source."""
    result = search_docs("What is the return and refund window?")
    assert result["success"] is True
    assert result["found"] is True
    assert result["results_count"] > 0
    assert result["best_score"] >= 0.45
    assert "return_and_refund_policy.md" in result["formatted_sources"]
    assert any("Refund Window" in s["title"] or "Eligibility" in s["title"] for s in result["sources"])

def test_rag_product_faq_source():
    """Verify product FAQ query retrieves smartphone documentation."""
    result = search_docs("What processor chip does the iPhone 16 have?")
    assert result["success"] is True
    assert result["found"] is True
    assert "product_faqs_smartphones.md" in result["formatted_sources"]
    assert "A18" in result["context"]

def test_rag_off_topic_question_triggers_not_available():
    """Verify that an off-topic query falls below threshold and triggers not-available response."""
    result = search_docs("How do I make chocolate ice cream with liquid nitrogen?")
    assert result["success"] is True
    assert result["found"] is False
    assert result["suggest_human"] is True
    assert "I could not find sufficient information" in result["message"]

def test_rag_reingestion_creates_no_duplicates(tmp_path):
    """Verify that running ingestion multiple times is idempotent with zero duplicates."""
    test_chroma = str(tmp_path / "chroma_idempotent")
    
    # First ingest
    ingest_documents(docs_dir=DOCS_DIR, chroma_dir=test_chroma)
    col = get_vector_store(chroma_dir=test_chroma)
    count1 = col.count()
    assert count1 > 0

    # Second ingest
    ingest_documents(docs_dir=DOCS_DIR, chroma_dir=test_chroma)
    col2 = get_vector_store(chroma_dir=test_chroma)
    count2 = col2.count()

    # Counts must be strictly identical
    assert count1 == count2
