"""
Tiny embedding microservice — wraps a free local embedding model behind a
simple HTTP endpoint so n8n (which can't run Python ML libraries directly)
can get a vector for an incoming ticket at request time.

POST /embed  { "text": "..." }  ->  { "embedding": [...], "dim": 384 }
GET  /health -> { "status": "ok" }
"""

from fastapi import FastAPI
from pydantic import BaseModel
from fastembed import TextEmbedding

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"

app = FastAPI()
model = TextEmbedding(model_name=EMBEDDING_MODEL)


class EmbedRequest(BaseModel):
    text: str


@app.post("/embed")
def embed(req: EmbedRequest):
    vector = list(model.embed([req.text]))[0]
    return {"embedding": vector.tolist(), "dim": len(vector)}


@app.get("/health")
def health():
    return {"status": "ok"}
