"""Run the frontend's pure-JS unit tests (``tests/js/*.test.mjs``) with Node.

Node is found via ``NODE_BIN``, then ``node`` on PATH, then the Windows Node
install that WSL can launch. With none of them the test is skipped, so the
Python suite still runs on a machine without Node.

Before node runs, the catalog listing (the ``/api/catalog`` body) is written to
``tests/js/.fixture/catalog.json`` (git-ignored) for the search tests. It sits
under the repo, not ``/tmp``, so Windows Node launched from WSL can read it.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from agentic_solutions.web.app import _catalog_listing
from agentic_solutions.web.registry import PATTERNS

ROOT = Path(__file__).resolve().parent.parent
WINDOWS_NODE = "/mnt/c/Program Files/nodejs/node.exe"


def _node() -> str | None:
    if os.environ.get("NODE_BIN"):
        return os.environ["NODE_BIN"]
    if found := shutil.which("node"):
        return found
    return WINDOWS_NODE if Path(WINDOWS_NODE).exists() else None


def _write_catalog_fixture() -> None:
    fixture = ROOT / "tests" / "js" / ".fixture" / "catalog.json"
    fixture.parent.mkdir(exist_ok=True)
    fixture.write_text(json.dumps(_catalog_listing(PATTERNS), indent=1), encoding="utf-8")


def test_js_unit_tests_pass():
    node = _node()
    if node is None:
        pytest.skip("no Node.js found (set NODE_BIN)")
    version = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
    major = int(version.lstrip("v").split(".")[0]) if version.startswith("v") else 0
    if major < 21:
        pytest.skip(f"Node {version or '?'} is too old: the test-file glob needs Node 21+")
    _write_catalog_fixture()
    # A relative glob: Windows Node started from WSL resolves it against the WSL
    # cwd. (Node 22+ reads a bare directory argument as a file, so name the files.)
    # TAP output gives stable "# pass N" / "# fail N" summary lines to check.
    result = subprocess.run([node, "--test", "--test-reporter=tap", "tests/js/*.test.mjs"], cwd=ROOT,
                            capture_output=True, text=True, timeout=120)
    output = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert result.returncode == 0, output
    assert "# fail 0" in result.stdout and "# pass 0" not in result.stdout, output
