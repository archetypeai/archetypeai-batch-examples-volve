#!/usr/bin/env bash
#
# Create and monitor a Nano Inference batch job on the Archetype AI platform.
#
# Usage:
#   ./create_nano_inference_job.sh
#
# Requires: curl, python3 (for JSON parsing)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Load env
export $(grep -v '^#' "$PROJECT_DIR/.env" | xargs)
BASE_URL="${ATAI_API_ENDPOINT}/v0.5"

echo "============================================================"
echo " Archetype AI Nano Inference Job (Shell)"
echo "============================================================"
echo

# --- Step 1: Create job ---------------------------------------------------
echo "[1/3] Creating nano inference job..."

JOB_RESPONSE=$(/usr/bin/curl -s -X POST "$BASE_URL/jos/jobs" \
  -H "Authorization: Bearer $ATAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "volve-nano-inference-sh",
    "pipeline_type": "batch",
    "pipeline_key": "nano-inference-pipeline",
    "inputs": {
      "worker.data": [{"file_id": "volve_nano_30.jsonl"}]
    },
    "parameters": {
      "worker": {
        "parallelism": 1,
        "config": {
          "generation": {
            "do_sample": true,
            "max_new_tokens": 256,
            "repetition_penalty": 1,
            "temperature": 0.7,
            "top_k": 20,
            "top_p": 0.8
          }
        }
      }
    }
  }')

JOB_ID=$(echo "$JOB_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
JOB_NAME=$(echo "$JOB_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['name'])")
JOB_STATUS=$(echo "$JOB_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")

echo "      job_id: $JOB_ID"
echo "      name:   $JOB_NAME"
echo "      status: $JOB_STATUS"
echo

# --- Step 2: Poll status ---------------------------------------------------
echo "[2/3] Monitoring job status..."

POLL_INTERVAL=15
PREV_STATUS=""

while true; do
    STATUS_RESPONSE=$(/usr/bin/curl -s "$BASE_URL/jos/jobs/$JOB_ID" \
      -H "Authorization: Bearer $ATAI_API_KEY")

    STATUS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")

    if [ "$STATUS" != "$PREV_STATUS" ]; then
        echo "      [$(date +%H:%M:%S)] $STATUS"
        PREV_STATUS="$STATUS"
    fi

    case "$STATUS" in
        COMPLETED|FAILED|CANCELLED) break ;;
    esac

    sleep $POLL_INTERVAL
done

echo

# --- Step 3: Show events ---------------------------------------------------
echo "[3/3] Job events:"

EVENTS=$(/usr/bin/curl -s "$BASE_URL/jos/jobs/$JOB_ID/events" \
  -H "Authorization: Bearer $ATAI_API_KEY")

echo "$EVENTS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for event in reversed(data.get('events', [])):
    level = event['level']
    msg = event['message']
    ts = event['created_at'][11:19]
    marker = '!!' if level == 'ERROR' else '  '
    print(f'  {marker} [{ts}] {level:<5} {msg}')
"

echo
echo "============================================================"
echo " Job: $JOB_ID"
echo " Status: $STATUS"
echo "============================================================"
