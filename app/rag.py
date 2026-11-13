import os
import re
import glob
from pathlib import Path
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.api.types import EmbeddingFunction, Documents, Embeddings

from app.config import (
    CHROMA_DIR,
    DOCS_DIR,
    RAG_SIMILARITY_THRESHOLD,
    RAG_TOP_K,
    EMBEDDING_PROVIDER,
    GEMINI_API_KEY,
    OPENAI_API_KEY,
)

class LocalSentenceTransformerEF(EmbeddingFunction):
    """
    Offline-capable embedding function using local cached SentenceTransformer model.
    """
    def __init__(self, model_name_or_path: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer
        # Check if cached locally in huggingface hub
        hf_cache_snaps = os.path.expanduser(
            "~/.cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2/snapshots"
        )
        if os.path.exists(hf_cache_snaps):
            snaps = os.listdir(hf_cache_snaps)
            if snaps:
                model_name_or_path = os.path.join(hf_cache_snaps, snaps[0])

        self.model = SentenceTransformer(model_name_or_path)

    def name(self) -> str:
        return "LocalSentenceTransformerEF"

    def get_config(self) -> Dict[str, Any]:
        return {"model_name": "all-MiniLM-L6-v2"}

    def __call__(self, input: Documents) -> Embeddings:
        embeddings = self.model.encode(list(input), show_progress_bar=False, normalize_embeddings=True)
        return [emb.tolist() for emb in embeddings]


_embedding_func_instance = None

def get_embedding_function() -> EmbeddingFunction:
    """Returns singleton embedding function instance."""
    global _embedding_func_instance
    if _embedding_func_instance is not None:
        return _embedding_func_instance

    _embedding_func_instance = LocalSentenceTransformerEF()
    return _embedding_func_instance

def get_vector_store(chroma_dir: Optional[str] = None) -> chromadb.Collection:
    """Returns or creates the ChromaDB collection for customer support docs."""
    directory = chroma_dir or CHROMA_DIR
    os.makedirs(directory, exist_ok=True)
    client = chromadb.PersistentClient(path=directory)
    ef = get_embedding_function()
    collection = client.get_or_create_collection(
        name="customer_support_docs",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"}
    )
    return collection

def split_markdown_into_chunks(
    markdown_text: str,
    filename: str,
    max_chunk_size: int = 600,
    overlap: int = 100
) -> List[Dict[str, Any]]:
    """
    Splits markdown document into semantic sections based on headers,
    preserving section titles and creating overlapping chunks for long sections.
    """
    chunks = []
    lines = markdown_text.splitlines()
    
    current_doc_title = Path(filename).stem.replace("_", " ").title()
    current_section = "General"
    current_lines = []

    def flush_section(title: str, text_lines: List[str]):
        text = "\n".join(text_lines).strip()
        if not text:
            return
        
        # If section is small enough, keep as single chunk
        if len(text) <= max_chunk_size:
            chunk_id = f"{filename}::{title}::{len(chunks)}"
            chunks.append({
                "id": chunk_id,
                "text": f"[{current_doc_title} > {title}]\n{text}",
                "metadata": {
                    "source": filename,
                    "title": title,
                    "doc_title": current_doc_title
                }
            })
        else:
            # Split with overlap by sentences/paragraphs
            paragraphs = text.split("\n\n")
            curr_chunk = ""
            for p in paragraphs:
                p = p.strip()
                if not p:
                    continue
                if len(curr_chunk) + len(p) + 2 <= max_chunk_size:
                    curr_chunk = f"{curr_chunk}\n\n{p}" if curr_chunk else p
                else:
                    if curr_chunk:
                        chunk_id = f"{filename}::{title}::{len(chunks)}"
                        chunks.append({
                            "id": chunk_id,
                            "text": f"[{current_doc_title} > {title}]\n{curr_chunk.strip()}",
                            "metadata": {
                                "source": filename,
                                "title": title,
                                "doc_title": current_doc_title
                            }
                        })
                    curr_chunk = p
            if curr_chunk:
                chunk_id = f"{filename}::{title}::{len(chunks)}"
                chunks.append({
                    "id": chunk_id,
                    "text": f"[{current_doc_title} > {title}]\n{curr_chunk.strip()}",
                    "metadata": {
                        "source": filename,
                        "title": title,
                        "doc_title": current_doc_title
                    }
                })

    for line in lines:
        if line.startswith("#"):
            # Header line encountered
            if current_lines:
                flush_section(current_section, current_lines)
                current_lines = []
            heading_text = line.lstrip("#").strip()
            current_section = heading_text if heading_text else current_section
        else:
            current_lines.append(line)

    if current_lines:
        flush_section(current_section, current_lines)

    return chunks

def search_docs(
    query: str,
    top_k: int = RAG_TOP_K,
    threshold: float = RAG_SIMILARITY_THRESHOLD,
    chroma_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Searches the documentation vector store for relevant information.
    Scores chunks by cosine similarity (1.0 - cosine_distance).
    If similarity falls below the threshold, gracefully reports not found.
    """
    if not query or not isinstance(query, str) or not query.strip():
        return {
            "success": False,
            "error_code": "EMPTY_QUERY",
            "message": "Query string cannot be empty."
        }
    
    clean_query = query.strip()
    collection = get_vector_store(chroma_dir)

    # Check if collection is empty
    if collection.count() == 0:
        return {
            "success": True,
            "found": False,
            "query": clean_query,
            "message": "The documentation index is currently empty. Please run ingestion.",
            "suggest_human": True,
            "sources": [],
            "chunks": []
        }

    try:
        results = collection.query(
            query_texts=[clean_query],
            n_results=top_k,
            include=["documents", "metadatas", "distances"]
        )
    except Exception as e:
        return {
            "success": False,
            "error_code": "RAG_SEARCH_ERROR",
            "message": f"Error executing vector search: {str(e)}"
        }

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    filtered_chunks = []
    sources = []

    for doc, meta, dist in zip(documents, metadatas, distances):
        # Chroma cosine distance ranges [0, 2], where 0 is identical
        # Cosine similarity = 1.0 - (dist / 2.0) or 1.0 - dist
        similarity = max(0.0, 1.0 - float(dist))
        
        if similarity >= threshold:
            src_file = meta.get("source", "unknown")
            sec_title = meta.get("title", "General")
            source_ref = f"{src_file} - {sec_title}"
            
            filtered_chunks.append({
                "content": doc,
                "source": src_file,
                "title": sec_title,
                "similarity_score": round(similarity, 4)
            })
            if source_ref not in [s["citation"] for s in sources]:
                sources.append({
                    "citation": source_ref,
                    "source": src_file,
                    "title": sec_title,
                    "score": round(similarity, 4)
                })

    if not filtered_chunks:
        return {
            "success": True,
            "found": False,
            "query": clean_query,
            "message": "I could not find sufficient information in our documentation addressing your question. Would you like me to connect you with a human customer support specialist?",
            "suggest_human": True,
            "sources": [],
            "chunks": []
        }

    formatted_citations = [f"[Source: {s['citation']}]" for s in sources]
    context_text = "\n\n---\n\n".join([c["content"] for c in filtered_chunks])

    return {
        "success": True,
        "found": True,
        "query": clean_query,
        "best_score": filtered_chunks[0]["similarity_score"],
        "results_count": len(filtered_chunks),
        "sources": sources,
        "formatted_sources": " ".join(formatted_citations),
        "chunks": filtered_chunks,
        "context": context_text
    }
