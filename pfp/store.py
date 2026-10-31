from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from .models import Story

SCHEMA = """
create table if not exists items (
  country text not null, rank int not null, edition_at text not null,
  url text not null, data text not null, primary key (country, rank)
);
create table if not exists history (
  country text not null, edition_at text not null, url text not null, data text not null
);
create index if not exists history_cc on history(country, edition_at);
create table if not exists api_keys (
  key_hash text primary key, label text not null, created_at text not null,
  revoked int not null default 0, per_minute int not null default 60
);
"""


class Store:
    def __init__(self, path: str | Path = "data/pfp.sqlite3"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()

    # editions -----------------------------------------------------------
    def save(self, country: str, items, edition_at: datetime) -> None:
        ts = edition_at.isoformat()
        with self.lock, self.db:
            self.db.execute("delete from items where country = ?", (country,))
            for it in items:
                d = json.dumps(it.to_dict(), ensure_ascii=False)
                self.db.execute("insert into items values (?,?,?,?,?)", (country, it.rank, ts, it.story.url, d))
                if not it.stale:
                    self.db.execute("insert into history values (?,?,?,?)", (country, ts, it.story.url, d))

    def edition(self, country: str) -> list[dict]:
        rows = self.db.execute("select data from items where country = ? order by rank", (country.upper(),))
        return [json.loads(r["data"]) for r in rows]

    def all_editions(self) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for r in self.db.execute("select country, data from items order by country, rank"):
            out.setdefault(r["country"], []).append(json.loads(r["data"]))
        return out

    def updated_at(self) -> str | None:
        r = self.db.execute("select max(edition_at) as t from items").fetchone()
        return r["t"] if r else None

    def previous(self, country: str, limit: int = 20) -> list[Story]:
        rows = self.db.execute(
            "select data from history where country = ? order by edition_at desc limit ?", (country, limit))
        out = []
        for r in rows:
            d = json.loads(r["data"])
            pub = datetime.fromisoformat(d["published"]) if d.get("published") else None
            out.append(Story(title=d["title"], url=d["url"], source=d["source"], country=d["country"],
                             published=pub, language=d.get("language", ""), via=d.get("via", ""),
                             local=d.get("local", False), summary=d.get("summary", ""), image=d.get("image", "")))
        return out

    def search(self, q: str, limit: int = 50) -> list[dict]:
        rows = self.db.execute("select data from items where data like ? limit ?", (f"%{q}%", limit))
        return [json.loads(r["data"]) for r in rows]

    # api keys -----------------------------------------------------------
    @staticmethod
    def _hash(key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()

    def create_key(self, label: str, per_minute: int = 60) -> str:
        key = "pfp_" + secrets.token_urlsafe(24)
        with self.lock, self.db:
            self.db.execute("insert into api_keys values (?,?,?,0,?)",
                            (self._hash(key), label, datetime.now(timezone.utc).isoformat(), per_minute))
        return key

    def check_key(self, key: str) -> sqlite3.Row | None:
        return self.db.execute("select * from api_keys where key_hash = ? and revoked = 0",
                               (self._hash(key),)).fetchone()

    def revoke_key(self, key: str) -> bool:
        with self.lock, self.db:
            cur = self.db.execute("update api_keys set revoked = 1 where key_hash = ?", (self._hash(key),))
        return cur.rowcount > 0
