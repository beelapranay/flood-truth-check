"""FastAPI backend for the Flood Claim Truth-Check Agent UI.

Serves the static frontend and a small JSON API to kick off pipeline runs,
poll their status, and fetch past results — so the agent can be run
repeatedly from a browser instead of the CLI.
"""
import json
import os
import threading
import time
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from src.pipeline import run_pipeline
from src.mireye_client import MireyeCreditsExhausted

app = FastAPI(title="Flood Claim Truth-Check Agent")

RUNS_DIR = "output/runs"
os.makedirs(RUNS_DIR, exist_ok=True)

# In-memory job store: run_id -> job dict. Mirrored to disk on completion
# so run history survives a server restart.
jobs = {}
jobs_lock = threading.Lock()


def _load_persisted_runs():
    if not os.path.isdir(RUNS_DIR):
        return
    for fname in sorted(os.listdir(RUNS_DIR)):
        if not fname.endswith(".json"):
            continue
        run_id = fname[:-5]
        try:
            with open(os.path.join(RUNS_DIR, fname)) as f:
                data = json.load(f)
            jobs[run_id] = data
        except (json.JSONDecodeError, OSError):
            continue


_load_persisted_runs()


def _execute_run(run_id, year_from, limit):
    def progress(msg):
        with jobs_lock:
            jobs[run_id]["log"].append(msg)

    try:
        result = run_pipeline(year_from=year_from, limit=limit, progress=progress)
        with jobs_lock:
            jobs[run_id].update({
                "status": "done",
                "finished_at": time.time(),
                "total_scanned": result["total_scanned"],
                "unique_locations": result["unique_locations"],
                "flagged_count": result["flagged_count"],
                "elapsed_seconds": result["elapsed_seconds"],
                "scored_claims": result["scored_claims"],
                "claims_by_id": result["claims_by_id"],
                "credits_exhausted": result["credits_exhausted"],
            })
    except MireyeCreditsExhausted:
        with jobs_lock:
            jobs[run_id].update({
                "status": "error",
                "error": "Mireye API credits have been exhausted.",
                "credits_exhausted": True,
                "finished_at": time.time(),
            })
    except Exception as e:
        with jobs_lock:
            jobs[run_id].update({"status": "error", "error": str(e), "finished_at": time.time()})

    with jobs_lock:
        snapshot = dict(jobs[run_id])
    with open(os.path.join(RUNS_DIR, f"{run_id}.json"), "w") as f:
        json.dump(snapshot, f, default=str)


@app.post("/api/run")
def start_run(payload: dict):
    year_from = int(payload.get("year_from", 2023))
    limit = int(payload.get("limit", 50))
    limit = max(10, min(limit, 50))  # capped low: public deploy, credits are limited
    year_from = max(2010, min(year_from, 2026))

    run_id = str(uuid.uuid4())[:8]
    with jobs_lock:
        jobs[run_id] = {
            "id": run_id,
            "status": "running",
            "params": {"year_from": year_from, "limit": limit},
            "started_at": time.time(),
            "log": [],
        }

    thread = threading.Thread(target=_execute_run, args=(run_id, year_from, limit), daemon=True)
    thread.start()
    return {"run_id": run_id}


@app.get("/api/runs")
def list_runs():
    with jobs_lock:
        items = [
            {
                "id": j["id"],
                "status": j["status"],
                "params": j["params"],
                "started_at": j["started_at"],
                "flagged_count": j.get("flagged_count"),
                "total_scanned": j.get("total_scanned"),
                "elapsed_seconds": j.get("elapsed_seconds"),
                "credits_exhausted": j.get("credits_exhausted", False),
            }
            for j in jobs.values()
        ]
    items.sort(key=lambda x: x["started_at"], reverse=True)
    return items


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    with jobs_lock:
        job = jobs.get(run_id)
        if not job:
            raise HTTPException(404, "run not found")
        return dict(job)


@app.get("/api/stats")
def stats():
    """A couple of real, precomputed stats used on the landing/hero section."""
    return {
        "missing_cert_count": 124875,
        "recent_claims_count": 137119,
        "missing_cert_pct": round(124875 / 137119 * 100, 1),
    }


app.mount("/", StaticFiles(directory="static", html=True), name="static")
