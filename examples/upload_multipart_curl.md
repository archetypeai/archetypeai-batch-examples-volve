# Multipart Upload with curl (step-by-step)

Manual curl commands for the 3-step presigned URL upload flow.

## Prerequisites

```bash
export ATAI_API_KEY="your-api-key"
export ATAI_API_ENDPOINT="https://api.dev.u1.archetypeai.app"
export BASE_URL="$ATAI_API_ENDPOINT/v0.5"
```

## Step 1: Initiate Upload

```bash
curl -s -X POST "$BASE_URL/files/uploads/initiate" \
  -H "Authorization: Bearer $ATAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "filename": "HIGGS.csv",
    "file_type": "text/csv",
    "num_bytes": 8035497980
  }' | python3 -m json.tool
```

Response (truncated):
```json
{
  "upload_id": "upl_abc123...",
  "file_uid": "fil_xyz789...",
  "strategy": "multipart",
  "num_parts": 20,
  "part_size": 419430400,
  "parts": [
    {"part_number": 1, "url": "https://s3...presigned-url...", "offset": 0, "length": 419430400},
    {"part_number": 2, "url": "https://s3...presigned-url...", "offset": 419430400, "length": 419430400},
    ...
  ],
  "expires_at": "2026-04-09T02:12:58Z"
}
```

Save the response:
```bash
curl -s -X POST "$BASE_URL/files/uploads/initiate" \
  -H "Authorization: Bearer $ATAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"filename":"HIGGS.csv","file_type":"text/csv","num_bytes":8035497980}' \
  > /tmp/upload_init.json
```

## Step 2: Upload Each Part

Extract a part's URL and upload the corresponding file bytes:

```bash
# Extract part 1 URL (using python3 for JSON parsing)
PART1_URL=$(python3 -c "import json; print(json.load(open('/tmp/upload_init.json'))['parts'][0]['url'])")

# Upload part 1 (first 400 MB)
dd if=data/HIGGS.csv bs=1M count=400 2>/dev/null | \
  curl -X PUT "$PART1_URL" \
    -H "Content-Length: 419430400" \
    --data-binary @- \
    -D /tmp/part1_headers.txt \
    -o /dev/null -s -w "HTTP %{http_code} in %{time_total}s\n"

# Get ETag from response headers
grep -i etag /tmp/part1_headers.txt
# -> ETag: "abc123def456..."
```

For part N (example: part 5):
```bash
PART_NUM=5
OFFSET=$(python3 -c "import json; print(json.load(open('/tmp/upload_init.json'))['parts'][$((PART_NUM-1))]['offset'])")
LENGTH=$(python3 -c "import json; print(json.load(open('/tmp/upload_init.json'))['parts'][$((PART_NUM-1))]['length'])")
PART_URL=$(python3 -c "import json; print(json.load(open('/tmp/upload_init.json'))['parts'][$((PART_NUM-1))]['url'])")

dd if=data/HIGGS.csv bs=1 skip=$OFFSET count=$LENGTH 2>/dev/null | \
  curl -X PUT "$PART_URL" \
    -H "Content-Length: $LENGTH" \
    --data-binary @- \
    -D /tmp/part${PART_NUM}_headers.txt \
    -o /dev/null -s -w "Part $PART_NUM: HTTP %{http_code} in %{time_total}s\n"
```

## Step 3: Complete Upload

Collect all ETags and send the completion request:

```bash
UPLOAD_ID=$(python3 -c "import json; print(json.load(open('/tmp/upload_init.json'))['upload_id'])")

curl -s -X POST "$BASE_URL/files/uploads/$UPLOAD_ID/complete" \
  -H "Authorization: Bearer $ATAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "parts": [
      {"part_number": 1, "part_token": "etag-from-part-1"},
      {"part_number": 2, "part_token": "etag-from-part-2"},
      ...
    ]
  }' | python3 -m json.tool
```

Response:
```json
{
  "file_uid": "fil_xyz789...",
  "file_name": "HIGGS.csv",
  "file_status": "Registered",
  "num_bytes": 8035497980,
  "file_attributes": {}
}
```

## Abort (if needed)

```bash
curl -s -X POST "$BASE_URL/files/uploads/$UPLOAD_ID/abort" \
  -H "Authorization: Bearer $ATAI_API_KEY"
```
