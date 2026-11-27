"""Shared offline test helpers, re-exported so tests can `from fakes import ...`."""
from agentic_solutions.agents.approval_agent.erp import ErpUnavailable
from test_secure_chat_graph import FakeEncoder, LIBRARY, make_guard  # noqa: F401


class UnreachableErp:
    """An ERP client for tests that only build graphs: building never connects."""

    async def call(self, tool, args):
        raise ErpUnavailable("no ERP in this test")


def no_token(claims):
    raise AssertionError("this test must not issue approval tokens")


# ---------------------------------------------------------------- library

import hashlib as _hashlib
import math as _math
import re as _re


def _tokens(text):
    return _re.findall(r"[a-z]+", text.lower())


def _token_id(token):
    return int.from_bytes(_hashlib.sha256(token.encode()).digest()[:4], "big") % (2 ** 31)


class FakeEmbedder:
    """Deterministic stand-in for FastEmbedder: no model download, exact-word matching.

    Dense vectors are a normalised bag of hashed words (384 dimensions); sparse
    vectors are word ids with term counts, so Qdrant's IDF-weighted BM25 vector
    finds exact words.
    """

    names = ("fake-dense", "fake-bm25")

    def __init__(self):
        self.dense_calls = 0
        self.loads = 0

    def load(self):
        self.loads += 1

    def _dense_one(self, text):
        v = [0.0] * 384
        for t in _tokens(text):
            v[_token_id(t) % 384] += 1.0
        norm = _math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def _sparse_one(self, text):
        counts = {}
        for t in _tokens(text):
            counts[_token_id(t)] = counts.get(_token_id(t), 0.0) + 1.0
        ids = sorted(counts)
        return ids, [counts[i] for i in ids]

    def dense(self, texts):
        self.dense_calls += 1
        return [self._dense_one(t) for t in texts]

    def sparse(self, texts):
        return [self._sparse_one(t) for t in texts]

    def dense_query(self, text):
        return self._dense_one(text)

    def sparse_query(self, text):
        return self._sparse_one(text)


def library_fixture_text():
    """Three short Books with a few words unique to each, in the committed text format."""
    words = {"I": "serpent fruit garden", "II": "pandemonium council mammon", "III": "light sphere uriel"}
    out = []
    for numeral, special in words.items():
        out.append(f"# Book {numeral}")
        for i in range(1, 41):
            extra = f" {special}" if i in (5, 6) else ""
            end = "." if i % 7 == 0 or i == 40 else ","
            out.append(f"Verse {numeral} line {i} of the fixture{extra}{end}")
    return "\n".join(out) + "\n"


class NoLibrary:
    """A library client for building graphs only: any call says the library is unavailable."""

    async def call(self, tool, args):
        return "Error: the library is unavailable."
