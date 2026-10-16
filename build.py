"""Build the static blog from scraped Substack JSON."""
import hashlib
import html as htmlmod
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from bs4 import BeautifulSoup
import markdown

NBSP = " "

# Substack embeds non-breaking spaces (&nbsp; -> U+00A0) inside LaTeX, e.g.
# "$$ \xa0d\tau ^2 \xa0= \frac {..} {..} $$".  MathJax can't tokenize U+00A0,
# so the math silently fails to render.  Normalize it to a plain space inside
# math delimiters only (display $$..$$ and inline $..$), leaving prose untouched.
_DISPLAY_MATH = re.compile(r"\$\$.+?\$\$", re.S)
_INLINE_MATH = re.compile(r"(?<!\$)\$(?!\$).+?(?<!\$)\$(?!\$)", re.S)


def fix_math(html: str) -> str:
    if not html or "$" not in html:
        return html
    repl = lambda m: m.group(0).replace(NBSP, " ")
    html = _DISPLAY_MATH.sub(repl, html)
    html = _INLINE_MATH.sub(repl, html)
    return html

ROOT = Path(__file__).resolve().parent
POSTS = ROOT / "posts"
SITE = ROOT / "docs"
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"
LAB = ROOT / "lab"
CURATED = ROOT / "curated" / "popular.json"
STATS = POSTS / "_stats.json"


def parse_date(s):
    if not s:
        return datetime(1970, 1, 1)
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def make_excerpt(html: str, words: int = 48) -> str:
    """Plain-text teaser for the index page."""
    text = BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)
    parts = text.split()
    if len(parts) <= words:
        return text
    return " ".join(parts[:words]) + "…"


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
    # Newer posts store block math as an empty <div class="latex-rendered">
    # whose LaTeX lives in data-attrs JSON (persistentExpression); Substack
    # renders it client-side, so statically it shows nothing.  Convert each
    # into a MathJax display-math paragraph.
    for tag in soup.select(".latex-rendered"):
        expr = ""
        raw = tag.get("data-attrs")
        if raw:
            try:
                expr = (json.loads(raw).get("persistentExpression") or "").strip()
            except (ValueError, TypeError):
                expr = ""
        new = soup.new_tag("p")
        new["class"] = "math-block"
        new.string = f"$$ {expr} $$" if expr else ""
        tag.replace_with(new)
    # Substack image wrappers often have captioned-image-container — keep them
    return fix_math(str(soup))


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
        cleaned = clean_body(body)
        excerpt = (data.get("description") or "").strip() or make_excerpt(cleaned)
        posts.append({
            "slug": data["slug"],
            "title": data.get("title") or data["slug"],
            "subtitle": data.get("subtitle") or "",
            "date": d,
            "date_human": d.strftime("%-d %B %Y"),
            "date_short": d.strftime("%-d %b"),
            "year": d.year,
            "body_html": cleaned,
            "excerpt": excerpt,
            "canonical_url": data.get("canonical_url")
                or f"https://chillphysicsenjoyer.substack.com/p/{data['slug']}",
            "tags": [t.get("name") for t in data.get("postTags") or [] if t.get("name")],
            "wordcount": int(data.get("wordcount") or 0),
            "cover_image": data.get("cover_image") or "",
        })
    posts.sort(key=lambda p: p["date"], reverse=True)
    # link prev/next (in chronological order across the list)
    for i, p in enumerate(posts):
        p["next"] = posts[i - 1]["slug"] if i > 0 else None
        p["prev"] = posts[i + 1]["slug"] if i + 1 < len(posts) else None
    return posts


def md_to_html(text: str) -> str:
    return fix_math(markdown.markdown(
        text, extensions=["tables", "fenced_code", "md_in_html"]))


