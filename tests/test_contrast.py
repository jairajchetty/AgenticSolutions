"""Persistent WCAG 2.x contrast check for the Blueprint tokens in styles.css."""
import re
from pathlib import Path

CSS = Path("src/agentic_solutions/web/static/styles.css").read_text()


def _root_block(css: str) -> str:
    m = re.search(r":root\s*\{(.*?)\}", css, re.S)
    assert m, "no :root block"
    return m.group(1)


TOKENS = dict(re.findall(r"(--[a-z-]+)\s*:\s*(#[0-9a-fA-F]{6})\b", _root_block(CSS)))


def _mix(a: str, pct_a: int, b: str) -> str:
    """CSS color-mix(in srgb, a pct_a%, b) for two #rrggbb colours."""
    ha, hb = a.lstrip("#"), b.lstrip("#")
    out = ""
    for i in (0, 2, 4):
        v = (int(ha[i:i + 2], 16) * pct_a + int(hb[i:i + 2], 16) * (100 - pct_a)) / 100
        out += f"{round(v):02x}"
    return "#" + out


def _derive_paper_surfaces() -> dict:
    """Resolve `--x: color-mix(in srgb, var(--a) N%, var(--b))` tokens that sit under text."""
    found = {}
    for name, a, pct, b in re.findall(
            r"(--paper-[a-z]+)\s*:\s*color-mix\(\s*in srgb\s*,\s*var\((--[a-z-]+)\)\s*(\d+)%\s*,"
            r"\s*var\((--[a-z-]+)\)\s*\)", _root_block(CSS)):
        found[name] = _mix(TOKENS[a], int(pct), TOKENS[b])
    return found


DERIVED = _derive_paper_surfaces()
TOKENS.update(DERIVED)


def _lin(c: int) -> float:
    s = c / 255
    return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4


def luminance(hex_: str) -> float:
    h = hex_.lstrip("#")
    r, g, b = (_lin(int(h[i:i + 2], 16)) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a: str, b: str) -> float:
    la, lb = luminance(TOKENS[a]), luminance(TOKENS[b])
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


PAIRS_AA = [("--ink", "--paper"), ("--muted-ink", "--paper"), ("--line", "--navy"),
            ("--paper", "--navy"), ("--ink", "--amber"), ("--signal-red", "--paper"),
            ("--amber", "--navy")]  # amber is normal-size text: node labels, legend glyph, edge labels
for _surface in ("--paper-sunk", "--paper-tint"):
    PAIRS_AA += [("--ink", _surface), ("--muted-ink", _surface)]


def test_derived_paper_surfaces_are_found():
    assert {"--paper-sunk", "--paper-tint"} <= set(DERIVED), DERIVED


def test_text_pairs_meet_aa():
    for a, b in PAIRS_AA:
        assert ratio(a, b) >= 4.5, (a, b, ratio(a, b))


def test_tokens_have_exact_values():
    expected = {"--navy": "#0f2b46", "--line": "#9cc7e8", "--paper": "#f3f6f8", "--ink": "#13202b",
                "--amber": "#e2a33b", "--signal-red": "#c2412d", "--muted-ink": "#51606d"}
    for name, value in expected.items():
        assert TOKENS[name].lower() == value, name
