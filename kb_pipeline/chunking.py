"""
chunking.py — splits markdown documents into retrievable chunks.

Lighter-weight alternative to the langchain_text_splitters approach in the
roadmap: no extra heavy dependency, same core idea — split on markdown
headers first (so each chunk stays topically coherent), then fall back to
fixed-size splitting with overlap for any section that's still too long.
"""

import re

CHUNK_SIZE = 1600   # ~400 tokens
OVERLAP = 240       # ~15%


def chunk_markdown(text: str, doc_id: str, source_type: str = "kb_article",
                    chunk_size: int = CHUNK_SIZE, overlap: int = OVERLAP) -> list[dict]:
    """Split markdown text into chunks, preferring header boundaries."""
    sections = re.split(r"\n(?=#{1,3} )", text)
    chunks = []
    rank = 0

    for section in sections:
        section = section.strip()
        if not section:
            continue

        if len(section) <= chunk_size:
            chunks.append({
                "chunk_text": section,
                "source_doc_id": doc_id,
                "source_type": source_type,
                "rank": rank,
            })
            rank += 1
        else:
            start = 0
            while start < len(section):
                end = start + chunk_size
                chunk_text = section[start:end].strip()
                if chunk_text:
                    chunks.append({
                        "chunk_text": chunk_text,
                        "source_doc_id": doc_id,
                        "source_type": source_type,
                        "rank": rank,
                    })
                    rank += 1
                start = end - overlap

    return chunks
