"""Build the static blog from scraped Substack JSON."""
import json
import shutil
from datetime import datetime
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
POSTS = ROOT / "posts"
SITE = ROOT / "docs"
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"


def parse_date(s):
    if not s:
        return datetime(1970, 1, 1)
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def clean_body(html: str) -> str:
    """Strip Substack subscribe widgets and other CTAs from post body."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    junk_selectors = [
        ".subscription-widget",
        ".subscription-widget-wrap",
        ".subscribe-widget",
        ".button-wrapper",
        ".embedded-publication",
        ".pencraft",
        "div[data-component-name='SubscribeWidget']",
        "div[data-component-name='ButtonCreateButton']",
    ]
    for sel in junk_selectors:
        for tag in soup.select(sel):
            tag.decompose()
    # Substack image wrappers often have captioned-image-container — keep them
    return str(soup)


def load_posts():
    posts = []
    for p in POSTS.glob("*.json"):
        if p.name.startswith("_"):
            continue
        data = json.loads(p.read_text())
        if not data.get("is_published", True):
            continue
        body = data.get("body_html") or ""
        if not body.strip() and not data.get("title"):
            continue
        d = parse_date(data.get("post_date"))
        posts.append({
            "slug": data["slug"],
            "title": data.get("title") or data["slug"],
            "subtitle": data.get("subtitle") or "",
            "date": d,
            "date_human": d.strftime("%-d %B %Y"),
            "date_short": d.strftime("%-d %b"),
            "year": d.year,
            "body_html": clean_body(body),
            "canonical_url": data.get("canonical_url")
                or f"https://chillphysicsenjoyer.substack.com/p/{data['slug']}",
            "tags": [t.get("name") for t in data.get("postTags") or [] if t.get("name")],
            "wordcount": data.get("wordcount") or 0,
        })
    posts.sort(key=lambda p: p["date"], reverse=True)
    # link prev/next (in chronological order across the list)
    for i, p in enumerate(posts):
        p["next"] = posts[i - 1]["slug"] if i > 0 else None
        p["prev"] = posts[i + 1]["slug"] if i + 1 < len(posts) else None
    return posts


def main():
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir()
    (SITE / "posts").mkdir()

    # copy static assets
    for f in STATIC.iterdir():
        shutil.copy2(f, SITE / f.name)

    posts = load_posts()
    print(f"Loaded {len(posts)} posts")

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html"]),
    )

    # group by year for archive
    by_year = {}
    for p in posts:
        by_year.setdefault(p["year"], []).append(p)
    by_year_sorted = sorted(by_year.items(), key=lambda kv: kv[0], reverse=True)

    # index: show 8 most recent in full
    index_tpl = env.get_template("index.html")
    (SITE / "index.html").write_text(index_tpl.render(
        recent=posts[:8],
        total=len(posts),
        root="",
    ))

    # archive
    arch_tpl = env.get_template("archive.html")
    (SITE / "archive.html").write_text(arch_tpl.render(
        by_year=by_year_sorted,
        total=len(posts),
        root="",
    ))

    # about
    about_tpl = env.get_template("about.html")
    (SITE / "about.html").write_text(about_tpl.render(root=""))

    # individual posts
    post_tpl = env.get_template("post.html")
    for p in posts:
        out = SITE / "posts" / f"{p['slug']}.html"
        out.write_text(post_tpl.render(post=p, root="../"))

    print(f"Wrote {len(posts)} post pages, index, archive, about -> {SITE}")


if __name__ == "__main__":
    main()
