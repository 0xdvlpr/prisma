"""Split edition.json into write batches of 50 documents for the live site's story store.

Usage: python scripts/edition_to_batches.py edition.json out_dir/
Writes out_dir/batch_000.json, batch_001.json, ... each a list of
{op, collection, doc_id, data} entries, plus meta/edition.
"""
import json
import sys
from pathlib import Path

src, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
ed = json.loads(src.read_text())
writes = [{"op": "set", "collection": "meta", "doc_id": "edition", "data": {"updatedAt": ed["updated_at"]}}]
for c in ed["countries"]:
    for s in c["stories"]:
        data = {"country": c["code"], "rank": s["rank"], "title": s["title"], "url": s["url"],
                "source": s["source"], "outlets": s.get("outlets") or 1, "stale": bool(s.get("stale"))}
        if s.get("published"):
            data["published"] = s["published"]
        writes.append({"op": "set", "collection": "stories", "doc_id": f"{c['code'].lower()}-{s['rank']}", "data": data})
for i in range(0, len(writes), 50):
    (out / f"batch_{i // 50:03d}.json").write_text(json.dumps(writes[i:i + 50], ensure_ascii=False))
print(f"{len(writes)} writes in {(len(writes) + 49) // 50} batches")
