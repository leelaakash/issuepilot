"""
Shared state object flowing through the entire LangGraph pipeline.
Every agent reads from and writes to this TypedDict.
"""
from typing import TypedDict, Optional, List
from enum import Enum


class AgentStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    SUCCESS   = "success"
    FAILED    = "failed"
    RETRYING  = "retrying"


class TestResult(TypedDict):
    passed:   bool
    output:   str
    errors:   str
    retries:  int


class AgentState(TypedDict):
    # ── Input ──────────────────────────────────────────────────────────────
    issue_number:     int
    issue_title:      str
    issue_body:       str
    repo_name:        str        # e.g. "owner/repo"
    repo_local_path:  str        # cloned repo on disk

    # ── Code Reader output ─────────────────────────────────────────────────
    relevant_files:   List[str]  # file paths
    code_context:     str        # concatenated file contents

    # ── Planner output ─────────────────────────────────────────────────────
    plan:             str        # step-by-step fix plan
    affected_files:   List[str]  # files the coder should touch

    # ── Code Writer output ──────────────────────────────────────────────────
    patch:            str        # unified diff OR new file contents
    patched_files:    List[dict] # [{path, content}, ...]

    # ── Test Writer output ──────────────────────────────────────────────────
    test_code:        str        # pytest file content
    test_file_path:   str

    # ── Sandbox / test runner output ────────────────────────────────────────
    test_result:      TestResult

    # ── PR Opener output ────────────────────────────────────────────────────
    branch_name:      str
    pr_url:           str
    pr_number:        int

    # ── Orchestration metadata ──────────────────────────────────────────────
    current_agent:    str
    retry_count:      int
    max_retries:      int
    errors:           List[str]
    status:           AgentStatus
    messages:         List[dict]  # full conversation log for audit
