"""Newsworthiness ranking.

The signal is agreement: a story many independent outlets are running is more
newsworthy than one only a single outlet carries. Stories are clustered by
headline similarity, then each cluster is scored on how many distinct outlets
cover it, how fresh it is, and whether local outlets carry it.
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime

from .models import Story

STOPWORDS = set("""a an the and or of to in on for at by with from as is are was were be been
it its this that these those after over into amid says said new news live latest update updates
video watch photos how what why who will would could can may about up out his her their our""".split())

SIMILARITY = 0.45           # Jaccard threshold on headline tokens for "same story"
MIN_SHARED = 3              # and at least this many shared content words
HALF_LIFE_HOURS = 18.0      # freshness decay

# Low-value items that make a front page look broken: briefings, live blogs, listings.
NOISE = re.compile(r"(horoscope|crossword|wordle|lottery results|weather forecast|"
                   r"newsletter|podcast|^watch:|full episode|live updates?$)", re.I)


def tokens(title: str) -> set[str]:
    t = unicodedata.normalize("NFKD", title.lower())
    words = re.findall(r"[^\W_]+", t)
    return {w for w in words if len(w) > 2 and w not in STOPWORDS}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass
class Cluster:
    stories: list[Story] = field(default_factory=list)
    toks: set[str] = field(default_factory=set)
    score: float = 0.0

    @property
    def outlets(self) -> set[str]:
        return {s.domain for s in self.stories}

    @property
    def lead(self) -> Story:
        # Prefer a local outlet, then the freshest, then the shortest clean headline.
        return sorted(self.stories, key=lambda s: (not s.local, s.age_hours(), len(s.title)))[0]


def dedupe(stories: list[Story]) -> list[Story]:
    seen, out = set(), []
    for s in stories:
        if s.key in seen or NOISE.search(s.title):
            continue
        seen.add(s.key)
        out.append(s)
    return out


def cluster(stories: list[Story]) -> list[Cluster]:
    clusters: list[Cluster] = []
    for s in stories:
        t = tokens(s.title)
        best, best_sim = None, 0.0
        for c in clusters:
            # Short headlines overlap by accident ("Fiji news one" / "Fiji news two"),
            # so a match also needs several shared content words.
            if len(t & c.toks) < MIN_SHARED:
                continue
            sim = jaccard(t, c.toks)
            if sim > best_sim:
                best, best_sim = c, sim
        if best is not None and best_sim >= SIMILARITY:
            best.stories.append(s)
            best.toks |= t
        else:
            clusters.append(Cluster([s], set(t)))
    return clusters


def score(c: Cluster, now: datetime | None = None) -> float:
    outlets = len(c.outlets)
    collectors = len({s.via for s in c.stories})
    freshest = min(s.age_hours(now) for s in c.stories)
    local_share = sum(s.local for s in c.stories) / len(c.stories)
    coverage = 3.0 * math.log2(1 + outlets) + 1.0 * (collectors - 1)
    freshness = 0.5 ** (freshest / HALF_LIFE_HOURS)
    return round(coverage * (0.4 + 0.6 * freshness) + 1.5 * local_share, 4)


def rank(stories: list[Story], k: int = 5, now: datetime | None = None) -> list[tuple[Story, float, int]]:
    """Return the top-k stories as (lead story, score, number of outlets covering it)."""
    clusters = cluster(dedupe(stories))
    for c in clusters:
        c.score = score(c, now)
    clusters.sort(key=lambda c: (-c.score, min(s.age_hours(now) for s in c.stories)))
    picked, used_domains = [], {}
    # Keep the front page varied: at most two lead stories from the same outlet.
    for c in clusters:
        lead = c.lead
        if used_domains.get(lead.domain, 0) >= 2 and len(clusters) > k * 2:
            continue
        used_domains[lead.domain] = used_domains.get(lead.domain, 0) + 1
        picked.append((lead, c.score, len(c.outlets)))
        if len(picked) == k:
            break
    return picked
