import os
import sys
from pathlib import Path
from typing import Optional

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import chromadb
from app.config import DOCS_DIR, CHROMA_DIR
from app.rag import get_embedding_function, split_markdown_into_chunks

def ingest_documents(docs_dir: Optional[str] = None, chroma_dir: Optional[str] = None):
    docs_path = Path(docs_dir or DOCS_DIR)
    chroma_path = Path(chroma_dir or CHROMA_DIR)

    print(f"=== Document Ingestion Pipeline ===")
    print(f"Docs Directory: {docs_path}")
    print(f"Chroma DB Path: {chroma_path}")

    if not docs_path.exists():
        print(f"Error: Documentation directory '{docs_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    md_files = sorted(list(docs_path.glob("*.md")))
    if not md_files:
        print(f"Error: No markdown (.md) files found in '{docs_path}'.", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(md_files)} documentation files to ingest:")
    for f in md_files:
        print(f"  - {f.name} ({f.stat().st_size} bytes)")

    # Prepare ChromaDB client
    os.makedirs(chroma_path, exist_ok=True)
    client = chromadb.PersistentClient(path=str(chroma_path))
    ef = get_embedding_function()

    collection_name = "customer_support_docs"
    # Idempotent re-ingestion: delete collection if exists, then re-create
    try:
        client.delete_collection(name=collection_name)
        print(f"Deleted existing '{collection_name}' collection for clean re-ingest.")
    except Exception:
        pass

    collection = client.create_collection(
        name=collection_name,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"}
    )

    all_chunks = []
    for f in md_files:
        with open(f, "r", encoding="utf-8") as file:
            content = file.read()
        chunks = split_markdown_into_chunks(content, filename=f.name)
        all_chunks.extend(chunks)

    print(f"\nGenerated {len(all_chunks)} semantic chunks across {len(md_files)} documents.")

    # Batch insert into ChromaDB
    chunk_ids = [c["id"] for c in all_chunks]
    chunk_texts = [c["text"] for c in all_chunks]
    chunk_metas = [c["metadata"] for c in all_chunks]

    # Ingest in batches of 50
    batch_size = 50
    for i in range(0, len(all_chunks), batch_size):
        end = min(i + batch_size, len(all_chunks))
        collection.add(
            ids=chunk_ids[i:end],
            documents=chunk_texts[i:end],
            metadatas=chunk_metas[i:end]
        )
        print(f"  Ingested chunks {i+1} to {end}...")

    print(f"\n[SUCCESS] Successfully ingested {len(all_chunks)} chunks into ChromaDB at {chroma_path}.")
    print(f"Verified collection count: {collection.count()}")

if __name__ == "__main__":
    d_dir = sys.argv[1] if len(sys.argv) > 1 else None
    c_dir = sys.argv[2] if len(sys.argv) > 2 else None
    ingest_documents(d_dir, c_dir)
