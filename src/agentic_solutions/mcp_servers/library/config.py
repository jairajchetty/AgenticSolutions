"""Where the library keeps its index and models, and how to open it."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .index import Embedder, FastEmbedder, LibraryIndex
from .text import TEXT_PATH


@dataclass(frozen=True)
class LibrarySettings:
    dir: Path = field(default_factory=lambda: Path(os.environ.get("LIBRARY_DIR") or "data/library"))
    host: str = field(default_factory=lambda: os.environ.get("LIBRARY_HOST") or "127.0.0.1")
    port: int = field(default_factory=lambda: int(os.environ.get("LIBRARY_PORT") or 8766))


def open_index(settings: LibrarySettings, embedder: Embedder | None = None) -> LibraryIndex:
    """Open the index, building it first if the text, chunking or models changed (about a minute)."""
    embedder = embedder or FastEmbedder(settings.dir / "models")
    return LibraryIndex.open(settings.dir, TEXT_PATH.read_text(encoding="utf-8"), embedder)
