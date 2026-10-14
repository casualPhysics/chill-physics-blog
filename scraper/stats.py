"""Refresh like/comment counts for every post into posts/_stats.json.

Uses the public post endpoint (no auth). Files starting with "_" in posts/
are ignored by build.py's post loader, so this sits safely alongside the
scraped post JSON.  Run:  .venv/bin/python scraper/stats.py
"""
import json
import time
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "posts"
OUT = POSTS / "_stats.json"
BASE = "https://chillphysicsenjoyer.substack.com/api/v1/posts/"


def main():
    old = json.loads(OUT.read_text()) if OUT.exists() else {"posts": {}}
    stats = dict(old.get("posts", {}))
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0"
    slugs = sorted(p.stem for p in POSTS.glob("*.json") if not p.name.startswith("_"))
    failed = []
    for slug in slugs:
        for attempt in range(3):
            r = s.get(BASE + slug, timeout=30)
            if r.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            break
        if r.status_code != 200:
            failed.append((slug, r.status_code))
            if slug not in stats:  # fall back to the scraped snapshot
                d = json.loads((POSTS / f"{slug}.json").read_text())
                stats[slug] = {"likes": d.get("reaction_count") or 0,
                               "comments": d.get("comment_count") or 0,
                               "restacks": d.get("restacks") or 0}
            continue
        d = r.json()
        stats[slug] = {"likes": d.get("reaction_count") or 0,
                       "comments": d.get("comment_count") or 0,
                       "restacks": d.get("restacks") or 0}
        time.sleep(0.4)
    OUT.write_text(json.dumps({"fetched": date.today().isoformat(), "posts": stats},
                              indent=1, sort_keys=True))
    print(f"Wrote {len(stats)} entries to {OUT}; {len(failed)} not refreshed: {failed}")


if __name__ == "__main__":
    main()
