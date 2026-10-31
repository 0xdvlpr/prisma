"""Google News RSS through pygooglenews.

pygooglenews is used when installed. Its RSS endpoints are simple, so a direct
feedparser fallback is built in for environments where the package won't install.
"""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import feedparser

from ..countries import Country
from ..models import Story
from . import http

try:  # optional dependency
    from pygooglenews import GoogleNews  # type: ignore
except Exception:  # noqa: BLE001
    GoogleNews = None


def _when(hours: int) -> str:
    return f"{hours}h" if hours < 48 else f"{hours // 24}d"


def _parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _entries(url: str) -> list:
    return feedparser.parse(http.get(url).content).entries


def _split_title(title: str, source: str) -> str:
    # Google News appends " - Outlet" to every title.
    suffix = f" - {source}"
    return title[: -len(suffix)] if source and title.endswith(suffix) else title


def _to_stories(entries, country: Country, local: bool) -> list[Story]:
    out = []
    for e in entries:
        src = (e.get("source") or {}).get("title", "") if isinstance(e.get("source"), dict) else ""
        title = _split_title(e.get("title", ""), src)
        if not title or not e.get("link"):
            continue
        out.append(Story(title=title, url=e["link"], source=src or "Google News", country=country.iso2,
                         published=_parse_date(e.get("published")), via="gnews", local=local))
    return out


class GoogleNewsEdition:
    """Top stories from the country's own Google News edition."""
    name = "gnews-edition"

    def collect(self, country: Country, hours: int) -> list[Story]:
        if not country.has_gnews_edition:
            return []
        lang = country.gnews_lang
        if GoogleNews is not None:
            entries = GoogleNews(lang=lang, country=country.iso2).top_news()["entries"]
        else:
            entries = _entries(f"https://news.google.com/rss?hl={lang}&gl={country.iso2}&ceid={country.iso2}:{lang.split('-')[0]}")
        return _to_stories(entries, country, local=True)


class GoogleNewsSearch:
    """Search Google News for the country name. Works for every country."""
    name = "gnews-search"

    def collect(self, country: Country, hours: int) -> list[Story]:
        if GoogleNews is not None:
            entries = GoogleNews(lang="en", country="US").search(f'"{country.name}"', when=_when(hours))["entries"]
        else:
            q = quote_plus(f'"{country.name}" when:{_when(hours)}')
            entries = _entries(f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en")
        return _to_stories(entries, country, local=False)
