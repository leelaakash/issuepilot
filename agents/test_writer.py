"""
Agent 4 — Test Writer
Responsibility: Write pytest tests that validate the fix.
Tests are written to the repo so the sandbox can execute them.
"""
import json
import logging
import os
import re
from core.state import AgentState, AgentStatus
from core.llm   import chat

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """
You are a senior QA engineer writing pytest tests to validate a bug fix or feature.

You will receive:
- The original GitHub issue
- The implementation plan
- The patched file contents

Write a pytest test file that:
1. Tests the specific fix / feature described in the issue
2. Includes both happy-path and edge-case tests
3. Uses clear test names that describe the behaviour (test_<behaviour>)
4. Mocks external calls (network, filesystem, DB) where needed
5. Is self-contained — it can be dropped into the repo root and run

Respond with a JSON object:
{
  "filename": "tests/test_fix_<issue_number>.py",
  "content": "... complete pytest file content ..."
}

No markdown fences, raw JSON only.
"""


def test_writer_agent(state: AgentState) -> AgentState:
    logger.info("▶ test_writer_agent: issue #%d", state["issue_number"])
    state["current_agent"] = "test_writer"
    state["status"]        = AgentStatus.RUNNING

    try:
        # Build patched files section for context
        patched_section = ""
        for item in state.get("patched_files", []):
            patched_section += f"\n--- {item['path']} ---\n{item['content']}\n"

        user_prompt = f"""
GitHub Issue #{state['issue_number']}: {state['issue_title']}

Issue Body:
{state['issue_body']}

Implementation Plan:
{state['plan']}

Patched Files:
{patched_section}

Write a pytest test file to validate this fix.
"""
        raw = chat(system=SYSTEM_PROMPT, user=user_prompt, temperature=0.1, max_tokens=4096)
        raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("```").strip()

        test_data = json.loads(raw)
        assert "filename" in test_data and "content" in test_data

        # Write test file to repo
        test_path = os.path.join(state["repo_local_path"], test_data["filename"])
        os.makedirs(os.path.dirname(test_path), exist_ok=True)
        with open(test_path, "w", encoding="utf-8") as f:
            f.write(test_data["content"])

        state["test_code"]      = test_data["content"]
        state["test_file_path"] = test_data["filename"]
        state["status"]         = AgentStatus.SUCCESS

        state["messages"].append({
            "agent":    "test_writer",
            "summary":  f"Wrote tests to {test_data['filename']}",
            "filename": test_data["filename"],
        })

        logger.info("Test file written: %s", test_data["filename"])

    except Exception as exc:
        logger.exception("test_writer_agent failed")
        state["errors"].append(f"test_writer: {exc}")
        state["status"] = AgentStatus.FAILED

    return state
