from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files


@dataclass(frozen=True)
class Country:
    iso2: str
    name: str
    region: str
    gdelt_source: str   # GDELT DOC API `sourcecountry:` value
    gnews_lang: str     # Google News edition language, "" when no national edition exists

    @property
    def has_gnews_edition(self) -> bool:
        return bool(self.gnews_lang)


@lru_cache(maxsize=1)
def all_countries() -> tuple[Country, ...]:
    text = files("pfp.data").joinpath("countries.csv").read_text(encoding="utf-8")
    rows = csv.DictReader(text.splitlines())
    return tuple(Country(**r) for r in rows)


def get(iso2: str) -> Country:
    iso2 = iso2.upper()
    for c in all_countries():
        if c.iso2 == iso2:
            return c
    raise KeyError(f"Unknown country code: {iso2}")
