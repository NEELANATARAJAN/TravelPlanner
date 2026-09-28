"""
embeddings.py
Embedding backend, pluggable the same way agent.py's LLM backend is:

  - "voyage": Voyage AI (default) — Anthropic's recommended embedding
              provider for RAG pipelines paired with Claude.
  - "vllm":   a self-hosted embedding model served by vLLM's
              OpenAI-compatible /v1/embeddings endpoint (e.g. BAAI/bge-m3,
              intfloat/e5-mistral-7b-instruct) — for a fully self-hosted
              stack alongside the vLLM LLM backend.

Select with:
    export EMBED_BACKEND=voyage    # default
    export EMBED_BACKEND=vllm

For vllm, also set:
    export VLLM_EMBED_BASE_URL=http://localhost:8001/v1
    export VLLM_EMBED_MODEL=BAAI/bge-m3
    export EMBED_DIMENSION=1024    # must match the model + your Pinecone index

Everything downstream (pinecone_store.py, retriever_agent.py) only calls
embed_documents() / embed_query() — neither knows or cares which backend
produced the vectors.
"""

import os

EMBED_BACKEND = os.environ.get("EMBED_BACKEND", "voyage").lower()

# Dimension must match whatever Pinecone index you created. Voyage's
# voyage-3.5 defaults to 1024; override via env var for vllm-served models
# (e.g. bge-m3 is also 1024, e5-mistral-7b-instruct is 4096).
EMBED_DIMENSION = int(os.environ.get("EMBED_DIMENSION", "1024"))


def _voyage_client():
    import voyageai

    return voyageai.Client(api_key=os.environ.get("VOYAGE_API_KEY"))


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed a batch of corpus chunks for upsert into Pinecone."""
    if EMBED_BACKEND == "vllm":
        return _embed_vllm(texts)

    result = _voyage_client().embed(texts, model="voyage-3.5", input_type="document")
    return result.embeddings


def embed_query(text: str) -> list[float]:
    """Embed a single user query for similarity search against Pinecone."""
    if EMBED_BACKEND == "vllm":
        return _embed_vllm([text])[0]

    result = _voyage_client().embed([text], model="voyage-3.5", input_type="query")
    return result.embeddings[0]


def _embed_vllm(texts: list[str]) -> list[list[float]]:
    from openai import OpenAI

    base_url = os.environ.get("VLLM_EMBED_BASE_URL", "http://localhost:8001/v1")
    model = os.environ.get("VLLM_EMBED_MODEL")
    if not model:
        raise RuntimeError(
            "VLLM_EMBED_MODEL env var is required when EMBED_BACKEND=vllm "
            "(e.g. 'BAAI/bge-m3')"
        )

    client = OpenAI(base_url=base_url, api_key="not-needed")
    response = client.embeddings.create(model=model, input=texts)
    # response.data is returned in request order
    return [item.embedding for item in response.data]