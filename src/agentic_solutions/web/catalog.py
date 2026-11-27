"""The pattern catalog: the single source of truth for the Studio's taxonomy.

The data lives in ``catalog.yaml`` next to this module, so the owner can change
the main page without touching code. It is loaded and checked when this module
is imported: an invalid file raises ``CatalogError`` and the app never starts
with a half-built catalog.

A pattern with ``builds_on`` is composite (a card on the main page); one
without is simple (a building block). Neither that nor "live" versus "guide"
is stored: composite comes from ``builds_on``, status from the web registry.

``execution/tool-use`` is a cross-list: it has no page of its own and borrows
``cognitive/react`` (its ``crosslist_of``), including its status.
"""

from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

CATALOG_PATH = Path(__file__).with_name("catalog.yaml")


class CatalogError(ValueError):
    """The catalog file is invalid. The message names the file and the entry."""


@dataclass(frozen=True)
class CatalogPattern:
    id: str
    category: str
    name: str
    description: str
    aliases: tuple[str, ...]
    demo: str | None  # registry PatternSpec id (possibly not yet registered), else None
    crosslist_of: str | None  # route of the canonical page for cross-lists, else None
    folder: str | None  # agent folder holding explanation.md (+ skeleton); None for cross-lists
    builds_on: tuple[str, ...] = ()  # routes of the patterns this one is built from

    @property
    def route(self) -> str:
        return f"{self.category}/{self.id}"

    @property
    def composite(self) -> bool:
        return bool(self.builds_on)


@dataclass(frozen=True)
class Category:
    id: str
    name: str
    description: str
    patterns: tuple[CatalogPattern, ...]


def load_catalog(path: Path) -> tuple[Category, ...]:
    """Read and check a catalog file. Raises CatalogError naming the file and entry."""

    def fail(where: str, problem: str):
        raise CatalogError(f"{path.name}: {where}: {problem}")

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CatalogError(f"{path.name}: cannot read the catalog: {exc}") from exc

    def text(obj: dict, key: str, where: str, required: bool = True) -> str | None:
        value = obj.get(key)
        if value is None and not required:
            return None
        if not isinstance(value, str) or not value.strip():
            fail(where, f"`{key}` must be a non-empty string")
        return value.strip()

    def strings(obj: dict, key: str, where: str) -> tuple[str, ...]:
        value = obj.get(key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
            fail(where, f"`{key}` must be a list of non-empty strings")
        return tuple(v.strip() for v in value)

    if not isinstance(data, dict) or not isinstance(data.get("categories"), list) or not data["categories"]:
        fail("top level", "expected a non-empty `categories` list")

    categories, seen_ids = [], set()
    for i, raw in enumerate(data["categories"]):
        if not isinstance(raw, dict):
            fail(f"category {i + 1}", "expected a mapping")
        cid = text(raw, "id", f"category {i + 1}")
        if cid in seen_ids:
            fail(cid, "duplicate category id")
        seen_ids.add(cid)
        if not isinstance(raw.get("patterns"), list) or not raw["patterns"]:
            fail(cid, "expected a non-empty `patterns` list")
        patterns = []
        for j, rp in enumerate(raw["patterns"]):
            if not isinstance(rp, dict):
                fail(f"{cid} pattern {j + 1}", "expected a mapping")
            pid = text(rp, "id", f"{cid} pattern {j + 1}")
            where = f"{cid}/{pid}"
            patterns.append(CatalogPattern(
                id=pid, category=cid, name=text(rp, "name", where), description=text(rp, "description", where),
                aliases=strings(rp, "aliases", where), demo=text(rp, "demo", where, required=False),
                crosslist_of=text(rp, "crosslist_of", where, required=False),
                folder=text(rp, "folder", where, required=False), builds_on=strings(rp, "builds_on", where)))
        categories.append(Category(cid, text(raw, "name", cid), text(raw, "description", cid), tuple(patterns)))

    by_route: dict[str, CatalogPattern] = {}
    for k in categories:
        for pat in k.patterns:
            if pat.route in by_route:
                fail(pat.route, "duplicate pattern route")
            by_route[pat.route] = pat
    for k in categories:
        if not any(pat.composite for pat in k.patterns):
            fail(k.id, "no composite pattern (none has `builds_on`), so the main page would show an empty band")
        for pat in k.patterns:
            if (pat.folder is None) == (pat.crosslist_of is None):
                fail(pat.route, "set exactly one of `folder` and `crosslist_of`")
            if pat.crosslist_of is not None and pat.crosslist_of not in by_route:
                fail(pat.route, f"`crosslist_of` names unknown route {pat.crosslist_of!r}")
            if len(set(pat.builds_on)) != len(pat.builds_on):
                dup = next(r for r in pat.builds_on if pat.builds_on.count(r) > 1)
                fail(pat.route, f"`builds_on` lists {dup} twice")
            for r in pat.builds_on:
                if r not in by_route:
                    fail(pat.route, f"`builds_on` names unknown route {r!r} (write routes as category/id)")

    # No pattern may build on itself, directly or through others.
    state: dict[str, int] = {}  # 1 = on the current path, 2 = checked

    def visit(route: str):
        state[route] = 1
        for nxt in by_route[route].builds_on:
            if state.get(nxt) == 1:
                fail(route, f"`builds_on` forms a cycle through {nxt}")
            if nxt not in state:
                visit(nxt)
        state[route] = 2

    for route in by_route:
        if route not in state:
            visit(route)
    return tuple(categories)


CATALOG: tuple[Category, ...] = load_catalog(CATALOG_PATH)

_BY_ROUTE = {p.route: p for k in CATALOG for p in k.patterns}


def entry(route: str) -> CatalogPattern | None:
    return _BY_ROUTE.get(route)


def target(p: CatalogPattern) -> CatalogPattern:
    """The canonical page for `p`: itself, or (one hop) the pattern it cross-lists."""
    return _BY_ROUTE[p.crosslist_of] if p.crosslist_of else p


def status(p: CatalogPattern, live_ids: Collection[str]) -> Literal["live", "guide"]:
    demo = target(p).demo
    return "live" if demo is not None and demo in live_ids else "guide"


def neighbours(route: str) -> tuple[str, str]:
    """Previous and next routes within the route's own category, wrapping around."""
    category, _, _ = route.partition("/")
    routes = [p.route for k in CATALOG if k.id == category for p in k.patterns]
    i = routes.index(route)
    return routes[i - 1], routes[(i + 1) % len(routes)]
