from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage
from pydantic import BaseModel
from agentic_solutions.web.serialize import message_to_dict, text_of, to_jsonable

def test_human_and_ai_messages():
    assert message_to_dict(HumanMessage("hi")) == {"role": "user", "content": "hi"}
    ai = AIMessage("", tool_calls=[{"name": "calculator", "args": {"expression": "2+2"}, "id": "c1"}])
    assert message_to_dict(ai) == {"role": "assistant", "content": "",
        "tool_calls": [{"name": "calculator", "args": {"expression": "2+2"}, "id": "c1"}]}

def test_tool_message_and_remove_message():
    assert message_to_dict(ToolMessage("4", tool_call_id="c1", name="calculator")) == {
        "role": "tool", "content": "4", "name": "calculator"}
    assert message_to_dict(RemoveMessage(id="m1")) == {"role": "remove", "id": "m1"}

def test_tuple_message_from_ask_node():
    assert to_jsonable({"messages": [("user", "hi")]}) == {"messages": [{"role": "user", "content": "hi"}]}

def test_content_blocks_are_flattened_to_text():
    assert text_of(AIMessage([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}])) == "ab"

def test_long_strings_are_truncated_for_display():
    out = to_jsonable({"x": "a" * 5000})
    assert len(out["x"]) == 4097 and out["x"].endswith("…")

def test_pydantic_and_unknown_objects():
    class P(BaseModel):
        score: int
    assert to_jsonable(P(score=3)) == {"score": 3}
    assert isinstance(to_jsonable(object()), str)
