"""Optional full-article enrichment with news-please.

Only the five published stories per country are fetched, so this adds about
a thousand page loads per run. It fills in a summary, image and language where
the collectors left them empty.
"""
from __future__ import annotations

import logging

log = logging.getLogger("pfp.enrich")

try:
    from newsplease import NewsPlease  # type: ignore
except Exception:  # noqa: BLE001
    NewsPlease = None


def enrich(story) -> None:
    if NewsPlease is None:
        return
    try:
        art = NewsPlease.from_url(story.url, timeout=15)
    except Exception as exc:  # noqa: BLE001
        log.debug("news-please failed for %s: %s", story.url, exc)
        return
    if art is None:
        return
    if not story.summary and art.description:
        story.summary = art.description.strip()[:400]
    if not story.image and art.image_url:
        story.image = art.image_url
    if not story.language and art.language:
        story.language = art.language
    if story.published is None and art.date_publish:
        story.published = art.date_publish