def load_lab_pages():
    """Each subdir of lab/ is one write-up: meta.json + page.md + files/."""
    pages = []
    if not LAB.exists():
        return pages
    for d in sorted(LAB.iterdir()):
        if not d.is_dir() or not (d / "meta.json").exists():
            continue
        meta = json.loads((d / "meta.json").read_text())
        date = datetime.fromisoformat(meta["date"])
        files = d / "files"
        page = {
            "slug": d.name,
            "title": meta["title"],
            "summary": meta.get("summary", ""),
            "date": date,
            "date_human": date.strftime("%-d %B %Y"),
            "body_html": md_to_html((d / "page.md").read_text()),
            "files_dir": files if files.exists() else None,
            "code_file": meta.get("code_file"),
            "code_html": None,
            "code_lines": 0,
            "extra_pages": meta.get("extra_pages", []),
            "parent": None,
        }
        if page["code_file"] and files.exists():
            src = (files / page["code_file"]).read_text()
            page["code_html"] = htmlmod.escape(src)
            page["code_lines"] = src.count("\n") + 1
        pages.append(page)
    pages.sort(key=lambda p: p["date"], reverse=True)
    return pages


def build_lab(env, by_year_sorted, css_version):
    pages = load_lab_pages()
    (SITE / "lab").mkdir(exist_ok=True)
    page_tpl = env.get_template("lab_page.html")
    for page in pages:
        if page["files_dir"]:
            shutil.copytree(page["files_dir"], SITE / "lab" / page["slug"])
        (SITE / "lab" / f"{page['slug']}.html").write_text(page_tpl.render(
            page=page, nav_years=by_year_sorted, css_version=css_version,
            active_slug=None, root="../",
        ))
        for extra in page["extra_pages"]:
            src = page["files_dir"] / extra["src"]
            sub = {
                "slug": page["slug"], "title": extra["title"],
                "date_human": page["date_human"],
                "body_html": md_to_html(src.read_text()),
                "code_html": None,
                "parent": {"title": page["title"], "href": f"../{page['slug']}.html"},
            }
            (SITE / "lab" / page["slug"] / extra["out"]).write_text(page_tpl.render(
                page=sub, nav_years=by_year_sorted, css_version=css_version,
                active_slug=None, root="../../",
            ))
    (SITE / "lab.html").write_text(env.get_template("lab.html").render(
        lab_pages=pages, nav_years=by_year_sorted, css_version=css_version,
        active_slug=None, root="",
    ))
    return pages


from urllib.parse import quote

_CDN_PREFIX = "https://substackcdn.com/image/fetch/"


THUMBS = ROOT / "thumbs"


def fetch_thumbs(posts, size: int = 120):
    """Download a small square JPEG of each post's cover into thumbs/<slug>.jpg
    (only when missing) and return {slug: 'thumbs/<slug>.jpg'}."""
    import requests
    from concurrent.futures import ThreadPoolExecutor
    THUMBS.mkdir(exist_ok=True)
    have = {}
    todo = []
    for p in posts:
        if not p.get("cover_image"):
            continue
        out = THUMBS / f"{p['slug']}.jpg"
        if out.exists():
            have[p["slug"]] = f"thumbs/{out.name}"
        else:
            todo.append((p["slug"], thumb_url(p["cover_image"], size, fmt="jpg"), out))

    def get(item):
        slug, url, out = item
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            out.write_bytes(r.content)
            return slug, f"thumbs/{out.name}"
        except Exception as e:  # noqa: BLE001
            print(f"  thumb failed for {slug}: {e}")
            return slug, ""

    if todo:
        print(f"Fetching {len(todo)} thumbnails...")
        with ThreadPoolExecutor(8) as ex:
            for slug, rel in ex.map(get, todo):
                if rel:
                    have[slug] = rel
    return have


def thumb_url(cover: str, size: int = 160, fmt: str = "auto") -> str:
    """Small square crop of a Substack cover image via the substackcdn resizer."""
    if not cover:
        return ""
    transform = f"w_{size},h_{size},c_fill,f_{fmt},q_auto:good"
    if cover.startswith(_CDN_PREFIX):
        rest = cover[len(_CDN_PREFIX):]
        _, _, original = rest.partition("/")
        return f"{_CDN_PREFIX}{transform}/{original}"
    return f"{_CDN_PREFIX}{transform}/{quote(cover, safe='')}"


