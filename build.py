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
            "wordcount": data.get("wordcount") or 0,
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
    index_tpl = env.get_template("index.html")
    (SITE / "index.html").write_text(index_tpl.render(
        featured=featured,
        recent=recent,
        total=len(posts),
        nav_years=by_year_sorted,
        css_version=css_version,
        active_slug=None,
        root="",
    ))

    # archive
    arch_tpl = env.get_template("archive.html")
    (SITE / "archive.html").write_text(arch_tpl.render(
        by_year=by_year_sorted,
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
