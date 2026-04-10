# Download Batch Job Outputs with curl (step-by-step)

Manual curl commands for downloading batch job output artifacts.

## Prerequisites

```bash
export ATAI_API_KEY="your-api-key"
export ATAI_API_ENDPOINT="https://api.dev.u1.archetypeai.app"
export BASE_URL="$ATAI_API_ENDPOINT/v0.5"
export JOB_ID="job_6pgect4qqc8h0sd6v3rva23y8g"
```

## Step 1: List Output Artifacts

```bash
# Get first page of outputs (50 per page)
curl -s "$BASE_URL/jos/jobs/$JOB_ID/outputs?limit=50&offset=0" \
  -H "Authorization: Bearer $ATAI_API_KEY" | python3 -m json.tool
```

Response:
```json
{
  "job_id": "job_6pgect4qqc8h0sd6v3rva23y8g",
  "total": 1375,
  "offset": 0,
  "limit": 50,
  "outputs": [
    {
      "id": "out_...",
      "data": {
        "ref": "https://s3...presigned-url...",
        "filename": "pred_volve_inference_part_1374.csv",
        "num_bytes": 147016
      },
      "expires_at": "2026-04-10T00:21:12Z"
    }
  ]
}
```

Key fields:
- `total` — total number of output files
- `data.ref` — presigned S3 URL (valid for 1 hour, no auth needed)
- `data.filename` — original filename
- `data.num_bytes` — file size

## Step 2: Download a Single File

Extract the presigned URL and download directly:

```bash
# Get the URL for the first output
URL=$(curl -s "$BASE_URL/jos/jobs/$JOB_ID/outputs?limit=1&offset=0" \
  -H "Authorization: Bearer $ATAI_API_KEY" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['outputs'][0]['data']['ref'])")

# Download (no auth header needed — signature is in the URL)
curl -s -o output_part.csv "$URL"

# View contents
head -5 output_part.csv
# Prediction,TimePoint
# drilling,1767225600
# not_drilling,1767225601
# ...
```

## Step 3: Download All Files (loop)

```bash
mkdir -p outputs/$JOB_ID

TOTAL=$(curl -s "$BASE_URL/jos/jobs/$JOB_ID/outputs?limit=1" \
  -H "Authorization: Bearer $ATAI_API_KEY" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['total'])")

echo "Total files: $TOTAL"

OFFSET=0
LIMIT=50

while [ "$OFFSET" -lt "$TOTAL" ]; do
  # Fetch page
  PAGE=$(curl -s "$BASE_URL/jos/jobs/$JOB_ID/outputs?limit=$LIMIT&offset=$OFFSET" \
    -H "Authorization: Bearer $ATAI_API_KEY")

  # Download each file in the page
  echo "$PAGE" | python3 -c "
import sys, json
for out in json.load(sys.stdin)['outputs']:
    print(out['data']['ref'] + '\t' + out['data']['filename'])
" | while IFS=$'\t' read -r url fname; do
    curl -s -o "outputs/$JOB_ID/$fname" "$url"
  done

  OFFSET=$((OFFSET + LIMIT))
  echo "Downloaded $OFFSET/$TOTAL..."
done
```

## Step 4: Merge All Parts

```bash
# Merge all CSV parts into a single file (keep header from first file only)
head -1 outputs/$JOB_ID/pred_volve_inference_part_0.csv > outputs/predictions_merged.csv
for f in outputs/$JOB_ID/pred_volve_inference_part_*.csv; do
  tail -n +2 "$f" >> outputs/predictions_merged.csv
done

wc -l outputs/predictions_merged.csv
```

## Output Format

Each output CSV contains:

| Column | Description |
|--------|-------------|
| `Prediction` | Predicted class (`drilling` or `not_drilling`) |
| `TimePoint` | Timestamp from input data (maps to row index) |

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v0.5/jos/jobs/{job_id}/outputs` | GET | List output artifacts (paginated) |
| `{presigned_url}` | GET | Download artifact (no auth, 1hr expiry) |

## Notes

- Presigned URLs expire in **1 hour** — re-fetch `/outputs` to get fresh URLs
- URLs are generated on each API call, so pagination is safe across time
- Output files are CSV with headers, ~147 KB each (~8000 predictions per file)