def assign_streams(posts, cur):
    """Return (stream_of_slug, ordered stream titles, blurbs). See the
    _streams_comment in curated/popular.json for the rules."""
    cfg = cur.get("streams", {})
    tag_map = cfg.get("tag_to_stream", [])
    cutoff_year, early_title = cfg.get("untagged_before_year", [0, "Miscellany"])
    fallback = cfg.get("untagged_fallback", "Miscellany")
    blurbs = {c["title"]: c.get("blurb", "") for c in cur.get("categories", [])}
    blurbs.update(cfg.get("stream_blurbs", {}))
    rename = cfg.get("category_rename", {})
    cat_of = {s: rename.get(c["title"], c["title"]) for c in cur.get("categories", []) for s in c["slugs"]}
    exp_of, exp_titles, lab_of = {}, [], {}
    for ex in cfg.get("experiment_streams", []):
        exp_titles.append(ex["title"])
        blurbs[ex["title"]] = ex.get("blurb", "")
        lab_of[ex["title"]] = ex.get("lab", [])
        for slug in ex["slugs"]:
            exp_of[slug] = ex["title"]
    known = {p["slug"] for p in posts}
    for slug in exp_of:
        if slug not in known:
            print(f"  streams: unknown experiment slug {slug!r}")
    stream_of = {}
    for p in posts:
        if p["slug"] in exp_of:
            stream_of[p["slug"]] = exp_of[p["slug"]]
            continue
        if p["slug"] in cat_of:
            stream_of[p["slug"]] = cat_of[p["slug"]]
            continue
        tags = {t.strip().lower() for t in p["tags"]}
        hit = next((st for tag, st in tag_map if tag.lower() in tags), None)
        if hit is None:
            hit = early_title if (not tags and p["year"] < cutoff_year) else fallback
        stream_of[p["slug"]] = hit
    counts = {}
    for st in stream_of.values():
        counts[st] = counts.get(st, 0) + 1
    first = list(cfg.get("essay_order") or cur.get("first", []))
    first += [c["title"] for c in cur.get("categories", []) if c["title"] not in first]
    first += [t for t in cfg.get("order_after_first", []) if t not in first]
    rest = sorted((t for t in counts if t not in exp_titles),
                  key=lambda t: (first.index(t) if t in first else len(first), -counts[t]))
    order = [t for t in exp_titles if t in counts] + rest
    groups = {t: ("Experiments" if t in exp_titles else "Essays and theory") for t in order}
    return stream_of, order, blurbs, groups, lab_of


def scatter(n, seed: str):
    """Deterministic 'tossed on a table' positions for n thumbnails: (left %, top %, deg)."""
    import random
    rng = random.Random(seed)
    cols = max(1, min(n, 7))
    out = []
    for i in range(n):
        col, row = i % cols, i // cols
        left = (col + 0.5) / cols * 100 + rng.uniform(-5, 5)
        top = row * 46 + rng.uniform(0, 30)
        out.append((round(left, 1), round(top, 1), round(rng.uniform(-11, 11), 1)))
    return out


def _norm(text: str) -> str:
    return re.sub(r"[\s.!?…]+$", "", (text or "").strip().lower())


