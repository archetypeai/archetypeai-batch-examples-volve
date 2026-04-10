#!/usr/bin/env python3
"""
Create and monitor a batch job on the Archetype AI platform.

Usage:
    python create_batch_job.py

Flow:
    1. POST /v0.5/jos/jobs          → create batch job
    2. GET  /v0.5/jos/jobs/{id}     → poll status
    3. GET  /v0.5/jos/jobs/{id}/events → view logs
"""

import json
import os
import sys
import time

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
with open(ENV_PATH) as f:
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k] = v

API_KEY = os.environ["ATAI_API_KEY"]
API_ENDPOINT = os.environ["ATAI_API_ENDPOINT"]
BASE_URL = f"{API_ENDPOINT}/v0.5"
AUTH = {"Authorization": f"Bearer {API_KEY}"}

# ---------------------------------------------------------------------------
# Job configuration
# ---------------------------------------------------------------------------
JOB_PAYLOAD = {
    "name": "higgs-batch-inference",
    "pipeline_type": "batch",
    "pipeline_key": "machine-state-job-pipeline",
    "inputs": {
        "worker.inference": [
            {"file_id": "higgs_no_label.csv"}
        ],
        "worker.n_shots": [
            {"file_id": "higgs_boson.csv", "metadata": {"class": "boson"}},
            {"file_id": "higgs_no_boson.csv", "metadata": {"class": "no_boson"}},
        ],
    },
    "parameters": {
        "worker": {
            "parallelism": 1,
            "config": {
                "batch_size": 8,
                "classifier_config": {
                    "metric": "euclidean",
                    "n_neighbors": 5,
                    "weights": "uniform",
                },
                "data_columns": [
                    "lepton_pT", "lepton_eta", "lepton_phi",
                    "missing_energy_magnitude", "missing_energy_phi",
                    "jet_1_pt", "jet_1_eta", "jet_1_phi", "jet_1_b-tag",
                    "jet_2_pt", "jet_2_eta", "jet_2_phi", "jet_2_b-tag",
                    "jet_3_pt", "jet_3_eta", "jet_3_phi", "jet_3_b-tag",
                    "jet_4_pt", "jet_4_eta", "jet_4_phi", "jet_4_b-tag",
                    "m_jj", "m_jjj", "m_lv", "m_jlv", "m_bb", "m_wbb", "m_wwbb",
                ],
                "flush_every_n_iteration": 150,
                "model_type": "omega_1_3_surface",
                "reader_config": {"step_size": 1, "window_size": 1},
                "timestamp_column": "timestamp",
            },
        }
    },
}

TERMINAL_STATUSES = {"COMPLETED", "FAILED", "CANCELLED"}


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------
def create_job(payload: dict) -> dict:
    resp = requests.post(
        f"{BASE_URL}/jos/jobs",
        headers={**AUTH, "Content-Type": "application/json"},
        json=payload,
    )
    resp.raise_for_status()
    return resp.json()


def get_job(job_id: str) -> dict:
    resp = requests.get(f"{BASE_URL}/jos/jobs/{job_id}", headers=AUTH)
    resp.raise_for_status()
    return resp.json()


def list_jobs(limit: int = 10, offset: int = 0) -> dict:
    resp = requests.get(
        f"{BASE_URL}/jos/jobs",
        headers=AUTH,
        params={"limit": limit, "offset": offset},
    )
    resp.raise_for_status()
    return resp.json()


def get_events(job_id: str, limit: int = 100) -> dict:
    resp = requests.get(
        f"{BASE_URL}/jos/jobs/{job_id}/events",
        headers=AUTH,
        params={"limit": limit},
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print(" Archetype AI Batch Job")
    print("=" * 60)
    print()

    # --- Step 1: Create job ------------------------------------------------
    print("[1/3] Creating batch job...")
    job = create_job(JOB_PAYLOAD)
    job_id = job["id"]

    print(f"      job_id:   {job_id}")
    print(f"      name:     {job['name']}")
    print(f"      pipeline: {job['pipeline_key']} v{job['pipeline_version']}")
    print(f"      status:   {job['status']}")
    print()

    # --- Step 2: Poll status -----------------------------------------------
    print("[2/3] Monitoring job status...")
    poll_interval = 5
    prev_status = None

    while True:
        job = get_job(job_id)
        status = job["status"]

        if status != prev_status:
            elapsed = ""
            if job.get("started_at") and job.get("created_at"):
                print(f"      [{time.strftime('%H:%M:%S')}] {status}")
            prev_status = status

        if status in TERMINAL_STATUSES:
            break

        time.sleep(poll_interval)

    print()

    # --- Step 3: Show events -----------------------------------------------
    print("[3/3] Job events:")
    events = get_events(job_id)

    for event in reversed(events.get("events", [])):
        level = event["level"]
        msg = event["message"]
        ts = event["created_at"][11:19]
        marker = "!!" if level == "ERROR" else "  "
        print(f"  {marker} [{ts}] {level:<5} {msg}")

    print()
    print("=" * 60)
    print(f" Job {job_id}")
    print(f" Status: {job['status']}")
    if job.get("completed_at"):
        print(f" Completed: {job['completed_at']}")
    if job.get("failed_at"):
        print(f" Failed: {job['failed_at']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
