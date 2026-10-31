from datetime import datetime, timedelta, timezone

import pytest

from pfp import countries
from pfp.models import Story, canonical_url
from pfp.pipeline import TARGET, Pipeline
from pfp.rank import cluster, dedupe, rank
from pfp.store import Store

NOW = datetime(2026, 10, 31, 6, tzinfo=timezone.utc)


def s(title, url, source="x", hours=1, local=True, via="gdelt", cc="AU"):
    return Story(title=title, url=url, source=source, country=cc,
                 published=NOW - timedelta(hours=hours), local=local, via=via)


class Fake:
    def __init__(self, name, by_window):
        self.name, self.by_window, self.calls = name, by_window, []

    def collect(self, country, hours):
        self.calls.append(hours)
        return list(self.by_window.get(hours, []))


class Broken:
    name = "broken"

    def collect(self, country, hours):
        raise ConnectionError("network down")


def test_all_196_countries_load_with_gdelt_names():
    cs = countries.all_countries()
    assert len(cs) == 196
    assert len({c.iso2 for c in cs}) == 196
    assert all(c.gdelt_source.isalpha() for c in cs)


def test_canonical_url_drops_tracking_and_amp():
    a = canonical_url("https://www.example.com/story/amp?utm_source=x&id=7#top")
    assert a == canonical_url("https://example.com/story?id=7")


def test_same_story_from_many_outlets_ranks_first():
    pool = [
        s("Lula wins fourth term in Brazil election", "https://a.com/1", "a"),
        s("Brazil election: Lula wins historic fourth term", "https://b.com/1", "b"),
        s("Lula wins fourth term as Brazil votes", "https://c.com/1", "c", via="gnews"),
        s("Local bakery opens second shop", "https://d.com/1", "d", hours=0.5),
    ]
    top = rank(pool, k=2, now=NOW)
    assert "Lula" in top[0][0].title
    assert top[0][2] == 3          # three outlets in the cluster
    assert len(cluster(dedupe(pool))) == 2


def test_noise_and_duplicate_urls_are_dropped():
    pool = [s("Daily horoscope for Friday", "https://a.com/h"),
            s("Budget passes", "https://a.com/b?utm_source=tw"),
            s("Budget passes", "https://www.a.com/b")]
    assert [x.title for x in dedupe(pool)] == ["Budget passes"]


def test_widens_window_until_five_and_survives_broken_sources(tmp_path):
    thin = Fake("local", {24: [s("Only one story today", "https://t.to/1", cc="TO")],
                          72: [s(h, f"https://t.to/{i}", cc="TO", hours=40) for i, h in enumerate([
                              "Cyclone season outlook issued for the kingdom",
                              "Parliament debates new fisheries licence rules",
                              "Ikale Tahi name squad for November rugby tests",
                              "Power outage hits Nuku'alofa for six hours",
                              "Exporters report record squash shipments to Japan",
                              "Health ministry launches dengue awareness drive"], 2)]})
    p = Pipeline(Store(tmp_path / "t.db"), collectors=([Broken(), thin], [Broken()]))
    items = p.build(countries.get("TO"), now=NOW)
    assert len(items) == TARGET
    assert 72 in thin.calls and 168 not in thin.calls


def test_carries_over_previous_edition_so_country_is_never_blank(tmp_path):
    store = Store(tmp_path / "t.db")
    full = Fake("local", {24: [s(f"Nauru headline {w}", f"https://n.nr/{w}", cc="NR")
                               for w in ["one", "two", "three", "four", "five"]]})
    Pipeline(store, collectors=([full], [])).run(["NR"])
    # Next day every source is down.
    items = Pipeline(store, collectors=([Broken()], [Broken()])).build(countries.get("NR"), now=NOW)
    assert len(items) == TARGET
    assert all(it.stale for it in items)


def test_api_requires_key_and_serves_top_five(tmp_path, monkeypatch):
    pytest.importorskip("httpx")
    monkeypatch.setenv("PFP_DB", str(tmp_path / "api.db"))
    import importlib
    import pfp.api as api
    importlib.reload(api)
    from fastapi.testclient import TestClient
    full = Fake("local", {24: [s(f"Fiji headline {w}", f"https://f.fj/{w}", cc="FJ")
                               for w in ["one", "two", "three", "four", "five", "six"]]})
    Pipeline(api.store, collectors=([full], [])).run(["FJ"])
    client = TestClient(api.app)
    assert client.get("/v1/countries/FJ/top").status_code == 401
    key = api.store.create_key("test")
    r = client.get("/v1/countries/FJ/top", headers={"X-API-Key": key})
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["country"] == "Fiji" and len(body["data"]) == 5
    assert [d["rank"] for d in body["data"]] == [1, 2, 3, 4, 5]
