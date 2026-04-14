"""
LangGraph Orchestrator
======================
Wires all agents into a StateGraph with:
  - Linear flow: reader → planner → coder → tester → sandbox → pr
  - Conditional routing: retry loop on test failure (up to max_retries)
  - Failure short-circuit: any FAILED status stops the graph
  - Full audit trail in state["messages"]

Graph topology:

    [START]
       │
  [code_reader]
       │
   [planner]
       │
  [code_writer]
       │
  [test_writer]
       │
   [sandbox] ◄─────────────────────────┐
       │                               │
  ┌────┴────┐                          │
  │  pass?  │                          │
  └────┬────┘                          │
  yes  │  no                           │
       │   └─── [retry_count < max] ───┘
       │             (re-runs code_writer)
       │   └─── [retry exhausted] → FAIL
       │
  [pr_opener]
       │
    [END]
"""
import logging
from langgraph.graph import StateGraph, END

from core.state     import AgentState, AgentStatus
from agents.code_reader  import code_reader_agent
from agents.planner      import planner_agent
from agents.code_writer  import code_writer_agent
from agents.test_writer  import test_writer_agent
from agents.sandbox      import sandbox_agent
from agents.pr_opener    import pr_opener_agent

logger = logging.getLogger(__name__)


# ── Routing functions ────────────────────────────────────────────────────────

def route_after_reader(state: AgentState) -> str:
    if state["status"] == AgentStatus.FAILED:
        logger.error("code_reader failed → aborting")
        return "fail"
    return "planner"


def route_after_planner(state: AgentState) -> str:
    if state["status"] == AgentStatus.FAILED:
        return "fail"
    return "code_writer"


def route_after_coder(state: AgentState) -> str:
    if state["status"] == AgentStatus.FAILED:
        return "fail"
    return "test_writer"


def route_after_test_writer(state: AgentState) -> str:
    if state["status"] == AgentStatus.FAILED:
        return "fail"
    return "sandbox"


def route_after_sandbox(state: AgentState) -> str:
    """
    Core retry logic:
      - Tests pass → open PR
      - Tests fail + retries left → increment counter, go back to code_writer
      - Tests fail + no retries left → fail
    """
    result = state.get("test_result", {})

    if result.get("passed"):
        logger.info("Tests passed → opening PR")
        return "pr_opener"

    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)

    if retry_count < max_retries:
        state["retry_count"] = retry_count + 1
        state["status"]      = AgentStatus.RETRYING

        # Inject test failure into messages so code_writer sees it
        state["messages"].append({
            "agent":  "orchestrator",
            "event":  "retry",
            "attempt": state["retry_count"],
            "reason": f"Tests failed:\n{result.get('output', '')[-1500:]}\n{result.get('errors', '')[-500:]}",
        })

        logger.warning(
            "Tests failed — retry %d/%d → re-running code_writer",
            state["retry_count"], max_retries,
        )
        return "code_writer"   # self-healing loop

    logger.error("Tests failed after %d retries → aborting", max_retries)
    return "fail"


def route_after_pr(state: AgentState) -> str:
    if state["status"] == AgentStatus.FAILED:
        return "fail"
    return END


# ── Terminal fail node ────────────────────────────────────────────────────────

def fail_node(state: AgentState) -> AgentState:
    logger.error(
        "Pipeline FAILED at agent=%s | errors=%s",
        state.get("current_agent"), state.get("errors"),
    )
    state["status"] = AgentStatus.FAILED
    state["messages"].append({
        "agent":  "orchestrator",
        "event":  "pipeline_failed",
        "errors": state.get("errors", []),
    })
    return state


# ── Build graph ───────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    g = StateGraph(AgentState)

    # Register nodes
    g.add_node("code_reader",  code_reader_agent)
    g.add_node("planner",      planner_agent)
    g.add_node("code_writer",  code_writer_agent)
    g.add_node("test_writer",  test_writer_agent)
    g.add_node("sandbox",      sandbox_agent)
    g.add_node("pr_opener",    pr_opener_agent)
    g.add_node("fail",         fail_node)

    # Entry point
    g.set_entry_point("code_reader")

    # Conditional edges
    g.add_conditional_edges("code_reader",  route_after_reader,
                            {"planner": "planner", "fail": "fail"})

    g.add_conditional_edges("planner",      route_after_planner,
                            {"code_writer": "code_writer", "fail": "fail"})

    g.add_conditional_edges("code_writer",  route_after_coder,
                            {"test_writer": "test_writer", "fail": "fail"})

    g.add_conditional_edges("test_writer",  route_after_test_writer,
                            {"sandbox": "sandbox", "fail": "fail"})

    g.add_conditional_edges(
        "sandbox",
        route_after_sandbox,
        {
            "pr_opener":   "pr_opener",
            "code_writer": "code_writer",   # retry loop
            "fail":        "fail",
        },
    )

    g.add_conditional_edges("pr_opener",    route_after_pr,
                            {END: END, "fail": "fail"})

    g.add_edge("fail", END)

    return g.compile()


# ── Public API ────────────────────────────────────────────────────────────────

def run_pipeline(initial_state: AgentState) -> AgentState:
    """
    Compile graph and run it to completion.
    Returns the final AgentState.
    """
    graph = build_graph()

    logger.info(
        "🚀 Starting pipeline | repo=%s issue=#%d",
        initial_state["repo_name"],
        initial_state["issue_number"],
    )

    final_state = graph.invoke(initial_state)

    if final_state["status"] == AgentStatus.SUCCESS:
        logger.info("🎉 Pipeline succeeded | PR: %s", final_state.get("pr_url"))
    else:
        logger.error("💥 Pipeline failed | errors: %s", final_state.get("errors"))

    return final_state
