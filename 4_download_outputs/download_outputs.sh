#!/usr/bin/env bash
#
# Download batch job output artifacts from the Archetype AI platform.
#
# Usage:
#   ./download_outputs.sh <job_id> [output_dir]
#   ./download_outputs.sh job_6pgect4qqc8h0sd6v3rva23y8g outputs/
#
# Requires: curl, python3 (for JSON parsing)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Load env
export $(grep -v '^#' "$PROJECT_DIR/.env" | xargs)
BASE_URL="${ATAI_API_ENDPOINT}/v0.5"

JOB_ID="${1:?Usage: $0 <job_id> [output_dir]}"
OUTPUT_DIR="${2:-outputs/$JOB_ID}"
mkdir -p "$OUTPUT_DIR"

echo "============================================================"
echo " Download Batch Job Outputs (Shell)"
echo "============================================================"
echo "  Job:    $JOB_ID"
echo "  Saving: $OUTPUT_DIR/"
echo

# Step 1: Get total count
echo "[1/2] Fetching output list..."
FIRST_PAGE=$(/usr/bin/curl -s "$BASE_URL/jos/jobs/$JOB_ID/outputs?limit=1&offset=0" \
  -H "Authorization: Bearer $ATAI_API_KEY")
TOTAL=$(echo "$FIRST_PAGE" | python3 -c "import sys,json; print(json.load(sys.stdin)['total'])")
echo "  Total: $TOTAL files"
echo

# Step 2: Download all files (paginated)
echo "[2/2] Downloading $TOTAL files..."

OFFSET=0
LIMIT=50
DOWNLOADED=0

while [ "$OFFSET" -lt "$TOTAL" ]; do
    # Fetch page of outputs
    PAGE=$(/usr/bin/curl -s "$BASE_URL/jos/jobs/$JOB_ID/outputs?limit=$LIMIT&offset=$OFFSET" \
      -H "Authorization: Bearer $ATAI_API_KEY")

    # Extract URLs and filenames
    NUM_ITEMS=$(echo "$PAGE" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['outputs']))")

    for i in $(seq 0 $((NUM_ITEMS - 1))); do
        URL=$(echo "$PAGE" | python3 -c "import sys,json; print(json.load(sys.stdin)['outputs'][$i]['data']['ref'])")
        FNAME=$(echo "$PAGE" | python3 -c "import sys,json; print(json.load(sys.stdin)['outputs'][$i]['data']['filename'])")

        /usr/bin/curl -s -o "$OUTPUT_DIR/$FNAME" "$URL"
        DOWNLOADED=$((DOWNLOADED + 1))

        if [ $((DOWNLOADED % 50)) -eq 0 ] || [ "$DOWNLOADED" -eq "$TOTAL" ]; then
            PCT=$((DOWNLOADED * 100 / TOTAL))
            echo "  [$PCT%] $DOWNLOADED/$TOTAL  $FNAME"
        fi
    done

    OFFSET=$((OFFSET + LIMIT))
done

FILE_COUNT=$(ls -1 "$OUTPUT_DIR" | wc -l | tr -d ' ')
TOTAL_SIZE=$(du -sh "$OUTPUT_DIR" | awk '{print $1}')

echo
echo "  Done! $FILE_COUNT files, $TOTAL_SIZE"
echo "  Saved to: $OUTPUT_DIR/"
echo "============================================================"
