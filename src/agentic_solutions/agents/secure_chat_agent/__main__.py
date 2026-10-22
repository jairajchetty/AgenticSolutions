"""Run the guarded chat agent:  python -m agentic_solutions.agents.secure_chat_agent

Type a question and press Enter. Type "stop" to quit.
"""
from agentic_solutions.agents.chat_agent.__main__ import CONFIG, text_of
from agentic_solutions.agents.chat_agent.graph import STOP_WORD
from agentic_solutions.agents.secure_chat_agent.graph import build_graph


def main() -> None:
    print("Loading the embedding model and threat library...")
    graph = build_graph()  # startup: model loaded, library embedded, once
    print(f'Ready. Ask me anything. Type "{STOP_WORD}" to quit.')

    # stream_mode="updates" yields {node_name: state_update} as each node ends.
    for update in graph.stream({"messages": []}, CONFIG, stream_mode="updates"):
        if "guard" in update and update["guard"]["threat"]:
            # Shown for learning purposes; a real app would log this instead.
            print(f"\n[guard] threat detected: {update['guard']['threat']}")
        if "refuse" in update:
            print(f"\nClaude: {update['refuse']['refusal']}")
        if "answer" in update:
            print(f"\nClaude: {text_of(update['answer']['messages'][-1])}")

    print("\nGoodbye!")


if __name__ == "__main__":
    main()
