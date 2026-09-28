# AI Travel Planner — Wikivoyage → Pinecone RAG

A multi-agent trip-planner that combines RAG (wikivoyage content, embedded and stored in pinecone VDB). KB is loaded periodically. Tool using LLM orchestrator (Claude), and live weather data to produce grounded, day-by-day itineraries.
This version replaces the local JSON keyword-search corpus with a real
vector database: **Wikivoyage articles are fetched, chunked, embedded,
and upserted into Pinecone**, kept fresh by a periodic ingest job. The
retriever agent then does semantic (embedding-based) search instead of
keyword overlap.

## Architecture

```
                     ┌──────────────────────────────────────┐
                     │   Periodic ingest (scheduler.py       │
                     │   or external cron), every few hours  │
                     └────────────────┬───────────────────────┘
                                      │
       Wikivoyage API ──► chunk into sections ──► embed (Voyage AI) ──► upsert
                                      │
                                      ▼
                          Pinecone index "travel-guides"


  User request
       │
       ▼
  ┌─────────────────────────┐
  │   Orchestrator Agent     │  decides what to ask each specialist,
  │   (orchestrator.py)      │  synthesizes the final itinerary
  └────────────┬──────────────┘
               │
     ┌─────────┴──────────┐
     ▼                     ▼
┌───────────────┐   ┌──────────────────┐
│ Retriever Agent │   │  Weather Agent    │
│ (RAG, Pinecone) │   │  (Open-Meteo)     │
│                 │   │                   │
│ grounded facts: │   │ live forecast, or │
│ sights, food,   │   │ climate normals   │
│ practical tips  │   │ if too far out    │
└───────────────┘   └──────────────────┘
       │                     │
       └──────────┬──────────┘
                   ▼
     Day-by-day itinerary: activities
     matched to weather, grounded in
     retrieved guide content, cited
     back to source_url
```

## Files

travel-planner-pinecone/
├── agent.py                 # Base class: shared Claude tool-use loop
├── orchestrator.py          # Top-level agent — delegates to the two specialists
├── retriever_agent.py       # RAG agent — semantic search against Pinecone
├── weather_agent.py         # Weather agent — Open-Meteo forecast + climate fallback
├── wikivoyage_loader.py     # Fetches + chunks Wikivoyage articles
├── embeddings.py            # Voyage AI embedding wrapper
├── pinecone_store.py        # Pinecone index create/upsert/query
├── ingest.py                # One-shot ingest pipeline (Wikivoyage → Pinecone)
├── scheduler.py             # Background periodic re-ingest (in-process alternative to cron)
├── main.py                  # CLI entry point
├── requirements.txt
└── README.md


