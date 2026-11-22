from pathlib import Path
import re

AGENTS = Path("src/agentic_solutions/agents")
REQUIRED = ["What it is", "When to use it", "How this graph works", "LangGraph concepts",
            "Trade-offs", "Key code", "Try this"]

def test_every_explanation_has_required_sections():
    files = sorted(AGENTS.glob("*/explanation.md"))
    assert len(files) >= 4
    for f in files:
        assert re.findall(r"^## (.+)$", f.read_text(), re.M) == REQUIRED, f
