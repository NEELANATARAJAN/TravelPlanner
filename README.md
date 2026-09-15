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

## Extending

- **More destinations**: add entries to `DESTINATIONS` in `ingest.py`.
  For very large destination lists, move this to a config file or DB
  table rather than a Python list.
- **Chunking strategy**: `wikivoyage_loader.py`'s `max_chunk_chars` and
  `RELEVANT_SECTIONS` control what gets ingested and how finely it's
  split — tune both if retrieval quality is off (too coarse = irrelevant
  padding in results, too fine = missing context).
- **Hybrid search**: Pinecone supports sparse+dense hybrid indexes if
  you find pure semantic search misses exact-match needs (e.g. specific
  venue names) — see Pinecone's hybrid search docs.
- **Attribution**: Wikivoyage is CC-BY-SA. `source_url` is carried
  through every retrieved chunk specifically so your UI can display
  attribution/links back to the source article.
