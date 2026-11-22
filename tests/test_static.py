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

def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200 and 'id="trace"' in r.text and 'id="console"' in r.text and 'id="guide"' in r.text
