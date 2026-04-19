"""
CLI entry-point
===============
Usage:
  python main.py --repo owner/repo --issue 42
  python main.py --repo owner/repo --issue 42 --dry-run
  python main.py --server   (start FastAPI dashboard)
"""
import argparse
import json
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("agent.log"),
    ],
)
logger = logging.getLogger(__name__)


def run_agent(repo_name: str, issue_number: int, dry_run: bool = False) -> None:
    from core.config        import cfg
    from core.orchestrator  import run_pipeline
    from github.github_utils import fetch_issue_and_clone

    logger.info("═" * 60)
    logger.info("  GitHub AI Agent")
    logger.info("  Repo:  %s", repo_name)
    logger.info("  Issue: #%d", issue_number)
    logger.info("  Model: %s", cfg.openai_model)
    logger.info("  Dry Run: %s", dry_run)
    logger.info("═" * 60)

    if not cfg.github_token:
        logger.error("GITHUB_TOKEN not set")
        sys.exit(1)

    if not cfg.openai_api_key:
        logger.error("OPENAI_API_KEY not set")
        sys.exit(1)

    # Fetch issue + clone repo
    initial_state = fetch_issue_and_clone(repo_name, issue_number)

    if dry_run:
        logger.info("[DRY RUN] State initialized — skipping pipeline execution")
        logger.info("Issue: %s", initial_state["issue_title"])
        logger.info("Cloned to: %s", initial_state["repo_local_path"])
        return

    # Run the full LangGraph pipeline
    final_state = run_pipeline(initial_state)

    # Print summary
    print("\n" + "═" * 60)
    print("  PIPELINE COMPLETE")
    print("═" * 60)
    print(f"  Status:      {final_state['status'].value}")
    print(f"  PR URL:      {final_state.get('pr_url', 'N/A')}")
    print(f"  Retries:     {final_state.get('retry_count', 0)}")
    print(f"  Files fixed: {len(final_state.get('patched_files', []))}")

    if final_state.get("errors"):
        print(f"  Errors:      {final_state['errors']}")

    print("\n  Agent log:")
    for m in final_state.get("messages", []):
        agent   = m.get("agent", "?")
        summary = m.get("summary", m.get("event", str(m)))
        print(f"    [{agent}] {summary}")

    print("═" * 60 + "\n")

    # Save audit trail
    with open(f"audit_issue_{issue_number}.json", "w") as f:
        # state has non-serialisable enums — coerce
        audit = {
            k: v if not hasattr(v, "value") else v.value
            for k, v in final_state.items()
            if k not in ("patched_files",)   # too large for quick audit
        }
        json.dump(audit, f, indent=2, default=str)
    logger.info("Audit trail saved to audit_issue_%d.json", issue_number)


def start_server() -> None:
    import uvicorn
    uvicorn.run("dashboard.api:app", host="0.0.0.0", port=8000, reload=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="GitHub AI Agent")
    parser.add_argument("--repo",    help="GitHub repo (owner/repo)")
    parser.add_argument("--issue",   type=int, help="Issue number")
    parser.add_argument("--dry-run", action="store_true", help="Init only, no LLM calls")
    parser.add_argument("--server",  action="store_true", help="Start FastAPI dashboard")

    args = parser.parse_args()

    if args.server:
        start_server()
    elif args.repo and args.issue:
        run_agent(args.repo, args.issue, dry_run=args.dry_run)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