def build_archive(env, posts, by_year_sorted, lab_pages, css_version):
    """Full archive: every post with subtitle, excerpt, length, tags,
    Substack likes/comments, Popular-page categories and HN badges."""
    cur = json.loads(CURATED.read_text()) if CURATED.exists() else {"categories": [], "hacker_news": []}
    stats_doc = json.loads(STATS.read_text()) if STATS.exists() else {"posts": {}}
    stats = stats_doc.get("posts", {})
    hn_by_slug = {h["slug"]: h for h in cur.get("hacker_news", [])}
    cats_by_slug = {}
    categories = []
    for cat in cur.get("categories", []):
        anchor = re.sub(r"[^a-z0-9]+", "-", cat["title"].lower()).strip("-")
        n = 0
        for slug in cat["slugs"]:
            cats_by_slug.setdefault(slug, []).append({"title": cat["title"], "anchor": anchor})
            n += 1
        categories.append({"title": cat["title"], "anchor": anchor, "n": n})
    categories.sort(key=lambda c: -c["n"])

    thumbs = fetch_thumbs(posts)
    tag_counter = {}
    enriched = []
    for p in posts:
        st = stats.get(p["slug"], {})
        cats = cats_by_slug.get(p["slug"], [])
        tags = [t.strip() for t in p["tags"] if t and t.strip()]
        for t in tags:
            tag_counter[t] = tag_counter.get(t, 0) + 1
        enriched.append({
            **p, "tags": tags,
            "likes": st.get("likes", p.get("likes", 0)),
            "comments": st.get("comments", 0),
            "hn": hn_by_slug.get(p["slug"]),
            "categories": cats,
            "category_titles": [c["title"] for c in cats],
            "read_min": max(1, round(p["wordcount"] / 230)),
            "show_excerpt": _norm(p["excerpt"]) not in ("", _norm(p["subtitle"]), _norm(p["title"])),
            "thumb": thumbs.get(p["slug"], ""),
        })
    stream_of, stream_order, stream_blurbs, stream_groups, lab_of = assign_streams(enriched, cur)
    anchors = {c["title"]: c["anchor"] for c in categories}
    lab_by_slug = {l["slug"]: l for l in lab_pages}
    streams = []
    for title in stream_order:
        items = [p for p in enriched if stream_of[p["slug"]] == title]
        items.sort(key=lambda p: (-p["likes"], -p["comments"], -p["date"].timestamp()))
        for p in items:
            p["stream"] = title
        pics = sorted((p for p in items if p["thumb"]), key=lambda p: (-p["likes"], p["date"]))[:7]
        streams.append({
            "title": title, "blurb": stream_blurbs.get(title, ""),
            "anchor": "s-" + re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-"),
            "popular_anchor": anchors.get(title),
            "posts": items, "words": sum(p["wordcount"] for p in items),
            "pics": [{**p, "pos": pos} for p, pos in zip(pics, scatter(len(pics), title))],
            "group": stream_groups[title],
            "lab": [lab_by_slug[l] for l in lab_of.get(title, []) if l in lab_by_slug],
        })
    by_year = {}
    for p in enriched:
        by_year.setdefault(p["year"], []).append(p)
    by_year_full = sorted(by_year.items(), key=lambda kv: kv[0], reverse=True)
    tag_counts = sorted(tag_counter.items(), key=lambda kv: (-kv[1], kv[0].lower()))

    fetched = stats_doc.get("fetched")
    fetched_human = (datetime.fromisoformat(fetched).strftime("%-d %B %Y")
                     if fetched else "the last build")
    (SITE / "archive.html").write_text(env.get_template("archive.html").render(
        by_year=by_year_full, total=len(enriched),
        total_words_k=sum(p["wordcount"] for p in enriched) // 1000,
        first_year=min(p["year"] for p in enriched) if enriched else "",
        tag_counts=tag_counts, categories=categories, lab_pages=lab_pages,
        streams=streams, fetched=fetched_human,
        nav_years=by_year_sorted, css_version=css_version, active_slug=None, root="",
    ))
    print(f"Built archive: {len(enriched)} posts in {len(streams)} streams, {len(tag_counts)} tags, "
          f"{len(categories)} categories, {len(lab_pages)} lab pages")


