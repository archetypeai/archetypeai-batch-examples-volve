#!/usr/bin/env bash
#
# Multipart file upload to Archetype AI using presigned URLs (shell script).
#
# Usage:
#   ./upload_multipart.sh data/HIGGS.csv
#
# Requires: curl, python3 (for JSON parsing), dd

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Load env
export $(grep -v '^#' "$PROJECT_DIR/.env" | xargs)
BASE_URL="${ATAI_API_ENDPOINT}/v0.5"

FILE_PATH="${1:?Usage: $0 <file_path>}"
FILE_NAME="$(basename "$FILE_PATH")"
FILE_SIZE=$(stat -f%z "$FILE_PATH" 2>/dev/null || stat --printf="%s" "$FILE_PATH")

echo "============================================================"
echo " Archetype AI Multipart Upload (Shell)"
echo "============================================================"
echo " File:     $FILE_NAME"
echo " Size:     $(echo "$FILE_SIZE" | awk '{printf "%.2f GB", $1/1073741824}') ($FILE_SIZE bytes)"
echo " Endpoint: $BASE_URL"
echo "============================================================"
echo

# --- Step 1: Initiate -------------------------------------------------------
echo "[1/3] Initiating upload..."

INIT_RESPONSE=$(curl -s -X POST "$BASE_URL/files/uploads/initiate" \
  -H "Authorization: Bearer $ATAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"filename\":\"$FILE_NAME\",\"file_type\":\"text/csv\",\"num_bytes\":$FILE_SIZE}")

UPLOAD_ID=$(echo "$INIT_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['upload_id'])")
FILE_UID=$(echo "$INIT_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['file_uid'])")
STRATEGY=$(echo "$INIT_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['strategy'])")
NUM_PARTS=$(echo "$INIT_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['num_parts'])")
PART_SIZE=$(echo "$INIT_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('part_size',0))")

echo "      upload_id : $UPLOAD_ID"
echo "      file_uid  : $FILE_UID"
echo "      strategy  : $STRATEGY"
echo "      parts     : $NUM_PARTS x $(echo "$PART_SIZE" | awk '{printf "%.0f MB", $1/1048576}')"
echo

# Save initiate response for part extraction
echo "$INIT_RESPONSE" > /tmp/atai_upload_init.json

# --- Step 2: Upload parts ---------------------------------------------------
echo "[2/3] Uploading $NUM_PARTS parts to S3..."
echo

COMPLETED_PARTS="["
UPLOAD_START=$(date +%s)
BYTES_UPLOADED=0

for i in $(seq 0 $((NUM_PARTS - 1))); do
    PART_NUM=$((i + 1))

    # Extract part info using python3
    PART_INFO=$(python3 -c "
import json
with open('/tmp/atai_upload_init.json') as f:
    data = json.load(f)
part = data['parts'][$i]
print(part['url'])
print(part['offset'])
print(part['length'])
")
    PART_URL=$(echo "$PART_INFO" | sed -n '1p')
    OFFSET=$(echo "$PART_INFO" | sed -n '2p')
    LENGTH=$(echo "$PART_INFO" | sed -n '3p')

    # Extract the part from the file using dd
    PART_FILE="/tmp/atai_part_${PART_NUM}.bin"
    BLOCK_SIZE=1048576  # 1 MB
    SKIP_BLOCKS=$((OFFSET / BLOCK_SIZE))
    COUNT_BLOCKS=$((LENGTH / BLOCK_SIZE))
    REMAINDER=$((LENGTH % BLOCK_SIZE))

    dd if="$FILE_PATH" of="$PART_FILE" bs=$BLOCK_SIZE skip=$SKIP_BLOCKS count=$COUNT_BLOCKS 2>/dev/null
    if [ "$REMAINDER" -gt 0 ]; then
        dd if="$FILE_PATH" of="$PART_FILE" bs=1 skip=$((OFFSET + COUNT_BLOCKS * BLOCK_SIZE)) count=$REMAINDER oflag=append conv=notrunc 2>/dev/null
    fi

    PART_START=$(date +%s)

    # Upload part and capture ETag
    ETAG=$(curl -s -X PUT "$PART_URL" \
      -H "Content-Length: $LENGTH" \
      --data-binary "@$PART_FILE" \
      -D - -o /dev/null 2>/dev/null | grep -i "^etag:" | tr -d '\r' | awk '{print $2}' | tr -d '"')

    rm -f "$PART_FILE"

    PART_END=$(date +%s)
    PART_ELAPSED=$((PART_END - PART_START))
    [ "$PART_ELAPSED" -eq 0 ] && PART_ELAPSED=1

    BYTES_UPLOADED=$((BYTES_UPLOADED + LENGTH))
    PART_SPEED=$((LENGTH / PART_ELAPSED / 1048576))
    OVERALL_ELAPSED=$((PART_END - UPLOAD_START))
    [ "$OVERALL_ELAPSED" -eq 0 ] && OVERALL_ELAPSED=1
    PCT=$((BYTES_UPLOADED * 100 / FILE_SIZE))
    REMAINING=$((FILE_SIZE - BYTES_UPLOADED))
    SPEED=$((BYTES_UPLOADED / OVERALL_ELAPSED))
    [ "$SPEED" -eq 0 ] && SPEED=1
    ETA=$((REMAINING / SPEED))

    printf "  Part %2d/%d  [%3d%%]  %s/%s  %d MB/s  ETag: %s...  ETA: %ds\n" \
      "$PART_NUM" "$NUM_PARTS" "$PCT" \
      "$(echo "$BYTES_UPLOADED" | awk '{printf "%.2f GB", $1/1073741824}')" \
      "$(echo "$FILE_SIZE" | awk '{printf "%.2f GB", $1/1073741824}')" \
      "$PART_SPEED" "${ETAG:0:12}" "$ETA"

    # Build completed parts JSON
    if [ "$i" -gt 0 ]; then COMPLETED_PARTS="$COMPLETED_PARTS,"; fi
    COMPLETED_PARTS="$COMPLETED_PARTS{\"part_number\":$PART_NUM,\"part_token\":\"$ETAG\"}"
done

COMPLETED_PARTS="$COMPLETED_PARTS]"
UPLOAD_END=$(date +%s)
TOTAL_TIME=$((UPLOAD_END - UPLOAD_START))
[ "$TOTAL_TIME" -eq 0 ] && TOTAL_TIME=1
AVG_SPEED=$((FILE_SIZE / TOTAL_TIME / 1048576))

echo
echo "      All parts uploaded in ${TOTAL_TIME}s (avg ${AVG_SPEED} MB/s)"
echo

# --- Step 3: Complete -------------------------------------------------------
echo "[3/3] Completing upload..."

COMPLETE_RESPONSE=$(curl -s -X POST "$BASE_URL/files/uploads/$UPLOAD_ID/complete" \
  -H "Authorization: Bearer $ATAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"parts\":$COMPLETED_PARTS}")

echo "      $COMPLETE_RESPONSE"
echo
echo "============================================================"
echo " DONE  file_uid: $(echo "$COMPLETE_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('file_uid','$FILE_UID'))")"
echo "       status:   $(echo "$COMPLETE_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('file_status','unknown'))")"
echo "============================================================"

# Cleanup
rm -f /tmp/atai_upload_init.json
