#!/usr/bin/env python3
"""
Download batch job output artifacts from the Archetype AI platform.

Usage:
    python download_outputs.py <job_id> [output_dir]
    python download_outputs.py job_6pgect4qqc8h0sd6v3rva23y8g outputs/
"""

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


def get_outputs(job_id: str, limit: int = 50) -> list:
    """Fetch all output metadata (paginated)."""
    outputs = []
    offset = 0
    while True:
        resp = requests.get(
            f"{BASE_URL}/batch/jobs/{job_id}/outputs",
            headers=AUTH,
            params={"limit": limit, "offset": offset},
        )
        resp.raise_for_status()
        data = resp.json()
        outputs.extend(data["outputs"])
        total = data["total"]
        print(f"  Fetched {len(outputs)}/{total} output records...")
        if offset + limit >= total:
            break
        offset += limit
    return outputs


def download_file(url: str, dest: str):
    """Download a file from a presigned URL."""
    resp = requests.get(url)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        f.write(resp.content)
    return len(resp.content)


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <job_id> [output_dir]")
        sys.exit(1)

    job_id = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else f"outputs/{job_id}"
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print(" Download Batch Job Outputs")
    print("=" * 60)
    print(f"  Job:    {job_id}")
    print(f"  Saving: {output_dir}/")
    print()

    # Step 1: Fetch output metadata
    print("[1/2] Fetching output list...")
    outputs = get_outputs(job_id)
    print(f"  Total: {len(outputs)} files")
    print()

    # Step 2: Download files
    print(f"[2/2] Downloading {len(outputs)} files...")
    t0 = time.time()
    total_bytes = 0

    for i, out in enumerate(outputs):
        url = out["data"]["ref"]
        filename = out["data"]["filename"]
        dest = os.path.join(output_dir, filename)

        nbytes = download_file(url, dest)
        total_bytes += nbytes

        if (i + 1) % 50 == 0 or i == 0 or i == len(outputs) - 1:
            elapsed = time.time() - t0
            pct = (i + 1) / len(outputs) * 100
            speed = total_bytes / elapsed / 1024 / 1024 if elapsed > 0 else 0
            print(f"  [{pct:5.1f}%] {i + 1}/{len(outputs)}  {filename}  ({speed:.1f} MB/s)")

    elapsed = time.time() - t0
    print()
    print(f"  Done! {len(outputs)} files, {total_bytes / 1024 / 1024:.1f} MB in {elapsed:.1f}s")
    print(f"  Saved to: {output_dir}/")


if __name__ == "__main__":
    main()
