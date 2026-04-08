#!/usr/bin/env python3
"""
Multipart file upload to Archetype AI using presigned URLs.

Usage:
    python upload_multipart.py data/HIGGS.csv

Flow:
    1. POST /v0.5/files/uploads/initiate  -> get presigned URLs
    2. PUT each part to S3                 -> collect ETags
    3. POST /v0.5/files/uploads/{id}/complete -> finalize
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
# Helpers
# ---------------------------------------------------------------------------
def fmt_bytes(n: int) -> str:
    if n >= 1024 ** 3:
        return f"{n / 1024**3:.2f} GB"
    if n >= 1024 ** 2:
        return f"{n / 1024**2:.0f} MB"
    return f"{n / 1024:.0f} KB"


def progress_bar(current: int, total: int, width: int = 40) -> str:
    pct = current / total
    filled = int(width * pct)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {pct:6.1%}"


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------
def initiate_upload(filename: str, file_size: int, file_type: str = "text/csv") -> dict:
    resp = requests.post(
        f"{BASE_URL}/files/uploads/initiate",
        headers={**AUTH, "Content-Type": "application/json"},
        json={"filename": filename, "file_type": file_type, "num_bytes": file_size},
    )
    resp.raise_for_status()
    return resp.json()


def upload_part(url: str, data: bytes, length: int) -> str:
    """Upload a single part and return its ETag."""
    resp = requests.put(url, data=data, headers={"Content-Length": str(length)})
    resp.raise_for_status()
    return resp.headers.get("ETag", "").strip('"')


def complete_upload(upload_id: str, parts: list) -> dict:
    resp = requests.post(
        f"{BASE_URL}/files/uploads/{upload_id}/complete",
        headers={**AUTH, "Content-Type": "application/json"},
        json={"parts": parts},
    )
    resp.raise_for_status()
    return resp.json()


def abort_upload(upload_id: str):
    requests.post(f"{BASE_URL}/files/uploads/{upload_id}/abort", headers=AUTH)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <file_path>")
        sys.exit(1)

    file_path = sys.argv[1]
    file_size = os.path.getsize(file_path)
    filename = os.path.basename(file_path)

    print(f"{'='*60}")
    print(f" Archetype AI Multipart Upload")
    print(f"{'='*60}")
    print(f" File:     {filename}")
    print(f" Size:     {fmt_bytes(file_size)} ({file_size:,} bytes)")
    print(f" Endpoint: {BASE_URL}")
    print(f"{'='*60}")
    print()

    # --- Step 1: Initiate ---------------------------------------------------
    print("[1/3] Initiating upload...")
    init = initiate_upload(filename, file_size)

    upload_id = init["upload_id"]
    file_uid = init["file_uid"]
    strategy = init["strategy"]
    num_parts = init["num_parts"]
    part_size = init.get("part_size", file_size)
    parts = init["parts"]

    print(f"      upload_id : {upload_id}")
    print(f"      file_uid  : {file_uid}")
    print(f"      strategy  : {strategy}")
    print(f"      parts     : {num_parts} x {fmt_bytes(part_size)}")
    print(f"      expires_at: {init.get('expires_at', 'N/A')}")
    print()

    # --- Step 2: Upload parts ------------------------------------------------
    print(f"[2/3] Uploading {num_parts} parts to S3...")
    print()

    completed_parts = []
    bytes_uploaded = 0
    upload_start = time.time()

    try:
        with open(file_path, "rb") as f:
            for part in parts:
                part_num = part["part_number"]
                offset = part["offset"]
                length = part["length"]

                f.seek(offset)
                data = f.read(length)

                part_start = time.time()
                etag = upload_part(part["url"], data, length)
                part_elapsed = time.time() - part_start

                bytes_uploaded += length
                part_speed = length / part_elapsed / 1024 / 1024
                overall_elapsed = time.time() - upload_start
                overall_speed = bytes_uploaded / overall_elapsed / 1024 / 1024
                eta = (file_size - bytes_uploaded) / (bytes_uploaded / overall_elapsed) if bytes_uploaded else 0

                print(f"  Part {part_num:>2}/{num_parts}  "
                      f"{progress_bar(bytes_uploaded, file_size)}  "
                      f"{fmt_bytes(bytes_uploaded):>8}/{fmt_bytes(file_size)}  "
                      f"{part_speed:5.1f} MB/s  "
                      f"ETA {eta:5.0f}s")

                completed_parts.append({"part_number": part_num, "part_token": etag})

    except Exception as e:
        print(f"\n  Upload FAILED at part {part_num}: {e}")
        print(f"  Aborting upload {upload_id}...")
        abort_upload(upload_id)
        sys.exit(1)

    total_time = time.time() - upload_start
    avg_speed = file_size / total_time / 1024 / 1024
    print()
    print(f"      All parts uploaded in {total_time:.1f}s (avg {avg_speed:.1f} MB/s)")
    print()

    # --- Step 3: Complete ----------------------------------------------------
    print("[3/3] Completing upload...")
    result = complete_upload(upload_id, completed_parts)
    print(f"      {json.dumps(result, indent=6)}")
    print()
    print(f"{'='*60}")
    print(f" DONE  file_uid: {result.get('file_uid', file_uid)}")
    print(f"       status:   {result.get('file_status', 'unknown')}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
