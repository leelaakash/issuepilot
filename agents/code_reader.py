"""
Agent 1 — Code Reader
Responsibility: Given the issue + local repo, find the files most relevant to the fix.
"""
import os
import logging
from pathlib import Path
from core.state import AgentState, AgentStatus
from core.llm   import chat

logger = logging.getLogger(__name__)

# Extensions worth reading; skip generated / binary files
READABLE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".go", ".java", ".rs", ".cpp", ".c", ".h",
    ".yaml", ".yml", ".toml", ".json", ".env.example",
    ".md", ".txt", ".sh",
}
MAX_FILES_TO_SEND  = 40   # send at most N filenames to LLM
MAX_CONTENT_CHARS  = 60_000  # total chars of code to stuff into context


def _gather_repo_files(repo_path: str) -> list[str]:
    """Walk the repo and return all readable file paths (relative)."""
    result = []
    base = Path(repo_path)
    for p in sorted(base.rglob("*")):
        if p.is_file() and p.suffix in READABLE_EXTENSIONS:
            # Skip common noise dirs
            parts = p.parts
            if any(d in parts for d in ("__pycache__", ".git", "node_modules",
                                         ".venv", "venv", "dist", "build")):
                continue
            result.append(str(p.relative_to(base)))
    return result


def _read_files(repo_path: str, file_list: list[str]) -> dict[str, str]:
    contents = {}
    for rel_path in file_list:
        abs_path = os.path.join(repo_path, rel_path)
        try:
            with open(abs_path, encoding="utf-8", errors="replace") as f:
                contents[rel_path] = f.read()
        except Exception as e:
            logger.warning("Could not read %s: %s", rel_path, e)
    return contents


def _pick_relevant_files(issue_title: str, issue_body: str, all_files: list[str]) -> list[str]:
    """Ask the LLM which files are most likely relevant."""
    file_listing = "\n".join(f"  {i+1}. {f}" for i, f in enumerate(all_files[:MAX_FILES_TO_SEND]))

    system = (
        "You are an expert software engineer doing code triage. "
        "Given a GitHub issue and a file tree, identify which files are "
        "MOST likely to need changes or to provide context for the fix. "
        "Return ONLY a JSON array of file paths, no commentary. "
        'Example: ["src/auth.py", "tests/test_auth.py"]'
    )
    user = f"""
GitHub Issue: {issue_title}

Issue Description:
{issue_body}

Repository file tree:
{file_listing}

Return a JSON array of the most relevant file paths (max 10 files).
"""
    response = chat(system=system, user=user, temperature=0.0)

    # Parse JSON defensively
    import json, re
    match = re.search(r"\[.*?\]", response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Fallback: return first 5 files
    logger.warning("Could not parse file list from LLM response; using fallback")
    return all_files[:5]


def _build_code_context(file_contents: dict[str, str]) -> str:
    """Concatenate file contents with clear delimiters, truncating if needed."""
    parts = []
    total = 0
    for path, content in file_contents.items():
        header  = f"\n{'='*60}\nFILE: {path}\n{'='*60}\n"
        snippet = content[:MAX_CONTENT_CHARS - total - len(header)]
        parts.append(header + snippet)
        total  += len(header) + len(snippet)
        if total >= MAX_CONTENT_CHARS:
            parts.append("\n... [truncated — context limit reached]")
            break
    return "".join(parts)


# ── LangGraph node ──────────────────────────────────────────────────────────

def code_reader_agent(state: AgentState) -> AgentState:
    logger.info("▶ code_reader_agent: issue #%d", state["issue_number"])
    state["current_agent"] = "code_reader"
    state["status"]        = AgentStatus.RUNNING

    try:
        repo_path  = state["repo_local_path"]
        all_files  = _gather_repo_files(repo_path)
        logger.info("Found %d readable files in repo", len(all_files))

        relevant   = _pick_relevant_files(
            state["issue_title"],
            state["issue_body"],
            all_files,
        )
        logger.info("LLM selected %d relevant files: %s", len(relevant), relevant)

        contents   = _read_files(repo_path, relevant)
        context    = _build_code_context(contents)

        state["relevant_files"] = relevant
        state["code_context"]   = context
        state["status"]         = AgentStatus.SUCCESS

        state["messages"].append({
            "agent":   "code_reader",
            "summary": f"Identified {len(relevant)} relevant files",
            "files":   relevant,
        })

    except Exception as exc:
        logger.exception("code_reader_agent failed")
        state["errors"].append(f"code_reader: {exc}")
        state["status"] = AgentStatus.FAILED

    return state
