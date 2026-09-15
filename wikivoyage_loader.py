"""
wikivoyage_loader.py
Fetches a Wikivoyage article via the public MediaWiki API and chunks it
into the same {destination, topic, text} shape used elsewhere in this
project — except each chunk also carries a `source_url` so retrieved
results can be cited back to Wikivoyage.

Wikivoyage content is CC-BY-SA — if you ship retrieved text to end users,
keep the source_url visible/attributed somewhere in the UI.
"""

import re
import httpx

WIKIVOYAGE_API = "https://en.wikivoyage.org/w/api.php"

# Wikivoyage's standard article sections we care about for a travel-guide
# corpus. Anything else (History, Understand, Connect, etc.) is skipped
# to keep chunks relevant to trip planning.
RELEVANT_SECTIONS = {
    "see": "sights",
    "do": "activities",
    "eat": "food",
    "drink": "food",
    "sleep": "practical",
    "get in": "practical",
    "get around": "practical",
    "stay safe": "practical",
    "buy": "practical",
}


def _fetch_wikitext(page_title: str) -> str:
    """Fetch raw wikitext for an article via the MediaWiki API."""
    resp = httpx.get(
        WIKIVOYAGE_API,
        params={
            "action": "parse",
            "page": page_title,
            "prop": "wikitext",
            "format": "json",
            "formatversion": "2",
        },
        timeout=15,
    )
    data = resp.json()
    if "error" in data:
        raise ValueError(f"Wikivoyage fetch failed for '{page_title}': {data['error']}")
    return data["parse"]["wikitext"]


def _clean_wikitext(text: str) -> str:
    """Strip common wiki markup so chunks read as plain prose."""
    text = re.sub(r"\{\{.*?\}\}", "", text, flags=re.DOTALL)      # templates
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", text)  # [[link|label]] -> label
    text = re.sub(r"'''?(.*?)'''?", r"\1", text)                   # bold/italic markup
    text = re.sub(r"<ref.*?</ref>", "", text, flags=re.DOTALL)     # references
    text = re.sub(r"<.*?>", "", text)                              # stray html tags
    text = re.sub(r"\n{3,}", "\n\n", text)                         # collapse blank lines
    return text.strip()


def _split_sections(wikitext: str) -> list[tuple[str, str]]:
    """Split an article into (section_title, section_body) pairs on == headers ==."""
    parts = re.split(r"\n==\s*([^=]+?)\s*==\n", wikitext)
    # parts[0] is the lead section before the first header
    sections = [("Lead", parts[0])]
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        sections.append((title, body))
    return sections


def load_destination_chunks(destination: str, page_title: str | None = None, max_chunk_chars: int = 800) -> list[dict]:
    """
    Fetch a Wikivoyage article for `destination` and return a list of
    corpus-ready chunks: {destination, topic, text, source_url}.

    `page_title` lets you pass the exact Wikivoyage page name if it
    differs from the destination string (e.g. "Kyoto" vs "Kyoto (city)").
    """
    title = page_title or destination
    wikitext = _fetch_wikitext(title)
    sections = _split_sections(wikitext)

    chunks = []
    source_url = f"https://en.wikivoyage.org/wiki/{title.replace(' ', '_')}"

    for section_title, body in sections:
        topic = RELEVANT_SECTIONS.get(section_title.lower())
        if topic is None:
            continue  # skip sections not relevant to trip planning

        cleaned = _clean_wikitext(body)
        if not cleaned:
            continue

        # Break long sections into smaller chunks so each one stays close
        # to a single retrievable "fact unit" rather than a whole section.
        paragraphs = [p.strip() for p in cleaned.split("\n\n") if p.strip()]
        buffer = ""
        for para in paragraphs:
            if len(buffer) + len(para) > max_chunk_chars and buffer:
                chunks.append({
                    "destination": destination,
                    "topic": topic,
                    "text": buffer.strip(),
                    "source_url": source_url,
                })
                buffer = ""
            buffer += para + "\n\n"
        if buffer.strip():
            chunks.append({
                "destination": destination,
                "topic": topic,
                "text": buffer.strip(),
                "source_url": source_url,
            })

    return chunks
