"""Scrape all posts from chillphysicsenjoyer.substack.com via the Substack public API."""
import json
import time
from pathlib import Path
import requests

BASE = "https://chillphysicsenjoyer.substack.com"
OUT = Path(__file__).resolve().parent.parent / "posts"
OUT.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0 Safari/537.36",
    "Accept": "application/json",
}

session = requests.Session()
session.headers.update(HEADERS)


def list_archive():
    """Page through the archive endpoint to collect every post stub."""
    posts = []
    offset = 0
    limit = 50
    while True:
        url = f"{BASE}/api/v1/archive?sort=new&limit={limit}&offset={offset}"
        r = session.get(url, timeout=30)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        posts.extend(batch)
        print(f"  archive offset={offset} got={len(batch)} total={len(posts)}")
        if len(batch) < limit:
            break
        offset += limit
        time.sleep(0.3)
    return posts


def fetch_post(slug):
    url = f"{BASE}/api/v1/posts/{slug}"
    r = session.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def main():
    slugs_file = Path(__file__).resolve().parent / "slugs.txt"
    slugs = [s.strip() for s in slugs_file.read_text().splitlines() if s.strip()]
    print(f"Loaded {len(slugs)} slugs")

    for i, slug in enumerate(slugs, 1):
        out_file = OUT / f"{slug}.json"
        if out_file.exists():
            continue
        try:
            print(f"[{i}/{len(slugs)}] fetching {slug}")
            post = fetch_post(slug)
            out_file.write_text(json.dumps(post, indent=2))
            time.sleep(0.4)
        except requests.HTTPError as e:
            print(f"  !! {slug}: {e}")
            time.sleep(2)
        except Exception as e:
            print(f"  !! {slug}: {e}")

    print("Done.")


if __name__ == "__main__":
    main()
