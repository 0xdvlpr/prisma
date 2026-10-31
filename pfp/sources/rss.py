"""Publisher RSS feeds.

Two lists feed this collector:
* newscatcher's open publisher catalogue (bundled as data/publisher_feeds.db, MIT licence),
  which maps about 50 countries to their main outlets' RSS feeds;
* feeds.yaml, a curated list you extend with outlets for any country.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from importlib.resources import as_file, files
from pathlib import Path

import feedparser
import yaml

from ..countries import Country
from ..models import Story, domain
from . import http

MAX_FEEDS_PER_COUNTRY = 8


def _published(e) -> datetime | None:
    t = e.get("published_parsed") or e.get("updated_parsed")
    return datetime(*t[:6], tzinfo=timezone.utc) if t else None


def read_feed(url: str, country: Country, hours: int, outlet: str = "", via: str = "rss") -> list[Story]:
    parsed = feedparser.parse(http.get(url, timeout=15).content)
    outlet = outlet or parsed.feed.get("title", "") or domain(url)
    out = []
    for e in parsed.entries[:40]:
        if not e.get("title") or not e.get("link"):
            continue
        s = Story(title=e.title.strip(), url=e.link, source=outlet, country=country.iso2,
                  published=_published(e), via=via, local=True, summary=(e.get("summary") or "")[:400])
        if s.published is None or s.age_hours() <= hours:
            out.append(s)
    return out


class NewscatcherFeeds:
    name = "newscatcher"

    def __init__(self) -> None:
        with as_file(files("pfp.data").joinpath("publisher_feeds.db")) as p:
            db = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
            rows = db.execute(
                "select clean_country, clean_url, rss_url from rss_main "
                "where main = 1 and topic_unified = 'news' and clean_country != 'None' "
                "order by GlobalRank").fetchall()
            db.close()
        self.feeds: dict[str, list[tuple[str, str]]] = {}
        for cc, site, rss in rows:
            self.feeds.setdefault(cc.upper(), []).append((site, rss))

    def collect(self, country: Country, hours: int) -> list[Story]:
        out: list[Story] = []
        for site, rss in self.feeds.get(country.iso2, [])[:MAX_FEEDS_PER_COUNTRY]:
            try:
                out += read_feed(rss, country, hours, outlet=site, via="newscatcher")
            except Exception:  # noqa: BLE001 - dead feeds are common
                continue
        return out


class CuratedFeeds:
    name = "rss"

    def __init__(self, path: str | Path = "feeds.yaml") -> None:
        p = Path(path)
        self.feeds: dict[str, list[dict]] = yaml.safe_load(p.read_text()) if p.exists() else {}

    def collect(self, country: Country, hours: int) -> list[Story]:
        out: list[Story] = []
        for f in (self.feeds or {}).get(country.iso2, [])[:MAX_FEEDS_PER_COUNTRY]:
            try:
                out += read_feed(f["url"], country, hours, outlet=f.get("name", ""))
            except Exception:  # noqa: BLE001
                continue
        return out
