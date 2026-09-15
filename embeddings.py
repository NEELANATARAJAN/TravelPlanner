"""
embeddings.py
Thin wrapper around Voyage AI embeddings — Anthropic's recommended
embedding provider for RAG pipelines paired with Claude. Swap this file
alone if you'd rather use a different embedding model/provider; nothing
else in the pipeline needs to know which one is in use.
"""

import os
import voyageai

_client = voyageai.Client(api_key=os.environ.get("VOYAGE_API_KEY"))

EMBED_MODEL = "voyage-3.5"       # general-purpose embedding model
EMBED_DIMENSION = 1024           # must match the Pinecone index dimension


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed a batch of corpus chunks for upsert into Pinecone."""
    result = _client.embed(texts, model=EMBED_MODEL, input_type="document")
    return result.embeddings


def embed_query(text: str) -> list[float]:
    """Embed a single user query for similarity search against Pinecone."""
    result = _client.embed([text], model=EMBED_MODEL, input_type="query")
    return result.embeddings[0]
