"""Builds each country's edition and guarantees it is never blank.

For every country the pipeline walks a ladder of sources and time windows,
stopping as soon as it has enough distinct stories to rank:

  1. local outlets       GDELT sourcecountry, Google News edition, newscatcher feeds, feeds.yaml
  2. coverage about it   Google News search and GDELT mentions of the country name
  3. wider windows       24 h -> 72 h -> 7 days -> 30 days
  4. carry-over          the previous edition's stories, marked stale

Step 4 means a country can show old news, but it never shows nothing once it has
been filled successfully even one time.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone

from . import rank as ranking
from .countries import Country, all_countries
from .enrich import enrich as enrich_story
from .models import Story
from .sources import safe
from .sources.gdelt import GdeltLocal, GdeltMentions
from .sources.gnews import GoogleNewsEdition, GoogleNewsSearch
from .sources.rss import CuratedFeeds, NewscatcherFeeds
from .store import Store

log = logging.getLogger("pfp.pipeline")

TARGET = 5
CANDIDATES_WANTED = 12          # gather a little more than 5 so ranking has a real choice
WINDOWS_HOURS = (24, 72, 168, 720)


@dataclass
class EditionItem:
    story: Story
    rank: int
    score: float
    outlets: int
    stale: bool = False

    def to_dict(self) -> dict:
        d = self.story.to_dict()
        d.update(rank=self.rank, score=self.score, outlets=self.outlets, stale=self.stale)
        return d


class Pipeline:
    def __init__(self, store: Store, feeds_path: str = "feeds.yaml", collectors=None, enrich: bool = False):
        self.enrich = enrich
        if collectors is None:
            local = [GdeltLocal(), GoogleNewsEdition(), NewscatcherFeeds(), CuratedFeeds(feeds_path)]
            about = [GoogleNewsSearch(), GdeltMentions()]
            collectors = (local, about)
        self.local, self.about = collectors
        self.store = store

    def gather(self, country: Country) -> tuple[list[Story], int]:
        pool: list[Story] = []
        window = WINDOWS_HOURS[0]
        for window in WINDOWS_HOURS:
            for tier in (self.local, self.about):
                for c in tier:
                    pool += safe(lambda c=c: c.collect(country, window), f"{c.name}:{country.iso2}")
                if len(ranking.cluster(ranking.dedupe(pool))) >= CANDIDATES_WANTED:
                    return pool, window
            if len(ranking.cluster(ranking.dedupe(pool))) >= TARGET:
                return pool, window
        return pool, window

    def build(self, country: Country, now: datetime | None = None) -> list[EditionItem]:
        now = now or datetime.now(timezone.utc)
        pool, window = self.gather(country)
        top = ranking.rank(pool, k=TARGET, now=now)
        items = [EditionItem(s, i + 1, sc, n) for i, (s, sc, n) in enumerate(top)]
        if self.enrich:
            for it in items:
                enrich_story(it.story)
        if len(items) < TARGET:
            have = {it.story.key for it in items}
            for old in self.store.previous(country.iso2):
                if len(items) >= TARGET:
                    break
                if old.key not in have:
                    items.append(EditionItem(old, len(items) + 1, 0.0, 1, stale=True))
                    have.add(old.key)
        log.info("%s %s: %d stories (%d candidates, %dh window)",
                 country.iso2, country.name, len(items), len(pool), window)
        return items

    def run(self, codes: list[str] | None = None, workers: int = 4) -> dict[str, int]:
        countries = [c for c in all_countries() if not codes or c.iso2 in codes]
        edition_at = datetime.now(timezone.utc)
        results: dict[str, int] = {}

        def one(c: Country):
            items = self.build(c, now=edition_at)
            if items:
                self.store.save(c.iso2, items, edition_at)
            return c.iso2, len(items)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for cc, n in pool.map(one, countries):
                results[cc] = n
        short = sorted(k for k, v in results.items() if v < TARGET)
        if short:
            log.warning("Under %d stories: %s", TARGET, ", ".join(short))
        return results
