from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

_TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
             "fbclid", "gclid", "ocid", "cmpid", "ref", "smid"}


def canonical_url(url: str) -> str:
    """Strip tracking parameters, fragments and AMP prefixes so duplicates match."""
    try:
        p = urlsplit(url.strip())
    except ValueError:
        return url
    host = p.netloc.lower().removeprefix("www.").removeprefix("amp.")
    query = urlencode([(k, v) for k, v in parse_qsl(p.query) if k.lower() not in _TRACKING])
    path = p.path.rstrip("/").removesuffix("/amp")
    return urlunsplit(("https", host, path, query, ""))


AGGREGATOR_HOSTS = {"news.google.com"}


def domain(url: str) -> str:
    return urlsplit(url).netloc.lower().removeprefix("www.").removeprefix("amp.")


@dataclass
class Story:
    title: str
    url: str
    source: str                     # outlet name, e.g. "Reuters"
    country: str                    # ISO 3166-1 alpha-2 of the country this story is filed under
    published: datetime | None = None
    language: str = ""
    via: str = ""                   # which collector found it: gdelt, gnews, newscatcher, rss
    local: bool = False             # True when the outlet is based in `country`
    summary: str = ""
    image: str = ""
    section: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return canonical_url(self.url)

    @property
    def domain(self) -> str:
        # Aggregator links (Google News redirects) all share one host, so use the outlet name instead.
        d = domain(self.url)
        if d in AGGREGATOR_HOSTS and self.source:
            return "outlet:" + self.source.strip().lower()
        return d

    def age_hours(self, now: datetime | None = None) -> float:
        if not self.published:
            return 48.0
        now = now or datetime.now(timezone.utc)
        pub = self.published if self.published.tzinfo else self.published.replace(tzinfo=timezone.utc)
        return max(0.0, (now - pub).total_seconds() / 3600)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["published"] = self.published.isoformat() if self.published else None
        d.pop("extra", None)
        return d