def build_popular(env, posts, by_year_sorted, css_version):
    """Curated reading list: categories from curated/popular.json, ranked by
    the Substack like counts in posts/_stats.json (see scraper/stats.py)."""
    if not CURATED.exists():
        return
    cur = json.loads(CURATED.read_text())
    stats_doc = json.loads(STATS.read_text()) if STATS.exists() else {"posts": {}}
    stats = stats_doc.get("posts", {})
    by_slug = {p["slug"]: p for p in posts}
    hn_by_slug = {h["slug"]: h for h in cur.get("hacker_news", [])}

    def enrich(slug):
        p = by_slug.get(slug)
        if p is None:
            print(f"  popular: unknown slug {slug!r}, skipped")
            return None
        st = stats.get(slug, {})
        return {**p, "likes": st.get("likes", 0), "comments": st.get("comments", 0),
                "hn": hn_by_slug.get(slug)}

    categories = []
    for cat in cur["categories"]:
        items = [x for x in (enrich(s) for s in cat["slugs"]) if x]
        items.sort(key=lambda x: (-x["likes"], -x["comments"], x["date"]))
        categories.append({
            "title": cat["title"],
            "blurb": cat.get("blurb", ""),
            "anchor": re.sub(r"[^a-z0-9]+", "-", cat["title"].lower()).strip("-"),
            "posts": items,
            "total_likes": sum(x["likes"] for x in items),
        })
    first = cur.get("first", [])
    categories.sort(key=lambda c: (first.index(c["title"]) if c["title"] in first
                                   else len(first), -c["total_likes"]))

    hn = []
    for h in cur.get("hacker_news", []):
        p = by_slug.get(h["slug"])
        if p is None:
            continue
        d = datetime.fromisoformat(h["date"])
        st = stats.get(h["slug"], {})
        hn.append({**h, "title": p["title"], "canonical_url": p["canonical_url"], "date_human": d.strftime("%-d %B %Y"),
                   "likes": st.get("likes", 0), "sub_comments": st.get("comments", 0)})
    hn.sort(key=lambda h: -h["points"])

    fetched = stats_doc.get("fetched")
    fetched_human = (datetime.fromisoformat(fetched).strftime("%-d %B %Y")
                     if fetched else "at last build")
    html = env.get_template("popular.html").render(
        categories=categories, hacker_news=hn,
        total=sum(len(c["posts"]) for c in categories), fetched=fetched_human,
        nav_years=by_year_sorted, no_sidebar=True,
        css_version=css_version, active_slug=None, root="",
    )
    (SITE / "popular.html").write_text(html)
    (SITE / "index.html").write_text(html)   # site root is the Popular page
    print(f"Built popular page: {len(categories)} categories, {len(hn)} HN posts")


def main():
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir()
    (SITE / "posts").mkdir()

    # copy static assets
    for f in STATIC.iterdir():
        shutil.copy2(f, SITE / f.name)

    # cache-busting version for the stylesheet (changes when the CSS changes)
    css_version = hashlib.md5((STATIC / "style.css").read_bytes()).hexdigest()[:8]

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

    # index: pin the lab equipment list on top, then 8 most recent as excerpts
    FEATURED_SLUG = "suggested-experiment-equipment"
    featured = next((p for p in posts if p["slug"] == FEATURED_SLUG), None)
    recent = [p for p in posts if p["slug"] != FEATURED_SLUG][:8]
    # the old chronological feed lives at home.html (unlinked for now);
    # index.html is written by build_popular below.
    index_tpl = env.get_template("index.html")
    (SITE / "home.html").write_text(index_tpl.render(
        featured=featured,
        recent=recent,
        total=len(posts),
        nav_years=by_year_sorted,
        css_version=css_version,
        active_slug=None,
        root="",
    ))

    # about
    about_tpl = env.get_template("about.html")
    (SITE / "about.html").write_text(about_tpl.render(
        nav_years=by_year_sorted,
        css_version=css_version,
        active_slug=None,
        root="",
    ))

    # lab write-ups
    lab_pages = build_lab(env, by_year_sorted, css_version)

    # full archive (needs stats, curated categories and the lab pages)
    build_archive(env, posts, by_year_sorted, lab_pages, css_version)
    if THUMBS.exists():
        shutil.copytree(THUMBS, SITE / "thumbs")

    # curated popular / by-topic page
    build_popular(env, posts, by_year_sorted, css_version)
    print(f"Built {len(lab_pages)} lab page(s)")

    # individual posts
    post_tpl = env.get_template("post.html")
    for p in posts:
        out = SITE / "posts" / f"{p['slug']}.html"
        out.write_text(post_tpl.render(
            post=p,
            nav_years=by_year_sorted,
            css_version=css_version,
            active_slug=p["slug"],
            root="../",
        ))

    print(f"Wrote {len(posts)} post pages, index, archive, about -> {SITE}")


if __name__ == "__main__":
    main()
