# 🛩️ IssuePilot

> **Multi-Agent AI System that reads GitHub Issues and automatically opens Pull Requests with fixes.**
> Built with LangGraph · OpenAI GPT-4o · Docker Sandbox · FastAPI

---

## What It Does

```
GitHub Issue  ──►  AI Team  ──►  Tested Fix  ──►  Pull Request
```

IssuePilot spins up a pipeline of 6 specialized AI agents, each with a single responsibility:

| Agent | Responsibility |
|---|---|
| 📂 Code Reader | Finds the files most relevant to the issue |
| 🧠 Planner | Produces a step-by-step implementation plan |
| ✍️ Code Writer | Implements the fix (complete file rewrites) |
| 🧪 Test Writer | Writes pytest tests to validate the fix |
| 🐳 Sandbox | Runs tests inside Docker (safe, isolated) |
| 🚀 PR Opener | Commits to a branch and opens a GitHub PR |

If tests fail, the **self-healing loop** automatically feeds the error back to the Code Writer and retries (up to `MAX_RETRIES` times).

---

## Architecture

```
                        ┌─────────────────────────────┐
                        │   LangGraph StateGraph       │
                        │                              │
 GitHub Issue ──► [code_reader] ──► [planner] ──► [code_writer]
                                                       │
                                                  [test_writer]
                                                       │
                                                   [sandbox] ◄──────────┐
                                                       │                 │
                                               tests pass?               │
                                              yes │    │ no + retries left
                                                  │    └─────────────────┘
                                             [pr_opener]
                                                  │
                                              GitHub PR ✅
```

### Shared State

Every agent reads from and writes to a single `AgentState` TypedDict:

```python
AgentState = {
    issue_number, issue_title, issue_body,    # input
    repo_name, repo_local_path,
    relevant_files, code_context,             # code_reader output
    plan, affected_files,                     # planner output
    patch, patched_files,                     # code_writer output
    test_code, test_file_path,                # test_writer output
    test_result,                              # sandbox output
    branch_name, pr_url, pr_number,           # pr_opener output
    retry_count, max_retries, errors, status  # orchestration metadata
}
```

---

## Project Structure

```
issuepilot/
├── agents/
│   ├── code_reader.py      # Agent 1 — finds relevant files
│   ├── planner.py          # Agent 2 — creates fix plan
│   ├── code_writer.py      # Agent 3 — writes patched files
│   ├── test_writer.py      # Agent 4 — writes pytest tests
│   ├── sandbox.py          # Agent 5 — runs tests in Docker
│   └── pr_opener.py        # Agent 6 — commits + opens PR
├── core/
│   ├── state.py            # AgentState TypedDict definition
│   ├── llm.py              # OpenAI wrapper with retry/logging
│   ├── config.py           # Config from .env
│   └── orchestrator.py     # LangGraph graph + routing logic
├── github/
│   └── github_utils.py     # Issue fetcher + repo cloner
├── dashboard/
│   ├── api.py              # FastAPI backend + WebSocket
│   └── static/
│       └── index.html      # Live monitoring dashboard
├── tests/
│   └── test_agents.py      # Unit tests (mocked)
├── .github/
│   └── workflows/
│       └── ai_fix.yml      # GitHub Actions trigger
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── main.py                 # CLI entry-point
└── requirements.txt
```

---

## Quick Start

### 1. Clone & install

```bash
git clone https://github.com/YOUR_USERNAME/issuepilot.git
cd issuepilot

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in OPENAI_API_KEY, GITHUB_TOKEN, GITHUB_USERNAME
```

**GitHub token scopes required:** `repo`, `issues`, `pull_requests`
→ Create one at https://github.com/settings/tokens

### 3. Run the agent (CLI)

```bash
python main.py --repo owner/repo --issue 42
```

Options:
```
--repo      GitHub repo in owner/repo format   (required)
--issue     Issue number to fix                (required)
--dry-run   Clone repo + init state only, no LLM calls
--server    Start the FastAPI dashboard instead
```

### 4. Run the dashboard (optional UI)

```bash
python main.py --server
# API:       http://localhost:8000
# Dashboard: open dashboard/static/index.html in browser
# API Docs:  http://localhost:8000/docs
```

### 5. Run with Docker Compose (recommended for production)

```bash
# Create .env first, then:
docker-compose up --build

# Dashboard at http://localhost:3000
# API at       http://localhost:8000
```

---

## GitHub Actions Integration

Add the `ai-fix` label to any issue to auto-trigger the agent:

1. Add secrets to your repo:
   - `OPENAI_API_KEY`
   - `GITHUB_TOKEN` (Actions default token works if it has PR write access)

2. Push the workflow file (already included at `.github/workflows/ai_fix.yml`)

3. Label an issue with **`ai-fix`** → agent runs → PR appears ✅

Or trigger manually:
```
Actions → "GitHub AI Agent — Auto Fix" → Run workflow → enter issue number
```

---

## Run Tests

```bash
pytest tests/ -v
```

All tests are fully mocked — no real API calls needed.

---

## Self-Healing Loop

When tests fail, the orchestrator does **not** stop. It:

1. Appends the full test error output to `state["messages"]`
2. Increments `retry_count`
3. Routes back to `code_writer` with the error context
4. Code Writer reads the failure and produces a corrected patch
5. Tests run again in the sandbox

This repeats up to `MAX_RETRIES` (default: 3).

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | ✅ | — | Your OpenAI API key |
| `OPENAI_MODEL` | | `gpt-4o` | Model to use |
| `GITHUB_TOKEN` | ✅ | — | Personal access token |
| `GITHUB_USERNAME` | ✅ | — | Your GitHub username |
| `MAX_RETRIES` | | `3` | Max test-failure retries |
| `WORKSPACE_DIR` | | `/tmp/issuepilot-workspace` | Where repos are cloned |
| `DOCKER_IMAGE` | | `python:3.11-slim` | Sandbox Docker image |
| `SANDBOX_TIMEOUT` | | `60` | Seconds before sandbox timeout |

---

## Highlights

- Multi-agent architecture with 6 specialized agents
- LangGraph-based orchestration with conditional routing
- Self-healing retry loop for automated error correction
- Docker-based sandboxed code execution
- End-to-end GitHub automation (issue → PR)
---

## License

MIT
