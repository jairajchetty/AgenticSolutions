import subprocess
import sys

from langchain_core.messages import AIMessage

from agentic_solutions.common.messages import text_of
from agentic_solutions.web import serialize


def test_text_of_joins_content_blocks_and_is_reexported():
    assert text_of(AIMessage([{"type": "text", "text": "a"}, "skip", {"type": "text", "text": "b"}])) == "ab"
    assert serialize.text_of is text_of


def test_cli_agents_do_not_import_the_web_package():
    code = ("import sys, agentic_solutions.agents.chat_agent.__main__, "
            "agentic_solutions.agents.interrupt_chat_agent.__main__; "
            "print([m for m in sys.modules if m.startswith('agentic_solutions.web')])")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"
