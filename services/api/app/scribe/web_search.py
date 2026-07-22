"""Optional live web-search grounding for Scribe post generation, via the
`ddgs` PyPI package (DuckDuckGo search, no API key required). Wrapped
end-to-end in try/except returning [] on any failure -- not installed,
rate-limited, network error, or a changed upstream API must never block or
fail post generation. Matches this codebase's established
graceful-degradation posture (see services/worker/app/extraction/ocr.py,
which never lets an optional enhancement take down the main feature).
"""
from __future__ import annotations

import logging

logger = logging.getLogger("profilepilot.api.scribe.web_search")


def search(query: str, max_results: int = 5) -> list[dict]:
    """Returns a list of {title, snippet, url} dicts, or [] on any failure."""
    try:
        from ddgs import DDGS  # imported lazily: optional dependency, never let an import failure at module load break the app

        with DDGS() as ddgs:
            raw = ddgs.text(query, max_results=max_results) or []
        return [
            {
                "title": r.get("title", ""),
                "snippet": r.get("body", ""),
                "url": r.get("href", ""),
            }
            for r in raw
        ]
    except Exception:  # noqa: BLE001 - web search is optional grounding, never fatal
        logger.warning("Web search failed; continuing without grounding", exc_info=True)
        return []
