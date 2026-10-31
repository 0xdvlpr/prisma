"""Public read API.

  GET /v1/countries                 every country with its story count
  GET /v1/countries/{code}/top      the country's top 5
  GET /v1/top?region=Europe         lead story for every country
  GET /v1/search?q=election         search the current edition

Send the key as the `X-API-Key` header. Create keys with `pfp keys create`.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .countries import all_countries, get as get_country
from .store import Store

store = Store(os.environ.get("PFP_DB", "data/pfp.sqlite3"))
app = FastAPI(title="Planet Front Page API", version="1.0",
              description="Top five news stories for every country in the world.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["X-API-Key"])

_hits: dict[str, deque] = defaultdict(deque)
OPEN = os.environ.get("PFP_OPEN_API") == "1"   # set to run without keys, e.g. locally


def api_key(x_api_key: str | None = Header(default=None)) -> str:
    if OPEN:
        return "open"
    if not x_api_key:
        raise HTTPException(401, "Add your key in the X-API-Key header. Create one with `pfp keys create`.")
    row = store.check_key(x_api_key)
    if row is None:
        raise HTTPException(401, "This API key isn't valid or has been revoked.")
    window = _hits[row["key_hash"]]
    now = time.monotonic()
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= row["per_minute"]:
        raise HTTPException(429, f"Rate limit is {row['per_minute']} requests a minute. Try again shortly.")
    window.append(now)
    return row["label"]


def _meta(n: int) -> dict:
    return {"updated_at": store.updated_at(), "count": n}


@app.get("/v1/countries")
def countries(_: str = Depends(api_key)):
    eds = store.all_editions()
    rows = [{"code": c.iso2, "name": c.name, "region": c.region, "stories": len(eds.get(c.iso2, []))}
            for c in all_countries()]
    return {"meta": _meta(len(rows)), "data": rows}


@app.get("/v1/countries/{code}/top")
def country_top(code: str, _: str = Depends(api_key)):
    try:
        c = get_country(code)
    except KeyError:
        raise HTTPException(404, f"No country with code {code!r}. Use ISO 3166-1 alpha-2, e.g. AU.")
    items = store.edition(c.iso2)
    return {"meta": _meta(len(items)) | {"country": c.name, "region": c.region}, "data": items}


@app.get("/v1/top")
def leads(region: str | None = Query(default=None), _: str = Depends(api_key)):
    eds = store.all_editions()
    rows = []
    for c in all_countries():
        if region and c.region.lower() != region.lower():
            continue
        if eds.get(c.iso2):
            rows.append({"country": c.iso2, "name": c.name, **eds[c.iso2][0]})
    return {"meta": _meta(len(rows)), "data": rows}


@app.get("/v1/search")
def search(q: str = Query(min_length=2), _: str = Depends(api_key)):
    rows = store.search(q)
    return {"meta": _meta(len(rows)) | {"q": q}, "data": rows}
