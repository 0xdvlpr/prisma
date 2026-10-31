"""GDELT DOC 2.0 API. Covers outlets in nearly every country, so it is the backbone
for small countries that have no Google News edition or publisher feeds."""
from __future__ import annotations

from datetime import datetime, timezone

from ..countries import Country
from ..models import Story, domain
from . import http

API = "https://api.gdeltproject.org/api/v2/doc/doc"


def _parse_seen(s: str) -> datetime | None:
    try:
        return datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _timespan(hours: int) -> str:
    return f"{hours}h" if hours < 72 else f"{max(1, hours // 24)}d"


def _query(q: str, hours: int, maxrecords: int = 75) -> list[dict]:
    resp = http.get(API, params={
        "query": q, "mode": "artlist", "format": "json",
        "maxrecords": maxrecords, "timespan": _timespan(hours), "sort": "hybridrel",
    })
    if not resp.text.strip().startswith("{"):
        return []   # GDELT answers plain text for bad queries
    return resp.json().get("articles", []) or []


def _to_stories(rows: list[dict], country: Country, local: bool) -> list[Story]:
    out = []
    for a in rows:
        title, url = (a.get("title") or "").strip(), a.get("url") or ""
        if not title or not url:
            continue
        out.append(Story(
            title=title, url=url, source=a.get("domain") or domain(url), country=country.iso2,
            published=_parse_seen(a.get("seendate")), language=(a.get("language") or "")[:2].lower(),
            via="gdelt", local=local, image=a.get("socialimage") or "",
        ))
    return out


class GdeltLocal:
    """Articles published by outlets based in the country."""
    name = "gdelt"

    def collect(self, country: Country, hours: int) -> list[Story]:
        return _to_stories(_query(f"sourcecountry:{country.gdelt_source}", hours), country, local=True)


class GdeltMentions:
    """Articles anywhere in the world that name the country. Used as a fallback."""
    name = "gdelt-mentions"

    def collect(self, country: Country, hours: int) -> list[Story]:
        return _to_stories(_query(f'"{country.name}"', hours, maxrecords=50), country, local=False)
