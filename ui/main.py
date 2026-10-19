from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import asyncio
import json
import sqlite3
from pathlib import Path

from database import get_db, get_events, get_run, get_connection
from pipeline import run_pipeline
from models import Finding
from config import get_config
from teams_notifier import TeamsNotifier


app = FastAPI(title="SQL Review Agent Dashboard")
config = get_config()

# Serve static files
app.mount("/static", StaticFiles(directory="ui/static"), name="static")


class FindingUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    recommendation: Optional[str] = None


class DispatchRequest(BaseModel):
    run_id: int


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    with open("ui/templates/dashboard.html", "r", encoding="utf-8") as f:
        return f.read()


@app.post("/api/run")
async def start_run(deploy_date: str):
    """Start a new review run."""
    result = run_pipeline(deploy_date)
    return {
        "run_id": result.run_id,
        "deploy_date": result.deploy_date,
        "state": result.state,
        "sql_files_count": len(result.sql_files),
        "findings_count": len(result.findings),
        "error": result.error
    }


@app.get("/api/run/{run_id}")
async def get_run_info(run_id: int):
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return dict(run)


@app.get("/api/run/{run_id}/events")
async def stream_events(run_id: int):
    """Server-Sent Events stream for run events."""
    async def event_generator():
        last_event_id = 0
        while True:
            events = get_events(run_id)
            new_events = [e for e in events if e["id"] > last_event_id]
            
            for event in new_events:
                data = {
                    "id": event["id"],
                    "step": event["step"],
                    "status": event["status"],
                    "message": event["message"],
                    "timestamp": event["timestamp"]
                }
                yield f"data: {json.dumps(data)}\n\n"
                last_event_id = event["id"]
            
            # Check if run is complete
            run = get_run(run_id)
            if run and run["state"] in ("Done", "Failed"):
                yield f"data: {json.dumps({'final': True, 'state': run['state']})}\n\n"
                break
            
            await asyncio.sleep(1)
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/run/{run_id}/findings")
async def get_findings(run_id: int):
    """Get findings for a run."""
    # In a real implementation, findings would be stored in the database
    # For now, we'll return a placeholder
    with get_connection() as conn:
        # This would need a findings table - for now return empty
        pass
    return []


@app.post("/api/findings/{finding_id}/approve")
async def approve_finding(finding_id: str):
    # Update finding status in database
    # Placeholder
    return {"status": "approved", "finding_id": finding_id}


@app.post("/api/findings/{finding_id}/reject")
async def reject_finding(finding_id: str):
    return {"status": "rejected", "finding_id": finding_id}


@app.post("/api/findings/{finding_id}/edit")
async def edit_finding(finding_id: str, update: FindingUpdate):
    return {"status": "edited", "finding_id": finding_id}


@app.post("/api/run/{run_id}/dispatch")
async def dispatch_findings(run_id: int):
    """Dispatch approved findings to Teams."""
    # In a real implementation, this would fetch approved findings from DB
    # and send them via TeamsNotifier
    notifier = TeamsNotifier()
    # notifier.post(approved_findings, run_metadata)
    return {"status": "dispatched", "run_id": run_id}