| File | Role |
|---|---|
| `wikivoyage_loader.py` | Fetches a Wikivoyage article via the MediaWiki API, strips wiki markup, splits into `{destination, topic, text, source_url}` chunks |
| `embeddings.py` | Wraps Voyage AI embeddings (Anthropic's recommended embedding provider) |
| `pinecone_store.py` | Creates the Pinecone index if missing, upserts chunks, runs similarity queries with metadata filtering |
| `ingest.py` | One-shot pipeline: for each configured destination, fetch → chunk → embed → upsert |
| `scheduler.py` | Runs `ingest.py`'s pipeline on a fixed interval in a background thread |
| `retriever_agent.py` | RAG agent — same shape as before, but its tool now queries Pinecone semantically instead of local keyword matching |
| `orchestrator.py`, `agent.py`, `weather_agent.py`, `main.py` | Unchanged from the earlier multi-agent version — they only depend on `RetrieverAgent`'s public interface, not its internals |

## Why this swap was "free" architecturally

Because retrieval was already isolated behind `RetrieverAgent.run()` in
the earlier multi-agent design, going from local keyword search to
Pinecone + embeddings only touched `retriever_agent.py` (plus new
supporting files). `orchestrator.py`, `agent.py`, `weather_agent.py`, and
`main.py` are byte-for-byte the same as the local-corpus version.

## Setup

```bash
cd travel-planner-pinecone
pip install -r requirements.txt

export ANTHROPIC_API_KEY=your_anthropic_key
export VOYAGE_API_KEY=your_voyage_key       # https://www.voyageai.com
export PINECONE_API_KEY=your_pinecone_key   # https://www.pinecone.io
export PINECONE_INDEX=travel-guides         # optional, this is the default
```

## First run — populate the index

```bash
python ingest.py
```

This fetches every destination in `DESTINATIONS` (edit that list in
`ingest.py` to add your own cities), chunks each article's See/Do/Eat/
Drink/Sleep/Get in/Get around/Stay safe/Buy sections, embeds them, and
upserts into Pinecone. Re-running is safe — chunk IDs are deterministic
hashes of `destination|topic|text`, so re-ingesting the same content
overwrites rather than duplicates.

## Keep it fresh — periodic reload

**In-process (simplest for dev/small deployments):**
```bash
python scheduler.py
```
Runs forever, re-running the full ingest every 6 hours (`INTERVAL_SEC` in
`scheduler.py`). Errors on one destination don't abort the run or wipe
already-ingested data.

**Production-recommended: external cron**
```bash
# crontab entry, e.g. every 6 hours
0 */6 * * * cd /path/to/travel-planner-pinecone && /usr/bin/python3 ingest.py >> ingest.log 2>&1
```
This is generally preferable in production: it survives app restarts,
can be monitored/alerted on independently of your API process, and
doesn't tie ingest failures to app uptime.

## Run the planner

```bash
python main.py "Plan a 3-day trip to Kyoto, June 10-12, I like temples and food"
```

The orchestrator will consult the retriever agent for grounded destination facts and the weather agent for the trip's forecast, then produce a day-by-day plan with weather-appropriate activity choices.

---

## Self-hosted models via vLLM

Both the agent LLM and the embedding model can run on **vLLM** (self-hosted, OpenAI-compatible API) instead of Anthropic/Voyage — useful for offline dev, cost control, or data-residency requirements. Nothing in `orchestrator.py`, `retriever_agent.py`, `weather_agent.py`, or `pinecone_store.py` changes; only the backend selected in `agent.py` / `embeddings.py` does.

### Backend selection

| Component | Env var | Values |
|---|---|---|
| Agent LLM | `LLM_BACKEND` | `anthropic` (default) or `vllm` |
| Embeddings | `EMBED_BACKEND` | `voyage` (default) or `vllm` |

### Standing up vLLM locally

Requires an NVIDIA GPU + the NVIDIA Container Toolkit. The included `docker-compose.yml` starts an LLM server and (optionally) an embedding server:

```bash
export HUGGING_FACE_HUB_TOKEN=your_hf_token   # only needed for gated models like Llama
docker compose up -d llm-server               # LLM only
docker compose up -d llm-server embed-server  # LLM + embeddings, fully self-hosted
```

Then point the app at them:

```bash
export LLM_BACKEND=vllm
export VLLM_BASE_URL=http://localhost:8000/v1
export VLLM_MODEL=meta-llama/Llama-3.1-8B-Instruct

# only if also using embed-server:
export EMBED_BACKEND=vllm
export VLLM_EMBED_BASE_URL=http://localhost:8001/v1
export VLLM_EMBED_MODEL=BAAI/bge-m3
export EMBED_DIMENSION=1024   # must match the embedding model's output dim
```

```bash
pip install -r requirements.txt   # installs openai SDK, used for both vllm paths
python main.py "Plan a 3-day trip to Kyoto, June 10-12, I like temples and food"
```

### Model requirements for vLLM

- **Tool calling must be supported by both the model and vLLM's parser.** Start vLLM with `--enable-auto-tool-choice` and a matching `--tool-call-parser` (e.g. `llama3_json` for Llama 3.1/3.3, `hermes` for Qwen2.5/NousHermes, `mistral` for Mistral/Mixtral). Check vLLM's [tool calling docs](https://docs.vllm.ai/en/latest/features/tool_calling.html) for the current parser matching your model — this changes as vLLM adds support for more models.
- Models known to work well for agentic tool-use at time of writing: **Llama 3.1/3.3 Instruct**, **Qwen2.5-Instruct**, **Mistral/Mixtral Instruct**. Smaller/older instruction-tuned models without explicit tool-use training tend to produce malformed tool calls under multi-step agent loops like this one — test the specific model against your tool schemas before relying on it.
- For embeddings, any vLLM-served embedding model works (`--task=embed`), e.g. `BAAI/bge-m3` (1024-dim) or `intfloat/e5-mistral-7b-instruct` (4096-dim). **`EMBED_DIMENSION` must match your Pinecone index's dimension** — if you change embedding models after the index already has vectors in it, you'll need to recreate the index (dimensions can't be changed in place) and re-run `ingest.py`.

### Mixing backends

The two toggles are independent — e.g. Claude for reasoning + a self-hosted embedding model, or a self-hosted LLM + Voyage for embeddings, are both valid combinations depending on what you're trying to control cost or data-residency for.

---

## Design notes

- **Why Pinecone over local keyword search?** Semantic search handles paraphrase and fuzzy intent ("quiet places to relax" matching a chunk about "peaceful temple gardens") that exact keyword matching misses. The trade-off is added infra (embedding calls, a hosted index) versus a zero-dependency local JSON file — worth it once your corpus is large or your queries are more conceptual than literal.
- **Why Wikivoyage?** CC-BY-SA licensed, written as genuine travel-guide prose (not just structured POI data), and already covers thousands of destinations — a practical way to bootstrap a real corpus without scraping or commercial licensing. `source_url` is carried through every chunk specifically so results can be attributed.
- **Why is weather never delegated to RAG or the LLM's memory?** Weather is inherently time-sensitive; no static corpus or training data can answer "what's the forecast for next Tuesday" correctly. It's always a live tool call, with a climate-normals fallback for trips too far out to forecast (~16+ days).
- **Why separate agents instead of one flat tool list?** Isolation. The retriever agent owns *how* to search (keyword, semantic, hybrid — whatever) and the orchestrator only knows *that* it can ask for destination facts. This is what let the corpus backend change from local JSON to Pinecone without touching `orchestrator.py`, `agent.py`, or `weather_agent.py` at all.

---

## Extending this project

- **Add more destinations** — extend `DESTINATIONS` in `ingest.py`; for large lists, move it to a config file or database table.
- **Tune chunking** — `wikivoyage_loader.py`'s `max_chunk_chars` and `RELEVANT_SECTIONS` control granularity. Too coarse → irrelevant padding in results; too fine → missing context.
- **Hybrid search** — if pure semantic search misses exact-match needs (specific venue names, addresses), Pinecone supports sparse+dense hybrid indexes.
- **Add a Places/Maps agent** — follow the same pattern as `weather_agent.py`: new file, its own tools, one new `consult_places_agent` entry in `orchestrator.py`'s tool list.
- **Swap the embedding provider** — only `embeddings.py` needs to change; `pinecone_store.py` and `retriever_agent.py` don't care which provider produced the vectors, as long as `EMBED_DIMENSION` matches the index.
- **Parallelize sub-agent calls** — if Claude requests both the retriever and weather agent in the same turn, `orchestrator.py` can run them concurrently (e.g. `asyncio.gather`) instead of sequentially.

---
