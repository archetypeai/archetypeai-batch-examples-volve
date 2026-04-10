# Create Batch Job with curl (step-by-step)

Manual curl commands for creating and monitoring batch jobs.

## Prerequisites

```bash
export ATAI_API_KEY="your-api-key"
export ATAI_API_ENDPOINT="https://api.dev.u1.archetypeai.app"
export BASE_URL="$ATAI_API_ENDPOINT/v0.5"
```

## Step 1: Create a Batch Job

```bash
curl -s -X POST "$BASE_URL/jos/jobs" \
  -H "Authorization: Bearer $ATAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "higgs-batch-inference",
    "pipeline_type": "batch",
    "pipeline_key": "machine-state-job-pipeline",
    "inputs": {
      "worker.inference": [
        {"file_id": "higgs_no_label.csv"}
      ],
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
          "model_type": "omega_1_3_surface",
          "reader_config": {"step_size": 1, "window_size": 1},
          "timestamp_column": "timestamp"
        }
      }
    }
  }' | python3 -m json.tool
```

Response:
```json
{
  "id": "job_2w2ykhs5a49qwszbdqj1sr636n",
  "name": "higgs-batch-inference",
  "pipeline_type": "batch",
  "pipeline_key": "machine-state-job-pipeline",
  "pipeline_version": "0.1.29",
  "status": "PENDING",
  "created_at": "2026-04-08T21:51:56.283818Z",
  ...
}
```

Save the job ID:
```bash
JOB_ID="job_2w2ykhs5a49qwszbdqj1sr636n"
```

## Step 2: Check Job Status

```bash
curl -s "$BASE_URL/jos/jobs/$JOB_ID" \
  -H "Authorization: Bearer $ATAI_API_KEY" | python3 -m json.tool
```

Status values: `PENDING` → `RUNNING` → `COMPLETED` / `FAILED` / `CANCELLED`

## Step 3: View Job Events

```bash
curl -s "$BASE_URL/jos/jobs/$JOB_ID/events" \
  -H "Authorization: Bearer $ATAI_API_KEY" | python3 -m json.tool
```

Response:
```json
{
  "job_id": "job_2w2ykhs5a49qwszbdqj1sr636n",
  "total": 8,
  "events": [
    {"event_type": "info", "level": "INFO", "message": "Using accelerator: cuda"},
    {"event_type": "running_job", "level": "INFO", "message": "Running job"},
    {"event_type": "vectorizing_file", "level": "INFO", "message": "Vectorizing file higgs_boson.csv"},
    ...
  ]
}
```

## List All Jobs

```bash
curl -s "$BASE_URL/jos/jobs?limit=10&offset=0" \
  -H "Authorization: Bearer $ATAI_API_KEY" | python3 -m json.tool
```

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v0.5/jos/jobs` | POST | Create a batch job |
| `/v0.5/jos/jobs` | GET | List all jobs |
| `/v0.5/jos/jobs/{job_id}` | GET | Get job status |
| `/v0.5/jos/jobs/{job_id}/events` | GET | Get job events/logs |
