"""
pinecone_store.py
Thin wrapper around a Pinecone index: create-if-missing, upsert chunks
(with embeddings), and similarity-query. Chunk metadata (destination,
topic, text, source_url) is stored alongside each vector so query results
come back with everything the retriever agent needs — no second lookup.
"""

import hashlib
import os

from pinecone import Pinecone, ServerlessSpec

from src.travelai.rag.embeddings import EMBED_DIMENSION, embed_documents, embed_query

INDEX_NAME = os.environ.get("PINECONE_INDEX", "travel-guides")

_pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])


def _ensure_index():
    if INDEX_NAME not in [idx["name"] for idx in _pc.list_indexes()]:
        _pc.create_index(
            name=INDEX_NAME,
            dimension=EMBED_DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
    return _pc.Index(INDEX_NAME)


_index = _ensure_index()


def _chunk_id(chunk: dict) -> str:
    """Stable, deterministic ID so re-ingesting the same chunk upserts
    (overwrites) rather than duplicates it."""
    key = f"{chunk['destination']}|{chunk['topic']}|{chunk['text'][:100]}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def upsert_chunks(chunks: list[dict], batch_size: int = 96):
    """Embed and upsert a list of corpus chunks into Pinecone."""
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        vectors = embed_documents([c["text"] for c in batch])

        records = [
            {
                "id": _chunk_id(chunk),
                "values": vector,
                "metadata": {
                    "destination": chunk["destination"],
                    "topic": chunk["topic"],
                    "text": chunk["text"],
                    "source_url": chunk.get("source_url", ""),
                },
            }
            for chunk, vector in zip(batch, vectors)
        ]
        _index.upsert(vectors=records)


def query(text: str, destination: str | None = None, top_k: int = 4) -> list[dict]:
    """Semantic search against the Pinecone index, optionally filtered
    to a specific destination via metadata filtering."""
    vector = embed_query(text)

    filter_dict = {"destination": {"$eq": destination}} if destination else None

    results = _index.query(
        vector=vector,
        top_k=top_k,
        include_metadata=True,
        filter=filter_dict,
    )

    return [
        {
            "score": match["score"],
            "destination": match["metadata"]["destination"],
            "topic": match["metadata"]["topic"],
            "text": match["metadata"]["text"],
            "source_url": match["metadata"].get("source_url", ""),
        }
        for match in results["matches"]
    ]


def index_stats() -> dict:
    return _index.describe_index_stats()
