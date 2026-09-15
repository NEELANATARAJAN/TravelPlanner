"""
ingest.py
Ties wikivoyage_loader + pinecone_store together: pull each destination's
Wikivoyage article, chunk it, and upsert into Pinecone. This is what runs
on a schedule (see scheduler.py) to keep the vector DB fresh.
"""

from wikivoyage_loader import load_destination_chunks
from pinecone_store import upsert_chunks

# Add/remove destinations here, or load this list from a config file /
# database instead if it grows large.
DESTINATIONS = [
    {"destination": "Kyoto"},
    {"destination": "Lisbon"},
    {"destination": "Bangkok"},
    {"destination": "Marrakesh"},
    {"destination": "Reykjavik"},
    # If the Wikivoyage page title differs from the destination name:
    # {"destination": "New York City", "page_title": "New York City"},
]


def run_full_ingest(destinations: list[dict] = DESTINATIONS) -> dict:
    """Fetch + chunk + upsert every configured destination. Returns a
    summary dict so the caller (or scheduler) can log/monitor results."""
    summary = {"destinations": 0, "chunks": 0, "errors": []}

    for dest in destinations:
        try:
            chunks = load_destination_chunks(
                destination=dest["destination"],
                page_title=dest.get("page_title"),
            )
            if not chunks:
                summary["errors"].append(f"{dest['destination']}: no chunks extracted")
                continue

            upsert_chunks(chunks)
            summary["destinations"] += 1
            summary["chunks"] += len(chunks)
            print(f"[ingest] {dest['destination']}: upserted {len(chunks)} chunks")

        except Exception as err:  # noqa: BLE001
            # One bad destination should never abort the whole ingest run.
            msg = f"{dest['destination']}: {err}"
            summary["errors"].append(msg)
            print(f"[ingest] ERROR — {msg}")

    return summary


if __name__ == "__main__":
    result = run_full_ingest()
    print(f"\nIngest complete: {result}")
