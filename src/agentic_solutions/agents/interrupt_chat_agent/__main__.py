"""Run the pausing chat agent:  python -m agentic_solutions.agents.interrupt_chat_agent

Type a question and press Enter. Type "stop" to quit.

This file is the CALLER. Because the graph pauses instead of blocking, the
caller is now responsible for the waiting: it runs the graph until it pauses,
asks the human, then resumes it. A web server or UI would do the same dance.
"""
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agentic_solutions.agents.chat_agent.__main__ import text_of
from agentic_solutions.agents.interrupt_chat_agent.graph import STOP_WORD, build_graph


def main() -> None:
    # InMemorySaver keeps paused state in RAM: fine for learning, lost on exit.
    # Later lessons swap in a database-backed saver to survive restarts.
    graph = build_graph(checkpointer=InMemorySaver())

    # The thread_id picks which saved conversation to run or resume. Use a
    # different id and you get a fresh, independent chat.
    config = {"configurable": {"thread_id": "chat-1"}}

    print(f'Ask me anything. Type "{STOP_WORD}" to quit.')

    # First run starts from empty messages; every later run is a resume.
    graph_input = {"messages": []}
    while True:
        # Run until the graph pauses (at `interrupt`) or finishes. There is no
        # recursion_limit to raise here: each resume is a NEW run of only a few
        # steps, so a long chat never hits the 25-step limit (unlike agent 2).
        for update in graph.stream(graph_input, config, stream_mode="updates"):
            if "answer" in update:
                print(f"\nClaude: {text_of(update['answer']['messages'][-1])}")

        # Did it finish, or is it paused? `state.next` lists the nodes still to
        # run; it is empty once the graph has reached END.
        state = graph.get_state(config)
        if not state.next:
            break

        # Paused: the payload given to interrupt() tells us what to ask.
        prompt = state.tasks[0].interrupts[0].value
        try:
            text = input(f"\n{prompt}\nYou: ")
        except EOFError:  # Ctrl+Z / Ctrl+D: same as typing "stop"
            text = STOP_WORD

        # Resume: `interrupt()` inside the `ask` node now returns `text`.
        graph_input = Command(resume=text)

    print("\nGoodbye!")


if __name__ == "__main__":
    main()
