"""Run with: python -m agentic_solutions.agents.qa_agent "your question" """
import sys

from agentic_solutions.agents.qa_agent.graph import graph


def main() -> None:
    question = " ".join(sys.argv[1:]) or input("Question: ")
    result = graph.invoke({"messages": [("user", question)]})
    print(result["messages"][-1].content)


if __name__ == "__main__":
    main()
