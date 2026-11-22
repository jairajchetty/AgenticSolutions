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
