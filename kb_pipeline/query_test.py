"""
query_test.py — sanity-check retrieval quality before wiring RAG into n8n.

Usage:
    python3 query_test.py "How do I reset my password?"
    python3 query_test.py "I was charged twice"
"""

import os
import sys

from fastembed import TextEmbedding
from qdrant_client import QdrantClient

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
COLLECTION = "support_kb"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"


def main(query: str):
    model = TextEmbedding(model_name=EMBEDDING_MODEL)
    client = QdrantClient(url=QDRANT_URL)

    vector = list(model.embed([query]))[0].tolist()
    response = client.query_points(collection_name=COLLECTION, query=vector, limit=5) 
    results = response.points

    print(f"\nTop results for: {query!r}\n")
    for r in results:
        print(f"score={r.score:.4f} | {r.payload['source_type']} | {r.payload['source_doc_id']}")
        print(f"  {r.payload['chunk_text'][:180].strip()}...")
        print()


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) or "How do I reset my password?"
    main(query)
