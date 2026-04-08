#!/usr/bin/env bash
#
# Create and monitor a batch job on the Archetype AI platform.
#
# Usage:
#   ./create_batch_job.sh
#
# Requires: curl, python3 (for JSON parsing)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Load env
export $(grep -v '^#' "$PROJECT_DIR/.env" | xargs)
BASE_URL="${ATAI_API_ENDPOINT}/v0.5"

echo "============================================================"
echo " Archetype AI Batch Job (Shell)"
echo "============================================================"
echo

# --- Step 1: Create job ---------------------------------------------------
echo "[1/3] Creating batch job..."

JOB_RESPONSE=$(/usr/bin/curl -s -X POST "$BASE_URL/jos/jobs" \
  -H "Authorization: Bearer $ATAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "higgs-batch-inference-sh",
    "pipeline_type": "batch",
    "pipeline_key": "machine-state-job-pipeline",
    "inputs": {
      "worker.inference": [{"file_id": "higgs_no_label.csv"}],
      "worker.n_shots": [
        {"file_id": "higgs_boson.csv", "metadata": {"class": "boson"}},
        {"file_id": "higgs_no_boson.csv", "metadata": {"class": "no_boson"}}
      ]
    },
    "parameters": {
      "worker": {
        "parallelism": 1,
        "config": {
          "batch_size": 8,
          "classifier_config": {
            "metric": "euclidean",
            "n_neighbors": 5,
            "weights": "uniform"
          },
          "data_columns": ["lepton_pT","lepton_eta","lepton_phi","missing_energy_magnitude","missing_energy_phi","jet_1_pt","jet_1_eta","jet_1_phi","jet_1_b-tag","jet_2_pt","jet_2_eta","jet_2_phi","jet_2_b-tag","jet_3_pt","jet_3_eta","jet_3_phi","jet_3_b-tag","jet_4_pt","jet_4_eta","jet_4_phi","jet_4_b-tag","m_jj","m_jjj","m_lv","m_jlv","m_bb","m_wbb","m_wwbb"],
          "flush_every_n_iteration": 150,
          "model_type": "omega_1_3_slb_surface",
          "reader_config": {"step_size": 1, "window_size": 1},
          "timestamp_column": "timestamp"
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

POLL_INTERVAL=5
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
