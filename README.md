# Casual Physics Enjoyer — static mirror

A static mirror of [chillphysicsenjoyer.substack.com](https://chillphysicsenjoyer.substack.com/), styled after John Baez's [Azimuth](https://johncarlosbaez.wordpress.com/).

## Layout

- `scraper/scrape.py` — pulls every post from Substack's public API into `posts/<slug>.json`.
- `posts/` — raw scraped post JSON (data source for the build).
- `templates/` — Jinja2 templates: `base.html`, `index.html`, `post.html`, `archive.html`, `about.html`.
- `static/style.css` — typography and layout.
- `build.py` — renders templates to `docs/`.
- `docs/` — the built static site, served by GitHub Pages.

## Build

```sh
python3 -m venv .venv
.venv/bin/pip install requests jinja2 beautifulsoup4
.venv/bin/python scraper/scrape.py   # only needed when new posts appear
.venv/bin/python build.py
```

## Preview locally

```sh
cd docs && python3 -m http.server 8765
```

Then open <http://localhost:8765>.

## Deploy

GitHub Pages is configured to serve from `main` branch, `/docs` folder. Pushing to `main` updates the live site.
