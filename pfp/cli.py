from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .countries import all_countries
from .pipeline import TARGET, Pipeline
from .store import Store


def cmd_run(a):
    store = Store(a.db)
    codes = [c.strip().upper() for c in a.countries.split(",")] if a.countries else None
    res = Pipeline(store, feeds_path=a.feeds, enrich=a.enrich).run(codes, workers=a.workers)
    full = sum(1 for n in res.values() if n >= TARGET)
    print(f"Filed {len(res)} countries: {full} with {TARGET}+ stories, "
          f"{sum(1 for n in res.values() if 0 < n < TARGET)} short, {sum(1 for n in res.values() if n == 0)} empty.")
    if a.export:
        cmd_export(a)


def cmd_export(a):
    """Write the current edition as one JSON file: the format the website and seed scripts read."""
    store = Store(a.db)
    eds = store.all_editions()
    out = {"updated_at": store.updated_at(), "countries": []}
    for c in all_countries():
        out["countries"].append({"code": c.iso2, "name": c.name, "region": c.region,
                                 "stories": [{k: s.get(k) for k in ("rank", "title", "url", "source", "published",
                                                                    "language", "outlets", "stale", "summary")}
                                             for s in eds.get(c.iso2, [])]})
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"Wrote {a.out}")


def cmd_keys(a):
    store = Store(a.db)
    if a.action == "create":
        print(store.create_key(a.label or "default", a.per_minute))
    elif a.action == "revoke":
        print("Revoked." if store.revoke_key(a.key) else "No such key.")


def cmd_serve(a):
    import os
    import uvicorn
    os.environ["PFP_DB"] = a.db
    uvicorn.run("pfp.api:app", host=a.host, port=a.port)


def main(argv=None):
    p = argparse.ArgumentParser(prog="pfp", description="Planet Front Page: top 5 stories for every country.")
    p.add_argument("--db", default="data/pfp.sqlite3")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="collect, rank and store a new edition")
    r.add_argument("--countries", help="comma-separated ISO codes, e.g. AU,NZ,FJ (default: all)")
    r.add_argument("--feeds", default="feeds.yaml")
    r.add_argument("--workers", type=int, default=4)
    r.add_argument("--enrich", action="store_true", help="fetch summaries and images with news-please")
    r.add_argument("--export", action="store_true", help="also write edition.json")
    r.add_argument("--out", default="edition.json")
    r.set_defaults(fn=cmd_run)

    e = sub.add_parser("export", help="write the current edition to JSON")
    e.add_argument("--out", default="edition.json")
    e.set_defaults(fn=cmd_export)

    k = sub.add_parser("keys", help="manage API keys")
    k.add_argument("action", choices=["create", "revoke"])
    k.add_argument("--label")
    k.add_argument("--key")
    k.add_argument("--per-minute", type=int, default=60)
    k.set_defaults(fn=cmd_keys)

    s = sub.add_parser("serve", help="run the API")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(fn=cmd_serve)

    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
