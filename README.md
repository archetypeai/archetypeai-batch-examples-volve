# Archetype AI Batch Processing Examples

End-to-end examples for batch upload, batch inference, and batch fine-tuning on the Archetype AI platform using real-world drilling sensor data from the [Equinor Volve Data Village](https://www.equinor.com/energy/volve-data-sharing) (7.4M rows, 14 wells, North Sea 2007-2016).

**What's included:**

| Step | Script | Description |
|------|--------|-------------|
| Prepare data | `1_prepare_data/` | Convert WITSML XML → CSV, generate ACTC labels, split into n-shot/inference files |
| Upload | `2_upload/` | Multipart presigned URL upload for large files (Python, shell, curl) |
| Batch jobs | `3_batch_jobs/` | Machine State classification + Nano Inference text generation |
| Download | `4_download_outputs/` | Paginated output download via presigned S3 URLs |
| Evaluate | `5_evaluate/` | Compare predictions against ACTC ground truth (accuracy, F1) |
| Optimize | `3_batch_jobs/optimize_config.py` | Grid search over pipeline hyperparameters |
| Fine-tune | `1_prepare_data/convert_to_jsonl.py` | TBD — fine-tuning endpoint not yet available |

**Two pipelines:**
- **Machine State** — classifies sensor windows as "drilling" vs "not_drilling" using n-shot examples + KNN (67% accuracy on quick test, full run pending)
- **Nano Inference** — generates natural language descriptions of rig state from sensor readings

**Quick start:** All data files are pre-built in `data/` via Git LFS. Skip to [step 4 (Upload)](#4-upload-files) to get started immediately.

## 1. Setup

```bash
# Clone
git clone https://github.com/archetypeai/archetype-batch-examples.git
cd archetype-batch-examples

# Configure credentials
cp .env.example .env
# Edit .env with your ATAI_API_KEY and ATAI_API_ENDPOINT

# Create a virtual environment
python3 -m venv myenv

# Activate it
source myenv/bin/activate

# Install Python dependencies
pip install requests

# Deactivate when done
deactivate
```

## 2. Dataset

These examples use the [Equinor Volve Data Village](https://www.equinor.com/energy/volve-data-sharing) — real-time drilling sensor data from the Volve oil field in the North Sea (2007-2016). The dataset is provided by Equinor under a [modified CC BY 4.0 license](https://www.equinor.com/energy/volve-data-sharing) (free for commercial use, must not be resold, must attribute Equinor).

### Why Drilling Data?

A drilling rig does many things besides actually drilling a hole. During a well operation, the rig cycles through different activities:

**Drilling** (actively cutting rock):
- Bit is on bottom, rotating (RPM > 0)
- Mud is flowing (SPPA > 0) to cool the bit and carry cuttings out
- The hole is getting deeper (ROP > 0)

**Not-drilling** (everything else):
- **Tripping** — pulling drill pipe out to change the bit, or running it back in
- **Connection** — adding a new pipe section (every ~30m of drilling, you stop and screw on another pipe)
- **Circulation** — pumping mud without drilling to clean the hole
- **Shut-in** — everything stopped (crew change, equipment issue, weather)

**Why rig state classification matters:**

1. **Safety** — detecting unexpected state changes (e.g., the rig thinks it's drilling but sensors show it stopped — could mean a stuck pipe)
2. **Efficiency** — how much time is spent actually drilling vs. non-productive time? Rig time costs ~$500K-$1M/day
3. **Anomaly detection** — sensor patterns during drilling that don't match normal drilling signatures could indicate equipment failure or geological problems
4. **Automation** — real-time rig state classification enables automated drilling advisors

### Sensor Channels

The Volve dataset provides 9 surface drilling sensor channels:

| Column | Description | Unit |
|--------|-------------|------|
| `DATE_TIME` | Timestamp (Unix epoch) | seconds |
| `BPOS` | Block Position — height of the traveling block | m |
| `DBTM` | Bit Depth — how deep the drill bit is | m |
| `FLWI` | Flow In — mud flow rate into the hole | L/min |
| `HDTH` | Hole Depth — total depth of the hole | m |
| `HKLD` | Hookload — weight hanging from the hook | kkgf |
| `ROP` | Rate of Penetration — drilling speed | m/h |
| `RPM` | Rotary Speed — drill string rotation | rpm |
| `SPPA` | Standpipe Pressure — mud pump pressure | kPa |
| `WOB` | Weight on Bit — downward force on the rock | kkgf |

### Download

Download the "WITSML Realtime drilling data" from the [Equinor Volve Data Village](https://www.equinor.com/energy/volve-data-sharing) (requires free registration via Databricks Marketplace). Place the zip file in `Downloads/volve-data-village/`.

```bash
mkdir -p data/volve
unzip "path/to/Volve_WITSML Realtime drilling data.zip" -d data/volve/
```

This creates `data/volve/WITSML Realtime drilling data/` with well folders containing WITSML XML files.

> **Note:** If you'd rather skip the download and conversion steps, all data files are already included in `data/` via Git LFS — see `volve_raw.csv`, `volve_raw_labeled.csv`, `volve_drilling.csv`, `volve_not_drilling.csv`, `volve_inference.csv`, `volve_quick_test_200.csv`, and `volve_nano_200.jsonl`.

## 3. Prepare Data

### Step 1: Convert WITSML XML to raw CSV

Parse all WITSML XML files into a single CSV with sensor data and ACTC rig mode codes:

```bash
python 1_prepare_data/volve_to_csv.py
```

Output: `data/volve_raw.csv` — 7,419,984 rows, 860 MB (9 sensor columns + DATE_TIME + ACTC)

### Step 2: Generate labels and split data

Label rows using ACTC rig mode codes and split into n-shot, inference, and quick test files:

```bash
python 1_prepare_data/generate_labels.py
```

ACTC code mapping:

| ACTC Code | Meaning | Label |
|-----------|---------|-------|
| 1 | Drilling | `drilling` |
| 2 | Reaming | `drilling` |
| 3 | Off Bottom | `not_drilling` |
| 4 | In Slips | `not_drilling` |
| 8 | Trip In Slips | `not_drilling` |
| 9 | Shut In | `not_drilling` |
| -1, 0, 5, 19, 20, empty | Ambiguous/unknown | skipped |

Output files:

| File | Rows | Size | Description |
|------|------|------|-------------|
| `volve_raw_labeled.csv` | 7,321,497 | 918 MB | All labeled rows (ground truth for evaluation) |
| `volve_drilling.csv` | 2,000 | 248 KB | N-shot examples — ACTC-labeled drilling |
| `volve_not_drilling.csv` | 2,000 | 229 KB | N-shot examples — ACTC-labeled not-drilling |
| `volve_inference.csv` | 7,317,439 | 834 MB | Remaining rows for batch inference (no label) |
| `volve_quick_test_200.csv` | 200 | 23 KB | Random sample for quick testing (no label) |

Notes:
- Labels are based on ACTC (rig control system), not sensor heuristics — independent ground truth
- 98.7% of rows receive a label (1.3% skipped due to ambiguous/unknown ACTC codes)
- Dataset breakdown: ~1.8M drilling (24%) vs ~5.5M not-drilling (76%)
- The 4,000 n-shot samples are excluded from inference and quick test files
- Random seed is fixed (42) for reproducibility

### Step 3: Convert CSV to JSONL (for Nano Inference)

The Nano Inference pipeline requires JSONL input. Convert CSV sensor data to JSONL with drilling analyst prompts:

```bash
# Convert 200 rows for a quick test (recommended starting point)
python 1_prepare_data/convert_to_inference_jsonl.py data/volve_inference.csv data/volve_nano_200.jsonl --max-rows 200

# Convert a larger batch
python 1_prepare_data/convert_to_inference_jsonl.py data/volve_inference.csv data/volve_nano_1000.jsonl --max-rows 1000
```

Each output line has `system` (with sensor definitions), `instruction`, and `prompt` fields:
```json
{"system": "You are a drilling operations analyst...", "instruction": "Describe the current rig state...", "prompt": "BPOS: 10.02, DBTM: 259.92, ..."}
```

> **Note:** Use `--max-rows` to limit the output size. Nano Inference generates up to 256 tokens per row, so large files (millions of rows) will take a very long time or timeout. Start with 200-1000 rows and scale up as needed. Omitting `--max-rows` converts all 7.4M rows, which is not recommended for Nano Inference.

### Workflow

```
1. Upload n-shot examples (volve_drilling.csv, volve_not_drilling.csv)
2. Upload inference data (volve_inference.csv)
3. Run batch job:
   a. Machine State — classify drilling vs. not-drilling (CSV input)
   b. Nano Inference — describe rig state in natural language (JSONL input)
4. Download outputs and evaluate predictions
```

## 4. Upload Files

The multipart upload uses a 3-step presigned URL flow:

```
1. POST /v0.5/files/uploads/initiate     → server returns presigned S3 URLs
2. PUT  each part to presigned URL        → upload directly to S3, collect ETags
3. POST /v0.5/files/uploads/{id}/complete → finalize with ETags
```

The server automatically selects `simple` (single PUT) or `multipart` (chunked) strategy based on file size.

Upload all prepared files:

### Python

```bash
# Machine State pipeline files
python 2_upload/upload_multipart.py data/volve_drilling.csv
python 2_upload/upload_multipart.py data/volve_not_drilling.csv
python 2_upload/upload_multipart.py data/volve_inference.csv

# Quick test for Machine State pipeline (200-row sample)
python 2_upload/upload_multipart.py data/volve_quick_test_200.csv

# Quick test for Nano Inference pipeline (200 prompts)
python 2_upload/upload_multipart.py data/volve_nano_200.jsonl
```

### Shell Script

```bash
chmod +x 2_upload/upload_multipart.sh

# Machine State pipeline files
./2_upload/upload_multipart.sh data/volve_drilling.csv
./2_upload/upload_multipart.sh data/volve_not_drilling.csv
./2_upload/upload_multipart.sh data/volve_inference.csv

# Quick test for Machine State pipeline (200-row sample)
./2_upload/upload_multipart.sh data/volve_quick_test_200.csv

# Quick test for Nano Inference pipeline (200 prompts)
./2_upload/upload_multipart.sh data/volve_nano_200.jsonl
```

### curl Commands

Step-by-step curl commands for manual execution. See [2_upload/upload_multipart_curl.md](2_upload/upload_multipart_curl.md).

```bash
# Initiate upload for each file
for FILE in volve_drilling.csv volve_not_drilling.csv volve_inference.csv volve_quick_test_200.csv; do
  FILE_SIZE=$(stat -f%z "data/$FILE")
  curl -s -X POST "$BASE_URL/files/uploads/initiate" \
    -H "Authorization: Bearer $ATAI_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"filename\":\"$FILE\",\"file_type\":\"text/csv\",\"num_bytes\":$FILE_SIZE}"
  echo
done

# JSONL file for Nano Inference (small enough for simple upload)
curl -s -X POST "$BASE_URL/files" \
  -H "Authorization: Bearer $ATAI_API_KEY" \
  -F "file=@data/volve_nano_200.jsonl;type=text/plain"
```

## 5. Batch Jobs

Create and monitor batch jobs via `POST /v0.5/jos/jobs`. Two pipeline types are available:

### Pipeline 1: Machine State Job Pipeline

Classifies time-series sensor data using n-shot examples. Uses the Newton foundation model to vectorize sensor windows, then a KNN classifier to predict machine state.

**Pipeline key:** `machine-state-job-pipeline`

**Available model types:**
- `omega_1_3_surface` — surface sensor monitoring (9 channels)
- `omega_1_3_power_drive` — downhole power drive monitoring (9 channels)

**Input ports:**
- `worker.inference` — files to classify
- `worker.n_shots` — labeled example files with `metadata.class`

**Config:**
```yaml
worker:
  parallelism: 1
  config:
    model_type: "omega_1_3_surface"
    batch_size: 8
    timestamp_column: "DATE_TIME"
    data_columns:
      - "BPOS"
      - "DBTM"
      - "FLWI"
      - "HDTH"
      - "HKLD"
      - "ROP"
      - "RPM"
      - "SPPA"
      - "WOB"
    reader_config:
      window_size: 64
      step_size: 1
    classifier_config:
      n_neighbors: 5
      metric: "euclidean"
      weights: "uniform"
    flush_every_n_iteration: 1000
```

**Prerequisites:** Upload files first (see [step 4](#4-upload-files)). The scripts reference files by name on the platform.

**Notes:**
- Both models expect exactly **9 sensor channels** — using more or fewer columns will cause shape mismatch errors
- `window_size` must be set appropriately (e.g., 64) — a value of 1 causes tensor shape errors
- `step_size` for n-shot files must be small enough to produce sufficient windows for the classifier (e.g., `step_size: 1` with 2000 n-shot rows and `window_size: 64` yields ~1936 windows)

#### Quick test (200-row sample)

Uses `volve_quick_test_200.csv` with the same n-shot files — fast way to verify the pipeline works:

```bash
curl -s -X POST "$BASE_URL/jos/jobs" \
  -H "Authorization: Bearer $ATAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "volve-quick-test",
    "pipeline_type": "batch",
    "pipeline_key": "machine-state-job-pipeline",
    "inputs": {
      "worker.inference": [{"file_id": "volve_quick_test_200.csv"}],
      "worker.n_shots": [
        {"file_id": "volve_drilling.csv", "metadata": {"class": "drilling"}},
        {"file_id": "volve_not_drilling.csv", "metadata": {"class": "not_drilling"}}
      ]
    },
    "parameters": {
      "worker": {
        "parallelism": 1,
        "config": {
          "batch_size": 8,
          "classifier_config": {"metric": "euclidean", "n_neighbors": 5, "weights": "uniform"},
          "data_columns": ["BPOS","DBTM","FLWI","HDTH","HKLD","ROP","RPM","SPPA","WOB"],
          "flush_every_n_iteration": 1000,
          "model_type": "omega_1_3_surface",
          "reader_config": {"step_size": 1, "window_size": 64},
          "timestamp_column": "DATE_TIME"
        }
      }
    }
  }'
```

#### Full run (7.3M rows)

Uses `volve_inference.csv` — takes several hours on GPU:

**Python:**
```bash
python 3_batch_jobs/create_machine_state_job.py
```

**Shell:**
```bash
chmod +x 3_batch_jobs/create_machine_state_job.sh
./3_batch_jobs/create_machine_state_job.sh
```

**curl:**
```bash
curl -s -X POST "$BASE_URL/jos/jobs" \
  -H "Authorization: Bearer $ATAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "volve-drilling-classification",
    "pipeline_type": "batch",
    "pipeline_key": "machine-state-job-pipeline",
    "inputs": {
      "worker.inference": [{"file_id": "volve_inference.csv"}],
      "worker.n_shots": [
        {"file_id": "volve_drilling.csv", "metadata": {"class": "drilling"}},
        {"file_id": "volve_not_drilling.csv", "metadata": {"class": "not_drilling"}}
      ]
    },
    "parameters": { ... }
  }'
```

See also: [3_batch_jobs/create_machine_state_job_curl.md](3_batch_jobs/create_machine_state_job_curl.md) for the full curl walkthrough.

### Pipeline 2: Nano Inference Pipeline

Text generation inference using Newton's language capabilities on input data files.

**Pipeline key:** `nano-inference-pipeline`

**Input ports:**
- `worker.data` — JSONL files (not raw CSV)

**Input format:** Each line must be a JSON object with `system`, `instruction`, and/or `prompt` fields:
```json
{"system": "You are a helpful assistant.", "instruction": "Answer concisely.", "prompt": "What is the capital of France?"}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `system` | string | No | System prompt |
| `instruction` | string | No | Task instruction |
| `prompt` | string | No | User prompt / input text |
| `inputs` | array | No | Multimodal inputs (images, video) |

At least one text field should be non-empty. See [input format reference](https://github.com/archetypeai/atai_core/tree/main/services/jos_service/nano_inference#input-format). To convert CSV data to JSONL, see [step 3](#step-3-convert-csv-to-jsonl-for-nano-inference).

**Prerequisites:** Upload `volve_nano_200.jsonl` first (see [step 4](#4-upload-files)).

**Config:**
```yaml
worker:
  parallelism: 1
  config:
    generation:
      do_sample: true
      max_new_tokens: 256
      repetition_penalty: 1
      temperature: 0.7
      top_k: 20
      top_p: 0.8
```

#### Quick test (200 prompts)

Uses `volve_nano_200.jsonl` — completes in a few minutes:

**Python:**
```bash
python 3_batch_jobs/create_nano_inference_job.py
```

**Shell:**
```bash
chmod +x 3_batch_jobs/create_nano_inference_job.sh
./3_batch_jobs/create_nano_inference_job.sh
```

**curl:**
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
  }'
```

See also: [3_batch_jobs/create_nano_inference_job_curl.md](3_batch_jobs/create_nano_inference_job_curl.md) for the full curl walkthrough.

**Important notes:**
- Raw CSV input will result in `"error": "parse error"` for every line — must use JSONL format
- The base Newton model (without fine-tuning) may not interpret sensor abbreviations correctly. Include sensor definitions in the `system` prompt for better results.
- For classification tasks, use **Machine State Pipeline** instead — it works out of the box with n-shot examples
- Large files (millions of rows) will timeout — keep batches to 200-1000 rows

### Monitoring Jobs

```bash
# Check status (PENDING → RUNNING → COMPLETED / FAILED / CANCELLED)
curl -s "$BASE_URL/jos/jobs/$JOB_ID" -H "Authorization: Bearer $ATAI_API_KEY"

# View events/logs
curl -s "$BASE_URL/jos/jobs/$JOB_ID/events" -H "Authorization: Bearer $ATAI_API_KEY"

# List all jobs
curl -s "$BASE_URL/jos/jobs" -H "Authorization: Bearer $ATAI_API_KEY"
```

See also: [3_batch_jobs/create_machine_state_job.py](3_batch_jobs/create_machine_state_job.py), [3_batch_jobs/create_machine_state_job.sh](3_batch_jobs/create_machine_state_job.sh), [3_batch_jobs/create_nano_inference_job.py](3_batch_jobs/create_nano_inference_job.py)

### Downloading Outputs

Job outputs are available via `GET /v0.5/jos/jobs/{job_id}/outputs` which returns paginated output metadata with presigned S3 download URLs (1-hour expiry, no auth needed).

```bash
python 4_download_outputs/download_outputs.py <job_id> outputs/
# or
./4_download_outputs/download_outputs.sh <job_id> outputs/
```

See also: [4_download_outputs/download_outputs_curl.md](4_download_outputs/download_outputs_curl.md)

## 6. Evaluation

### Machine State Pipeline

Compare Machine State predictions against ACTC-based ground truth labels.

**Prerequisite:** Generate labels first (see [step 2 of data prep](#step-2-generate-labels-and-split-data)):
```bash
python 1_prepare_data/generate_labels.py
```

#### Quick test evaluation

```bash
python 5_evaluate/evaluate_results.py <quick_test_job_id>
```

Quick test results (200-row sample, ACTC-based labels):

```
  Predictions:           137
  Matched:               137

  Confusion Matrix
                         Pred Drill  Pred Not-Drill
  Actual Drill                   10              25
  Actual Not-Drill               20              82

  Accuracy:           0.6715  (92 / 137)
  Precision:          0.3333  (drilling)
  Recall:             0.2857  (drilling)
  F1 Score:           0.3077

  Drilling predictions:             30  (21.9%)
  Not-drilling predictions:        107  (78.1%)
```

**67% accuracy** — the model correctly classifies most not-drilling states. It's biased toward "not_drilling" (78% of predictions), which reflects the dataset distribution (76% not-drilling). The model is conservative about predicting "drilling," resulting in lower recall for that class.

#### Full run evaluation

```bash
python 5_evaluate/evaluate_results.py <full_run_job_id>
```

This downloads all output chunks (may take several minutes for large jobs), matches predictions to ACTC ground truth labels via timestamps, and produces a confusion matrix, accuracy, precision, recall, and F1 score. Full run results will be more representative than the 200-row quick test.

### Nano Inference Pipeline

Nano Inference outputs are natural language descriptions, not classification labels, so there's no automated evaluation. Download the outputs and review manually:

```bash
python 4_download_outputs/download_outputs.py <nano_job_id> outputs/
```

Each output line contains:
```json
{"line_index": 0, "prediction": "Based on the sensor readings, the rig appears to be idle..."}
```

## 7. Config Optimization

Before fine-tuning, you can improve results by optimizing the Machine State pipeline config. The optimizer script runs a grid search over key hyperparameters using the 200-row quick test dataset:

```bash
python 3_batch_jobs/optimize_config.py
```

This searches over:

| Parameter | Values | Description |
|-----------|--------|-------------|
| `window_size` | 16, 32, 64, 128 | Time steps per classification window |
| `n_neighbors` | 3, 5, 7, 11 | KNN neighbors for classification |
| `metric` | euclidean, cosine, manhattan | Distance metric |
| `weights` | uniform, distance | KNN weight function |

**96 combinations** — each takes ~30 seconds (most is model loading), so the full search completes in ~48 minutes.

For each combination, the script:
1. Creates a batch job with the config
2. Waits for completion
3. Downloads predictions and evaluates against ACTC ground truth
4. Tracks accuracy, precision, recall, and F1

Output:
- Ranked results table showing all combinations
- Best config printed as ready-to-use YAML
- Results saved to `data/optimization_results.json`

Once you find the best config, use it for the full run on `volve_inference.csv`.

## 8. Fine-Tuning

TBD — Fine-tuning endpoint (`/v0.5/internal/experiment/runner/jobs`) is not yet available on dev. See `1_prepare_data/convert_to_jsonl.py` for converting CSV training data to the required JSONL format.

## Data Attribution

The drilling sensor data used in these examples is from the **Equinor Volve Data Village**, released under a modified CC BY 4.0 license. The data may be used for commercial and non-commercial purposes but may not be resold.

> Data provided by Equinor and the former Volve license partners (ExxonMobil Exploration & Production Norway AS and Bayerngas Norge AS). [Terms and Conditions](https://www.equinor.com/energy/volve-data-sharing).

## API Reference

### Files API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v0.5/files/uploads/initiate` | POST | Initiate upload, get presigned URLs |
| `{presigned_url}` | PUT | Upload part directly to S3 |
| `/v0.5/files/uploads/{upload_id}/complete` | POST | Finalize upload with ETags |
| `/v0.5/files/uploads/{upload_id}/abort` | POST | Cancel in-progress upload |
| `/v0.5/files` | POST | Simple upload (< 255 MB) |
| `/v0.5/files/info` | GET | List file storage summary |
| `/v0.5/files/metadata` | GET | List all file metadata |

### Batch Jobs API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v0.5/jos/jobs` | POST | Create a batch job |
| `/v0.5/jos/jobs` | GET | List all jobs |
| `/v0.5/jos/jobs/{job_id}` | GET | Get job status |
| `/v0.5/jos/jobs/{job_id}/events` | GET | Get job events/logs |
| `/v0.5/jos/jobs/{job_id}/outputs` | GET | List output artifacts (paginated, presigned URLs) |

## License

Apache 2.0
