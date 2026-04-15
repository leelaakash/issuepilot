"""
Agent 2 — Planner
Responsibility: Given the issue + code context, produce a detailed, step-by-step plan.
"""
import json
import logging
import re
from core.state import AgentState, AgentStatus
from core.llm   import chat

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """
You are a senior software engineer creating a precise implementation plan.

Given:
- A GitHub issue describing a bug or feature
- The relevant source code

Produce a JSON object with this exact shape:
{
  "summary": "One-line description of what needs to change",
  "root_cause": "Why the bug exists / what is missing",
  "steps": [
    "1. Exactly what to do in file X",
    "2. Exactly what to do in file Y",
    ...
  ],
  "affected_files": ["path/to/file1.py", "path/to/file2.py"],
  "risk_level": "low|medium|high",
  "notes": "Any caveats or edge-cases the coder should watch for"
}

Be specific: mention function names, line numbers if known, and exact logic changes.
Return ONLY the JSON — no markdown fences, no commentary.
"""


def planner_agent(state: AgentState) -> AgentState:
    logger.info("▶ planner_agent: issue #%d", state["issue_number"])
    state["current_agent"] = "planner"
    state["status"]        = AgentStatus.RUNNING

    try:
        user_prompt = f"""
GitHub Issue #{state['issue_number']}: {state['issue_title']}

{state['issue_body']}

--- RELEVANT CODE CONTEXT ---
{state['code_context']}
"""
        raw = chat(system=SYSTEM_PROMPT, user=user_prompt, temperature=0.1)

        # Strip markdown fences if model hallucinated them
        raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("```").strip()

        plan_data = json.loads(raw)

        # Flatten steps into a human-readable plan string
        plan_text = f"Summary: {plan_data['summary']}\n\n"
        plan_text += f"Root Cause: {plan_data['root_cause']}\n\n"
        plan_text += "Steps:\n" + "\n".join(plan_data["steps"])
        if plan_data.get("notes"):
            plan_text += f"\n\nNotes: {plan_data['notes']}"

        state["plan"]           = plan_text
        state["affected_files"] = plan_data.get("affected_files", state["relevant_files"])
        state["status"]         = AgentStatus.SUCCESS

        state["messages"].append({
            "agent":        "planner",
            "summary":      plan_data["summary"],
            "root_cause":   plan_data["root_cause"],
            "steps":        plan_data["steps"],
            "risk_level":   plan_data.get("risk_level", "unknown"),
            "affected_files": state["affected_files"],
        })

        logger.info("Plan created. Affected files: %s | Risk: %s",
                    state["affected_files"], plan_data.get("risk_level"))

    except json.JSONDecodeError as exc:
        logger.error("Planner LLM returned non-JSON: %s", exc)
        # Graceful fallback: store raw text as plan
        state["plan"]           = raw if "raw" in dir() else "Plan generation failed"
        state["affected_files"] = state.get("relevant_files", [])
        state["status"]         = AgentStatus.SUCCESS   # non-fatal; coder can still proceed

    except Exception as exc:
        logger.exception("planner_agent failed")
        state["errors"].append(f"planner: {exc}")
        state["status"] = AgentStatus.FAILED

    return state
