"""
embed_and_index.py — chunks the KB corpus + resolved tickets, embeds them
with a free local model (fastembed, no API key needed), and upserts into
Qdrant.

This is an OFFLINE script — run it by hand whenever your KB content changes.
It does NOT run inside n8n. It talks to Qdrant over the port your
docker-compose.yml already exposes (localhost:6333).

Usage:
    pip install fastembed qdrant-client --break-system-packages
    python3 embed_and_index.py
"""

import glob
import json
import os
import uuid

from chunking import chunk_markdown
from fastembed import TextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
COLLECTION = "support_kb"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"  # free, local, 384-dim, good quality/speed tradeoff

BASE_DIR = os.path.dirname(__file__)


def load_kb_articles() -> list[dict]:
    chunks = []
    for path in glob.glob(os.path.join(BASE_DIR, "sample_docs", "*.md")):
        doc_id = os.path.basename(path)
        with open(path, "r") as f:
            text = f.read()
        chunks.extend(chunk_markdown(text, doc_id, source_type="kb_article"))
    return chunks


def load_resolved_tickets() -> list[dict]:
    chunks = []
    path = os.path.join(BASE_DIR, "sample_resolved_tickets.jsonl")
    with open(path, "r") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            chunk_text = f"Q: {item['question']}\nA: {item['answer']}"
            chunks.append({
                "chunk_text": chunk_text,
                "source_doc_id": f"resolved_ticket_{i}",
                "source_type": "past_ticket",
                "rank": 0,
            })
    return chunks


def main():
    print("Loading corpus...")
    all_chunks = load_kb_articles() + load_resolved_tickets()
    print(f"Total chunks to embed: {len(all_chunks)}")

    print(f"Loading embedding model '{EMBEDDING_MODEL}' (first run downloads it, ~130MB)...")
    model = TextEmbedding(model_name=EMBEDDING_MODEL)

    texts = [c["chunk_text"] for c in all_chunks]
    print("Computing embeddings...")
    embeddings = list(model.embed(texts))

    dim = len(embeddings[0])
    print(f"Embedding dimension: {dim}")

    client = QdrantClient(url=QDRANT_URL)

    print(f"(Re)creating Qdrant collection '{COLLECTION}'...")
    client.recreate_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )

    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=emb.tolist(),
            payload=chunk,
        )
        for chunk, emb in zip(all_chunks, embeddings)
    ]

    client.upsert(collection_name=COLLECTION, points=points)
    print(f"Indexed {len(points)} chunks into Qdrant collection '{COLLECTION}'.")


if __name__ == "__main__":
    main()
