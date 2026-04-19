"""
FastAPI backend
===============
Exposes:
  POST /run          — trigger the pipeline for a repo + issue
  GET  /status/{id}  — poll job status
  WS   /ws/{id}      — stream live agent events
  GET  /jobs         — list all jobs
"""
import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.config      import cfg
from core.orchestrator import run_pipeline
from github.github_utils import fetch_issue_and_clone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


# ── In-memory job store (swap for Redis in prod) ─────────────────────────────

jobs: dict[str, dict[str, Any]] = {}

# WebSocket connections per job
ws_clients: dict[str, list[WebSocket]] = {}


# ── Models ────────────────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    repo_name:    str   # "owner/repo"
    issue_number: int


class JobStatus(BaseModel):
    job_id:      str
    status:      str
    pr_url:      str | None = None
    errors:      list[str]  = []
    messages:    list[dict] = []
    retry_count: int        = 0


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _broadcast(job_id: str, event: dict) -> None:
    """Push an event to all WebSocket clients watching this job."""
    dead = []
    for ws in ws_clients.get(job_id, []):
        try:
            await ws.send_text(json.dumps(event))
        except Exception:
            dead.append(ws)
    for ws in dead:
        ws_clients[job_id].remove(ws)


def _run_pipeline_sync(job_id: str, repo_name: str, issue_number: int) -> None:
    """
    Runs in a thread-pool thread (via BackgroundTasks / asyncio.to_thread).
    Patches each agent to emit events to the job store.
    """
    try:
        jobs[job_id]["status"] = "running"

        initial_state = fetch_issue_and_clone(repo_name, issue_number)
        final_state   = run_pipeline(initial_state)

        jobs[job_id].update({
            "status":      final_state["status"].value,
            "pr_url":      final_state.get("pr_url"),
            "errors":      final_state.get("errors", []),
            "messages":    final_state.get("messages", []),
            "retry_count": final_state.get("retry_count", 0),
            "final_state": final_state,
        })

    except Exception as exc:
        logger.exception("Pipeline job %s crashed", job_id)
        jobs[job_id].update({
            "status": "failed",
            "errors": [str(exc)],
        })


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(title="GitHub AI Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/run", response_model=JobStatus)
async def run(req: RunRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "job_id":      job_id,
        "repo_name":   req.repo_name,
        "issue_number": req.issue_number,
        "status":      "queued",
        "pr_url":      None,
        "errors":      [],
        "messages":    [],
        "retry_count": 0,
    }
    ws_clients[job_id] = []

    background_tasks.add_task(
        asyncio.to_thread,
        _run_pipeline_sync,
        job_id,
        req.repo_name,
        req.issue_number,
    )

    logger.info("Job %s queued | %s #%d", job_id, req.repo_name, req.issue_number)
    return JobStatus(job_id=job_id, status="queued")


@app.get("/status/{job_id}", response_model=JobStatus)
async def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    j = jobs[job_id]
    return JobStatus(
        job_id=job_id,
        status=j["status"],
        pr_url=j.get("pr_url"),
        errors=j.get("errors", []),
        messages=j.get("messages", []),
        retry_count=j.get("retry_count", 0),
    )


@app.get("/jobs")
async def list_jobs():
    return [
        {"job_id": k, "status": v["status"], "repo": v.get("repo_name"),
         "issue": v.get("issue_number"), "pr_url": v.get("pr_url")}
        for k, v in jobs.items()
    ]


@app.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    await websocket.accept()
    if job_id not in ws_clients:
        ws_clients[job_id] = []
    ws_clients[job_id].append(websocket)

    try:
        # Send current state immediately
        if job_id in jobs:
            await websocket.send_text(json.dumps({"type": "snapshot", "data": jobs[job_id]}))

        # Keep alive — client disconnects when done
        while True:
            await asyncio.sleep(1)
            if job_id in jobs:
                await websocket.send_text(json.dumps({
                    "type":   "update",
                    "status": jobs[job_id]["status"],
                    "messages": jobs[job_id].get("messages", []),
                    "pr_url": jobs[job_id].get("pr_url"),
                }))
                if jobs[job_id]["status"] in ("success", "failed"):
                    break

    except WebSocketDisconnect:
        pass
    finally:
        if job_id in ws_clients and websocket in ws_clients[job_id]:
            ws_clients[job_id].remove(websocket)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
