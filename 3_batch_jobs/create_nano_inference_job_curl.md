# Create Nano Inference Job with curl (step-by-step)

Manual curl commands for creating and monitoring Nano Inference batch jobs.

## Prerequisites

```bash
export ATAI_API_KEY="your-api-key"
export ATAI_API_ENDPOINT="https://api.dev.u1.archetypeai.app"
export BASE_URL="$ATAI_API_ENDPOINT/v0.5"
```

## Input Format

Each input file must be JSONL with `system`, `instruction`, and/or `prompt` fields:
```json
{"system": "You are a drilling analyst.", "instruction": "Describe the rig state.", "prompt": "BPOS: 10.02, DBTM: 259.92, ..."}
```

Use `1_prepare_data/convert_to_inference_jsonl.py` to convert CSV to JSONL.

## Step 1: Create a Nano Inference Job

```bash
curl -s -X POST "$BASE_URL/jos/jobs" \
  -H "Authorization: Bearer $ATAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "volve-nano-inference",
    "pipeline_type": "batch",
    "pipeline_key": "nano-inference-pipeline",
    "inputs": {
      "worker.data": [{"file_id": "volve_nano_200.jsonl"}]
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
  }' | python3 -m json.tool
```

Response:
```json
{
  "id": "job_...",
  "name": "volve-nano-inference",
  "pipeline_type": "batch",
  "pipeline_key": "nano-inference-pipeline",
  "pipeline_version": "0.0.20",
  "status": "PENDING",
  ...
}
```

## Step 2: Check Job Status

```bash
JOB_ID="job_..."

curl -s "$BASE_URL/jos/jobs/$JOB_ID" \
  -H "Authorization: Bearer $ATAI_API_KEY" | python3 -m json.tool
```

## Step 3: View Job Events

```bash
curl -s "$BASE_URL/jos/jobs/$JOB_ID/events" \
  -H "Authorization: Bearer $ATAI_API_KEY" | python3 -m json.tool
```

## Output Format

Each output line:
```json
{"line_index": 0, "prediction": "Based on the sensor readings, the rig appears to be idle..."}
```

On error:
```json
{"line_index": 5, "prediction": null, "error": "parse error"}
```

## Important Notes

- Input must be **JSONL format** — raw CSV will produce `"error": "parse error"` for every line
- The base Newton model produces generic responses without fine-tuning
- Large files (millions of rows) may timeout — test with small batches first
- Include sensor definitions in the `system` prompt for better abbreviation interpretation
