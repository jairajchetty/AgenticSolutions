import importlib, inspect, typing
from pathlib import Path
import pytest
from agentic_solutions.web.topology import graph_topology

# folder -> (nodes without __start__/__end__, edges as (src, dst) incl. __start__/__end__).
# Later tasks append their rows.
SKELETONS = {
    "react_agent": ({"ask", "agent", "tools"},
        {("__start__","ask"), ("ask","agent"), ("ask","ask"), ("ask","__end__"), ("agent","tools"), ("agent","ask"), ("tools","agent")}),
    "reflection_agent": ({"generate", "critique", "revise"},
        {("__start__","generate"), ("generate","critique"), ("critique","revise"), ("critique","__end__"), ("revise","critique")}),
    "plan_execute_agent": ({"planner", "executor", "tools", "synthesizer"},
        {("__start__","planner"), ("planner","executor"), ("executor","tools"), ("executor","executor"),
         ("executor","synthesizer"), ("tools","executor"), ("synthesizer","__end__")}),
    "search_agent": ({"propose", "score", "answer"},
        {("__start__","propose"), ("propose","score"), ("score","propose"), ("score","answer"), ("answer","__end__")}),
    "supervisor_agent": ({"supervisor", "researcher", "writer"},
        {("__start__","supervisor"), ("supervisor","researcher"), ("supervisor","writer"), ("supervisor","__end__"),
         ("researcher","supervisor"), ("writer","supervisor")}),
    "swarm_agent": ({"triage", "billing", "technical"},
        {("__start__","triage"), ("triage","billing"), ("triage","technical"), ("triage","__end__"),
         ("billing","technical"), ("billing","__end__"), ("technical","billing"), ("technical","__end__")}),
    "hierarchy_agent": ({"director", "research_lead", "writing_lead", "searcher", "analyst", "drafter", "editor"},
        {("__start__","director"), ("director","research_lead"), ("director","writing_lead"), ("director","__end__"),
         ("research_lead","searcher"), ("research_lead","analyst"), ("research_lead","director"),
         ("searcher","research_lead"), ("analyst","research_lead"),
         ("writing_lead","drafter"), ("writing_lead","editor"), ("writing_lead","director"),
         ("drafter","writing_lead"), ("editor","writing_lead")}),
    "episodic_memory_agent": ({"recall_episodes", "answer", "store_episode"},
        {("__start__","recall_episodes"), ("recall_episodes","answer"), ("answer","store_episode"), ("store_episode","__end__")}),
    "semantic_memory_agent": ({"retrieve", "grade", "answer", "rewrite_query"},
        {("__start__","retrieve"), ("retrieve","grade"), ("grade","answer"), ("grade","rewrite_query"),
         ("rewrite_query","retrieve"), ("answer","__end__")}),
    "knowledge_graph_agent": ({"extract_entities", "query_graph", "answer", "update_graph"},
        {("__start__","extract_entities"), ("extract_entities","query_graph"), ("query_graph","answer"),
         ("answer","update_graph"), ("update_graph","__end__")}),
    "routing_agent": ({"classify", "billing", "technical", "general"},
        {("__start__","classify"), ("classify","billing"), ("classify","technical"), ("classify","general"),
         ("billing","__end__"), ("technical","__end__"), ("general","__end__")}),
    "workflow_agent": ({"extract", "validate", "transform", "load", "handle_error"},
        {("__start__","extract"), ("extract","validate"), ("validate","transform"), ("validate","handle_error"),
         ("transform","load"), ("load","__end__"), ("handle_error","__end__")}),
    "event_driven_agent": ({"receive_event", "handle_order", "handle_refund", "ignore", "emit_result"},
        {("__start__","receive_event"), ("receive_event","handle_order"), ("receive_event","handle_refund"),
         ("receive_event","ignore"), ("handle_order","emit_result"), ("handle_refund","emit_result"),
         ("ignore","__end__"), ("emit_result","__end__")}),
    "autonomous_agent": ({"set_goal", "plan", "act", "observe", "check_goal", "report"},
        {("__start__","set_goal"), ("set_goal","plan"), ("plan","act"), ("act","observe"), ("observe","check_goal"),
         ("check_goal","plan"), ("check_goal","report"), ("report","__end__")}),
    "audit_agent": ({"act", "record", "summarize"},
        {("__start__","act"), ("act","record"), ("record","act"), ("record","summarize"), ("summarize","__end__")}),
    "review_agent": ({"draft", "review", "approve"},
        {("__start__","draft"), ("draft","review"), ("review","draft"), ("review","approve"), ("approve","__end__")}),
}

AGENTS_DIR = Path(__file__).resolve().parents[1] / "src" / "agentic_solutions" / "agents"


@pytest.mark.parametrize("folder", sorted(SKELETONS))
def test_skeleton_topology_matches_spec(folder):
    mod = importlib.import_module(f"agentic_solutions.agents.{folder}.graph")
    t = graph_topology(mod.build_skeleton())
    nodes = {n["id"] for n in t["nodes"]} - {"__start__", "__end__"}
    edges = {(e["source"], e["target"]) for e in t["edges"]}
    assert (nodes, edges) == SKELETONS[folder]


@pytest.mark.parametrize("folder", sorted(SKELETONS))
def test_skeleton_exports_only_build_skeleton_and_routers_are_literal(folder):
    mod = importlib.import_module(f"agentic_solutions.agents.{folder}.graph")
    assert not hasattr(mod, "graph")
    for name, fn in inspect.getmembers(mod, inspect.isfunction):
        if name.startswith("route_"):
            assert typing.get_origin(typing.get_type_hints(fn)["return"]) is typing.Literal, name


@pytest.mark.parametrize("folder", sorted(SKELETONS))
def test_skeleton_has_no_main_module(folder):
    assert not (AGENTS_DIR / folder / "__main__.py").exists()
