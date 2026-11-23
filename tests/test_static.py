import re
from pathlib import Path
STATIC = Path("src/agentic_solutions/web/static")

def test_scripts_only_from_allowed_cdns_with_pinned_versions():
    html = (STATIC / "index.html").read_text()
    for src in re.findall(r'<script[^>]+src="([^"]+)"', html):
        if src.startswith("http"):
            assert src.startswith(("https://cdnjs.cloudflare.com/", "https://cdn.jsdelivr.net/npm/")), src
            assert re.search(r"@?\d+\.\d+\.\d+", src), src

def test_innerhtml_only_in_guide_and_sanitized():                # Review Focus 5
    for js in STATIC.glob("*.js"):
        text = js.read_text()
        if js.name == "guide.js":
            assert "DOMPurify.sanitize" in text
        else:
            assert "innerHTML" not in text, js.name

def test_catalog_and_guide_build_links_with_create_element():   # Catalog spec §9
    catalog_js = (STATIC / "catalog.js").read_text()
    guide_js = (STATIC / "guide.js").read_text()
    assert 'document.createElement("a")' in guide_js
    # catalog.js builds every element through make(tag), a thin wrapper over
    # document.createElement, so its links are make("a", ...).
    assert "document.createElement(tag)" in catalog_js and 'make("a"' in catalog_js
    assert "innerHTML" not in catalog_js
    # guide.js: exactly one innerHTML assignment, and it is the sanitized one.
    assert guide_js.count(".innerHTML") == 1
    assert ".innerHTML = markdownToSafeHtml(" in guide_js

def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200 and 'id="trace"' in r.text and 'id="console"' in r.text and 'id="guide"' in r.text


def test_fonts_only_from_google():
    html = (STATIC / "index.html").read_text()
    hrefs = re.findall(r'<link[^>]*rel="stylesheet"[^>]*href="([^"]+)"', html)
    hrefs += re.findall(r'<link[^>]*href="([^"]+)"[^>]*rel="stylesheet"', html)
    for href in hrefs:
        assert href.startswith("/static/") or href.startswith("https://fonts.googleapis.com/"), href
    assert any(h.startswith("https://fonts.googleapis.com/") for h in hrefs)


def test_no_dark_scheme_override():
    assert "prefers-color-scheme" not in (STATIC / "styles.css").read_text()
