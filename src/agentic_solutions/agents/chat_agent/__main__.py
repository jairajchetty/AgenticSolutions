"""Run the looping chat agent:  python -m agentic_solutions.agents.chat_agent

Type a question and press Enter. Type "stop" to quit.
"""
from agentic_solutions.agents.chat_agent.graph import STOP_WORD, graph

# LangGraph aborts a run after `recursion_limit` steps (default 25) to stop
# runaway loops. One question costs two steps (ask + answer), so the default
# would end a long chat with an error after ~12 questions. A chat loop is
# *meant* to run for a while, so we raise the limit.
CONFIG = {"recursion_limit": 1000}


def text_of(message) -> str:
    """Return a message's text (Claude may reply with a list of content blocks)."""
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content if isinstance(b, dict))


def main() -> None:
    print(f'Ask me anything. Type "{STOP_WORD}" to quit.')

    # stream_mode="updates" yields one {node_name: state_update} dict each
    # time a node finishes. That lets us print each answer as soon as it is
    # ready instead of waiting for the whole graph to end.
    for update in graph.stream({"messages": []}, CONFIG, stream_mode="updates"):
        if "answer" in update:
            reply = update["answer"]["messages"][-1]
            print(f"\nClaude: {text_of(reply)}")

    print("\nGoodbye!")


if __name__ == "__main__":
    main()
