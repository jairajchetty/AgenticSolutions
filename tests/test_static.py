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
    assert r.status_code == 200 and 'id="trace"' in r.text and 'id="console"' in r.text and 'id="purpose"' in r.text and 'id="guide-rest"' in r.text


def test_fonts_only_from_google():
    html = (STATIC / "index.html").read_text()
    hrefs = re.findall(r'<link[^>]*rel="stylesheet"[^>]*href="([^"]+)"', html)
    hrefs += re.findall(r'<link[^>]*href="([^"]+)"[^>]*rel="stylesheet"', html)
    for href in hrefs:
        assert href.startswith("/static/") or href.startswith("https://fonts.googleapis.com/"), href
    assert any(h.startswith("https://fonts.googleapis.com/") for h in hrefs)


def test_no_dark_scheme_override():
    assert "prefers-color-scheme" not in (STATIC / "styles.css").read_text()


def test_no_personal_contact_strings_in_served_files():          # Blueprint spec §5
    # Separators are allowed between phone digit groups so spaced, dashed or
    # dotted numbers match, but unrelated digits elsewhere in a file do not
    # (stripping every non-digit from a whole file would concatenate them).
    phone = re.compile(rb"(?:\+27|(?<![\d.])0)\D{0,2}[6-8]\d\D{0,3}\d{3}\D{0,3}\d{4}(?!\d)")
    files = [p for p in STATIC.rglob("*") if p.is_file()]
    assert files
    for path in files:
        data = path.read_bytes()
        assert b"@".join([b"jairajchetty", b"gmail.com"]) not in data, path
        assert phone.search(data) is None, path
        assert b"+27" not in data, path


def test_noscript_contact_line_is_not_inside_a_hidden_element():  # Blueprint spec §5, §9.1
    # Without JS nothing un-hides a [hidden] ancestor, so the fallback address
    # must sit outside every element carrying the hidden attribute.
    from html.parser import HTMLParser

    void = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    class Finder(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack = []  # (tag, hidden) for each open element
            self.found = []  # (text, inside_hidden) for each <noscript>

        def handle_starttag(self, tag, attrs):
            if tag in void:
                return
            self.stack.append((tag, any(name == "hidden" for name, _ in attrs)))
            if tag == "noscript":
                self.found.append(["", any(h for _, h in self.stack)])

        def handle_endtag(self, tag):
            while self.stack:
                if self.stack.pop()[0] == tag:
                    break

        def handle_data(self, data):
            if any(t == "noscript" for t, _ in self.stack):
                self.found[-1][0] += data

    finder = Finder()
    finder.feed((STATIC / "index.html").read_text())
    lines = [hidden for text, hidden in finder.found if "at gmail dot com" in text]
    assert lines, "no <noscript> fallback address"
    assert not any(lines), "the <noscript> address is inside a [hidden] element"
