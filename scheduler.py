"""
scheduler.py
Runs ingest.run_full_ingest() on a fixed interval in a background thread,
independent of request traffic — Pinecone is the source of truth for the
retriever agent, and this keeps it in sync with Wikivoyage.

For production, a cron job / scheduled cloud function calling
`python ingest.py` on a schedule is usually simpler and more robust than
an in-process thread (survives app restarts, easier to monitor/alert on
failures independently of the API process). This in-process version is
useful for local dev or small deployments where standing up separate
scheduling infra isn't worth it yet.

Usage:
    python scheduler.py            # runs forever, ingesting every INTERVAL_SEC
"""

import threading
import time

from ingest import run_full_ingest

INTERVAL_SEC = 6 * 60 * 60  # re-ingest every 6 hours; tune to how often Wikivoyage content changes


class IngestScheduler:
    def __init__(self, interval_sec: int = INTERVAL_SEC):
        self._interval_sec = interval_sec
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def _loop(self):
        while not self._stop_event.is_set():
            start = time.time()
            print(f"[scheduler] Starting ingest run...")
            result = run_full_ingest()
            elapsed = time.time() - start
            print(f"[scheduler] Ingest run finished in {elapsed:.1f}s: {result}")

            # Wait for the interval, but check stop_event periodically so
            # shutdown doesn't hang for hours.
            self._stop_event.wait(self._interval_sec)

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)


if __name__ == "__main__":
    scheduler = IngestScheduler()
    scheduler.start()
    print(f"[scheduler] Running, ingesting every {INTERVAL_SEC / 3600:.1f}h. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        scheduler.stop()
