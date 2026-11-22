"""Run the frontend's pure-JS unit tests (``tests/js/*.test.mjs``) with Node.

Node is found via ``NODE_BIN``, then ``node`` on PATH, then the Windows Node
install that WSL can launch. With none of them the test is skipped, so the
Python suite still runs on a machine without Node.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WINDOWS_NODE = "/mnt/c/Program Files/nodejs/node.exe"


def _node() -> str | None:
    if os.environ.get("NODE_BIN"):
        return os.environ["NODE_BIN"]
    if found := shutil.which("node"):
        return found
    return WINDOWS_NODE if Path(WINDOWS_NODE).exists() else None


def test_js_unit_tests_pass():
    node = _node()
    if node is None:
        pytest.skip("no Node.js found (set NODE_BIN)")
    # A relative glob: Windows Node started from WSL resolves it against the WSL
    # cwd. (Node 22+ reads a bare directory argument as a file, so name the files.)
    # TAP output gives stable "# pass N" / "# fail N" summary lines to check.
    result = subprocess.run([node, "--test", "--test-reporter=tap", "tests/js/*.test.mjs"], cwd=ROOT,
                            capture_output=True, text=True, timeout=120)
    output = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert result.returncode == 0, output
    assert "# fail 0" in result.stdout and "# pass 0" not in result.stdout, output
