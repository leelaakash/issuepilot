"""
Unit + integration tests for the agent system.
Uses mocks to avoid real OpenAI/GitHub calls.
"""
import json
import pytest
from unittest.mock import MagicMock, patch, call
from core.state import AgentState, AgentStatus, TestResult


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_state(**overrides) -> AgentState:
    base = AgentState(
        issue_number    = 42,
        issue_title     = "Fix divide-by-zero in calculator",
        issue_body      = "When denominator is 0, the app crashes.",
        repo_name       = "test-owner/test-repo",
        repo_local_path = "/tmp/test-repo",
        relevant_files  = [],
        code_context    = "",
        plan            = "",
        affected_files  = [],
        patch           = "",
        patched_files   = [],
        test_code       = "",
        test_file_path  = "",
        test_result     = TestResult(passed=False, output="", errors="", retries=0),
        branch_name     = "",
        pr_url          = "",
        pr_number       = 0,
        current_agent   = "init",
        retry_count     = 0,
        max_retries     = 3,
        errors          = [],
        status          = AgentStatus.PENDING,
        messages        = [],
    )
    base.update(overrides)
    return base


# ── Planner tests ──────────────────────────────────────────────────────────────

class TestPlannerAgent:

    @patch("agents.planner.chat")
    def test_planner_parses_valid_json(self, mock_chat):
        plan_data = {
            "summary":       "Add zero-check before division",
            "root_cause":    "No guard clause for denominator == 0",
            "steps":         ["1. In calc.py line 12, add: if b == 0: raise ValueError"],
            "affected_files": ["calc.py"],
            "risk_level":    "low",
            "notes":         "",
        }
        mock_chat.return_value = json.dumps(plan_data)

        from agents.planner import planner_agent
        state  = make_state(code_context="def divide(a, b): return a / b")
        result = planner_agent(state)

        assert result["status"]  == AgentStatus.SUCCESS
        assert "Add zero-check"  in result["plan"]
        assert "calc.py"         in result["affected_files"]

    @patch("agents.planner.chat")
    def test_planner_handles_bad_json_gracefully(self, mock_chat):
        mock_chat.return_value = "Sorry I cannot help with that."

        from agents.planner import planner_agent
        state  = make_state(code_context="some code")
        result = planner_agent(state)

        # Should not raise — fall back gracefully
        assert result["status"] == AgentStatus.SUCCESS


# ── Code Reader tests ──────────────────────────────────────────────────────────

class TestCodeReaderAgent:

    @patch("agents.code_reader.chat")
    @patch("agents.code_reader._gather_repo_files")
    @patch("agents.code_reader._read_files")
    def test_reader_identifies_files(self, mock_read, mock_gather, mock_chat):
        mock_gather.return_value = ["calc.py", "utils.py", "README.md"]
        mock_chat.return_value   = '["calc.py"]'
        mock_read.return_value   = {"calc.py": "def divide(a, b): return a/b"}

        from agents.code_reader import code_reader_agent
        state  = make_state()
        result = code_reader_agent(state)

        assert result["status"]        == AgentStatus.SUCCESS
        assert "calc.py"               in result["relevant_files"]
        assert "divide"                in result["code_context"]


# ── Orchestrator routing tests ────────────────────────────────────────────────

class TestOrchestratorRouting:

    def test_route_after_sandbox_passes(self):
        from core.orchestrator import route_after_sandbox
        state = make_state(
            test_result=TestResult(passed=True, output="1 passed", errors="", retries=0),
            retry_count=0,
            max_retries=3,
        )
        assert route_after_sandbox(state) == "pr_opener"

    def test_route_after_sandbox_retries_on_failure(self):
        from core.orchestrator import route_after_sandbox
        state = make_state(
            test_result=TestResult(passed=False, output="FAILED", errors="AssertionError", retries=0),
            retry_count=0,
            max_retries=3,
        )
        result = route_after_sandbox(state)
        assert result        == "code_writer"
        assert state["retry_count"] == 1

    def test_route_after_sandbox_exhausts_retries(self):
        from core.orchestrator import route_after_sandbox
        state = make_state(
            test_result=TestResult(passed=False, output="FAILED", errors="err", retries=3),
            retry_count=3,
            max_retries=3,
        )
        assert route_after_sandbox(state) == "fail"

    def test_route_short_circuits_on_failure(self):
        from core.orchestrator import route_after_reader
        state = make_state(status=AgentStatus.FAILED)
        assert route_after_reader(state) == "fail"


# ── Sandbox tests ──────────────────────────────────────────────────────────────

class TestSandboxAgent:

    @patch("agents.sandbox._run_in_docker")
    def test_sandbox_passes_on_success(self, mock_docker):
        mock_docker.return_value = TestResult(
            passed=True, output="1 passed in 0.1s", errors="", retries=0
        )

        from agents.sandbox import sandbox_agent
        state  = make_state(
            test_file_path="tests/test_fix_42.py",
            repo_local_path="/tmp/repo",
        )
        result = sandbox_agent(state)

        assert result["status"]             == AgentStatus.SUCCESS
        assert result["test_result"]["passed"] is True

    @patch("agents.sandbox._run_in_docker")
    def test_sandbox_marks_failed_on_test_failure(self, mock_docker):
        mock_docker.return_value = TestResult(
            passed=False, output="FAILED", errors="AssertionError", retries=0
        )

        from agents.sandbox import sandbox_agent
        state  = make_state(
            test_file_path="tests/test_fix_42.py",
            repo_local_path="/tmp/repo",
        )
        result = sandbox_agent(state)

        assert result["status"]             == AgentStatus.FAILED
        assert result["test_result"]["passed"] is False
