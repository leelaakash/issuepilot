"""
Agent 3 — Code Writer
Responsibility: Implement the plan by generating complete, corrected file contents.
Produces patched_files: [{path, content}, ...] written to disk.
"""
import json
import logging
import os
import re
from core.state  import AgentState, AgentStatus
from core.llm    import chat

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """
You are an expert software engineer implementing a bug fix or feature.

You will receive:
1. A GitHub issue
2. An implementation plan
3. The current content of each file that needs changing

For EACH file that needs to change, return the COMPLETE new file content.

Respond ONLY with a JSON array like this:
[
  {
    "path": "relative/path/to/file.py",
    "content": "... complete new file content here ..."
  }
]

Rules:
- Return COMPLETE file contents, not diffs or snippets
- Preserve all existing functionality unless the plan says to remove it
- Follow the coding style of the existing code
- Add clear, concise comments for non-obvious changes
- Do NOT wrap in markdown fences — return raw JSON only
"""


def _load_affected_files(repo_path: str, file_paths: list[str]) -> dict[str, str]:
    contents = {}
    for rel in file_paths:
        abs_path = os.path.join(repo_path, rel)
        if os.path.exists(abs_path):
            with open(abs_path, encoding="utf-8", errors="replace") as f:
                contents[rel] = f.read()
        else:
            contents[rel] = ""   # new file
    return contents


def _write_patched_files(repo_path: str, patched: list[dict]) -> None:
    for item in patched:
        abs_path = os.path.join(repo_path, item["path"])
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(item["content"])
        logger.info("Written: %s (%d chars)", item["path"], len(item["content"]))


def code_writer_agent(state: AgentState) -> AgentState:
    logger.info("▶ code_writer_agent: issue #%d", state["issue_number"])
    state["current_agent"] = "code_writer"
    state["status"]        = AgentStatus.RUNNING

    try:
        repo_path      = state["repo_local_path"]
        affected_files = state["affected_files"]
        file_contents  = _load_affected_files(repo_path, affected_files)

        # Build file snapshot section
        files_section = ""
        for path, content in file_contents.items():
            files_section += f"\n--- FILE: {path} ---\n{content}\n"

        user_prompt = f"""
GitHub Issue #{state['issue_number']}: {state['issue_title']}

Issue Body:
{state['issue_body']}

Implementation Plan:
{state['plan']}

Current File Contents:
{files_section}

Implement the plan. Return a JSON array of {{path, content}} for every file you changed.
"""
        raw = chat(system=SYSTEM_PROMPT, user=user_prompt, temperature=0.15, max_tokens=8192)

        # Strip markdown fences
        raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("```").strip()

        patched_files = json.loads(raw)

        # Validate structure
        assert isinstance(patched_files, list), "Expected a list"
        for item in patched_files:
            assert "path" in item and "content" in item, f"Bad item: {item}"

        # Write to disk
        _write_patched_files(repo_path, patched_files)

        # Build a human-readable patch summary
        patch_summary = "\n".join(
            f"  • {item['path']} ({len(item['content'])} chars)" for item in patched_files
        )

        state["patched_files"] = patched_files
        state["patch"]         = patch_summary
        state["status"]        = AgentStatus.SUCCESS

        state["messages"].append({
            "agent":   "code_writer",
            "summary": f"Patched {len(patched_files)} file(s)",
            "files":   [p["path"] for p in patched_files],
        })

        logger.info("Code writer patched %d files", len(patched_files))

    except (json.JSONDecodeError, AssertionError) as exc:
        logger.error("Code writer parse error: %s", exc)
        state["errors"].append(f"code_writer parse: {exc}")
        state["status"] = AgentStatus.FAILED

    except Exception as exc:
        logger.exception("code_writer_agent failed")
        state["errors"].append(f"code_writer: {exc}")
        state["status"] = AgentStatus.FAILED

    return state
