"""
GitHub utilities: fetch issues, clone repos, manage branches.
"""
import logging
import os
import subprocess
from github import Github
from core.config import cfg
from core.state  import AgentState, AgentStatus

logger = logging.getLogger(__name__)


def fetch_issue_and_clone(repo_name: str, issue_number: int) -> AgentState:
    """
    Entry-point helper: fetch GitHub issue metadata + clone repo locally.
    Returns a fully-initialized AgentState ready for the graph.
    """
    gh    = Github(cfg.github_token)
    repo  = gh.get_repo(repo_name)
    issue = repo.get_issue(issue_number)

    logger.info("Fetched issue #%d: %s", issue_number, issue.title)

    # Clone repo
    workspace = os.path.join(cfg.workspace_dir, f"{repo_name.replace('/', '_')}_{issue_number}")
    os.makedirs(workspace, exist_ok=True)

    clone_url = f"https://{cfg.github_token}@github.com/{repo_name}.git"
    clone_dir = os.path.join(workspace, "repo")

    if not os.path.exists(clone_dir):
        logger.info("Cloning %s → %s", repo_name, clone_dir)
        result = subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, clone_dir],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Clone failed: {result.stderr}")
    else:
        logger.info("Repo already cloned at %s, pulling latest", clone_dir)
        subprocess.run(["git", "pull"], cwd=clone_dir, capture_output=True)

    return AgentState(
        issue_number    = issue_number,
        issue_title     = issue.title,
        issue_body      = issue.body or "",
        repo_name       = repo_name,
        repo_local_path = clone_dir,
        relevant_files  = [],
        code_context    = "",
        plan            = "",
        affected_files  = [],
        patch           = "",
        patched_files   = [],
        test_code       = "",
        test_file_path  = "",
        test_result     = {"passed": False, "output": "", "errors": "", "retries": 0},
        branch_name     = "",
        pr_url          = "",
        pr_number       = 0,
        current_agent   = "init",
        retry_count     = 0,
        max_retries     = cfg.max_retries,
        errors          = [],
        status          = AgentStatus.PENDING,
        messages        = [],
    )
