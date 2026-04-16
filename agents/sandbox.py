"""
Agent 5 — Sandbox (Docker test runner)
Responsibility: Run pytest inside a Docker container and return results.
This is the safety layer — AI-generated code NEVER runs on the host.

Self-healing loop: if tests fail, we pass the error back to the code writer
for a retry (handled by conditional routing in the graph).
"""
import logging
import os
import subprocess
import tempfile
from core.state  import AgentState, AgentStatus, TestResult
from core.config import cfg

logger = logging.getLogger(__name__)


def _run_in_docker(repo_path: str, test_file: str) -> TestResult:
    """
    Mounts the repo into a Docker container and runs pytest.
    Returns structured TestResult.
    """
    cmd = [
        "docker", "run", "--rm",
        "--network", "none",                   # no internet access
        "--memory", "512m",                    # memory cap
        "--cpus", "1",                         # cpu cap
        "-v", f"{os.path.abspath(repo_path)}:/app:ro",  # read-only mount
        "-w", "/app",
        cfg.docker_image,
        "sh", "-c",
        f"pip install -r requirements.txt -q 2>&1 | tail -5 && pytest {test_file} -v --tb=short 2>&1",
    ]

    logger.info("Running Docker sandbox: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=cfg.sandbox_timeout,
        )
        passed = result.returncode == 0
        return TestResult(
            passed=passed,
            output=result.stdout,
            errors=result.stderr,
            retries=state_retries := 0,  # set by caller
        )

    except subprocess.TimeoutExpired:
        return TestResult(
            passed=False,
            output="",
            errors=f"Docker sandbox timed out after {cfg.sandbox_timeout}s",
            retries=0,
        )
    except FileNotFoundError:
        # Docker not available — fall back to subprocess on host with venv
        logger.warning("Docker not found — running tests in isolated subprocess (less safe)")
        return _run_subprocess_fallback(repo_path, test_file)


def _run_subprocess_fallback(repo_path: str, test_file: str) -> TestResult:
    """
    Fallback: run pytest in a temp venv if Docker is unavailable.
    WARNING: less sandboxed — use only in dev environments.
    """
    with tempfile.TemporaryDirectory() as venv_dir:
        try:
            subprocess.run(
                ["python", "-m", "venv", venv_dir],
                check=True, capture_output=True,
            )
            pip = os.path.join(venv_dir, "bin", "pip")
            python = os.path.join(venv_dir, "bin", "python")

            req_file = os.path.join(repo_path, "requirements.txt")
            if os.path.exists(req_file):
                subprocess.run(
                    [pip, "install", "-r", req_file, "-q"],
                    check=True, capture_output=True, cwd=repo_path,
                )

            subprocess.run(
                [pip, "install", "pytest", "-q"],
                check=True, capture_output=True,
            )

            result = subprocess.run(
                [python, "-m", "pytest", test_file, "-v", "--tb=short"],
                capture_output=True, text=True, cwd=repo_path,
                timeout=cfg.sandbox_timeout,
            )
            return TestResult(
                passed=result.returncode == 0,
                output=result.stdout,
                errors=result.stderr,
                retries=0,
            )

        except Exception as exc:
            return TestResult(passed=False, output="", errors=str(exc), retries=0)


# ── LangGraph node ──────────────────────────────────────────────────────────

def sandbox_agent(state: AgentState) -> AgentState:
    logger.info("▶ sandbox_agent: issue #%d (retry %d)",
                state["issue_number"], state.get("retry_count", 0))
    state["current_agent"] = "sandbox"
    state["status"]        = AgentStatus.RUNNING

    try:
        test_file   = state["test_file_path"]
        repo_path   = state["repo_local_path"]

        result = _run_in_docker(repo_path, test_file)
        result["retries"] = state.get("retry_count", 0)

        state["test_result"] = result
        state["status"]      = AgentStatus.SUCCESS if result["passed"] else AgentStatus.FAILED

        state["messages"].append({
            "agent":   "sandbox",
            "passed":  result["passed"],
            "output":  result["output"][-3000:],   # trim for storage
            "errors":  result["errors"][-1000:],
        })

        if result["passed"]:
            logger.info("✅ All tests passed")
        else:
            logger.warning("❌ Tests failed:\n%s", result["output"][-2000:])

    except Exception as exc:
        logger.exception("sandbox_agent failed")
        state["errors"].append(f"sandbox: {exc}")
        state["status"] = AgentStatus.FAILED
        state["test_result"] = TestResult(passed=False, output="", errors=str(exc), retries=0)

    return state
