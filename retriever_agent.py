"""
retriever_agent.py
RAG retriever agent, now backed by Pinecone (semantic/vector search)
instead of local keyword scoring. The corpus itself lives in Pinecone,
populated and kept fresh by ingest.py / scheduler.py pulling from
Wikivoyage — this file only queries it.

Public interface (the `keyword_search_corpus`-style tool contract) is
kept close to the earlier vectorless version on purpose: the orchestrator
never needs to know retrieval moved from local JSON + keyword matching to
Pinecone + embeddings.
"""

from agent import Agent
import pinecone_store

_TOOLS = [
    {
        "name": "semantic_search_corpus",
        "description": "Semantically search the travel guide corpus (sourced from Wikivoyage, stored in Pinecone). Returns the most relevant chunks with similarity scores and source URLs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "destination": {"type": "string", "description": "Optional destination filter, e.g. 'Kyoto'"},
                "k": {"type": "integer", "description": "Number of results", "default": 4},
            },
            "required": ["query"],
        },
    }
]

_SYSTEM_PROMPT = """You are a retrieval agent for a travel-planning system.
Given a natural-language information need, call semantic_search_corpus
(reformulating the query if needed for better semantic matches) and then
return ONLY the most relevant retrieved chunks as a concise JSON list,
including each chunk's source_url. Do not add commentary, do not invent
facts not present in the retrieved chunks. If results look weak (low
scores or few matches), say so rather than padding with your own
knowledge."""


class RetrieverAgent(Agent):
    name = "retriever"
    system_prompt = _SYSTEM_PROMPT
    tools = _TOOLS

    def run_tool(self, name: str, tool_input: dict):
        if name != "semantic_search_corpus":
            raise ValueError(f"Unknown tool {name}")

        return pinecone_store.query(
            text=tool_input["query"],
            destination=tool_input.get("destination"),
            top_k=tool_input.get("k", 4),
        )
