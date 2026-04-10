# Archetype AI Batch Processing Examples

Examples for batch upload, batch inference, and batch fine-tuning on the Archetype AI platform using real-world drilling sensor data.

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

> **Note:** If you'd rather skip the download and conversion steps, the prepared CSV files are already included in `data/` — see `volve_drilling.csv`, `volve_not_drilling.csv`, `volve_inference.csv`, and `volve_nano_30.jsonl`.

## 3. Prepare Data

Convert the raw WITSML XML files to CSV format and split into n-shot examples and inference data:

```bash
python 1_prepare_data/volve_to_csv.py
```

This parses 7,150 WITSML XML files across 14 wells and produces:

| File | Rows | Size | Description |
|------|------|------|-------------|
| `volve_drilling.csv` | 2,000 | 253 KB | N-shot examples — drilling class |
| `volve_not_drilling.csv` | 2,000 | 226 KB | N-shot examples — not-drilling class |
| `volve_inference.csv` | 7,415,900 | 845 MB | All wells combined — for batch inference |
| `volve_csv/*.csv` | varies | varies | Per-well CSVs (with ACTC rig mode column) |

Notes:
- Drilling/not-drilling classification uses a sensor heuristic: `ROP > 0 AND RPM > 0 AND SPPA > 0`
- The 4,000 n-shot samples are excluded from the inference file
- Dataset breakdown: ~2M drilling rows (27%) vs ~5.4M not-drilling rows (73%)
- Random seed is fixed (42) for reproducibility
- Column names are mapped to match the `omega_1_3_surface` model's expected format

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

# Nano Inference pipeline files
python 2_upload/upload_multipart.py data/volve_nano_30.jsonl

# Quick test file (30-row sample)
python 2_upload/upload_multipart.py data/volve_drilling_30.csv
```

### Shell Script

```bash
chmod +x 2_upload/upload_multipart.sh

# Machine State pipeline files
./2_upload/upload_multipart.sh data/volve_drilling.csv
./2_upload/upload_multipart.sh data/volve_not_drilling.csv
./2_upload/upload_multipart.sh data/volve_inference.csv

# Nano Inference pipeline files
./2_upload/upload_multipart.sh data/volve_nano_30.jsonl

# Quick test file (30-row sample)
./2_upload/upload_multipart.sh data/volve_drilling_30.csv
```

### curl Commands

Step-by-step curl commands for manual execution. See [2_upload/upload_multipart_curl.md](2_upload/upload_multipart_curl.md).

```bash
# Initiate upload for each file
for FILE in volve_drilling.csv volve_not_drilling.csv volve_inference.csv volve_drilling_30.csv; do
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
  -F "file=@data/volve_nano_30.jsonl;type=text/plain"
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

**Prerequisites:** Upload `volve_drilling.csv`, `volve_not_drilling.csv`, and `volve_inference.csv` first (see [step 4](#4-upload-files)). The scripts reference these files by name on the platform.

**Notes:**
- Both models expect exactly **9 sensor channels** — using more or fewer columns will cause shape mismatch errors
- `window_size` must be set appropriately (e.g., 64) — a value of 1 causes tensor shape errors
- `step_size` for n-shot files must be small enough to produce sufficient windows for the classifier (e.g., `step_size: 1` with 2000 n-shot rows and `window_size: 64` yields ~1936 windows)

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

At least one text field should be non-empty. See [input format reference](https://github.com/archetypeai/atai_core/tree/main/services/jos_service/nano_inference#input-format).

Use `convert_to_inference_jsonl.py` to convert CSV data to the required JSONL format:
```bash
python 1_prepare_data/convert_to_inference_jsonl.py data/volve_inference.csv data/volve_inference.jsonl --max-rows 100
```

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

**Python:**
```bash
python 3_batch_jobs/create_nano_inference_job.py
```

**Shell:**
```bash
chmod +x 3_batch_jobs/create_nano_inference_job.sh
./3_batch_jobs/create_nano_inference_job.sh
```

See also: [3_batch_jobs/create_nano_inference_job_curl.md](3_batch_jobs/create_nano_inference_job_curl.md) for the full curl walkthrough.

**Important notes:**
- Raw CSV input will result in `"error": "parse error"` for every line — must use JSONL format
- The base Newton model (without fine-tuning) produces generic responses, not useful analysis. **Fine-tuning is required** to teach Newton how to respond to specific tasks.
- For classification tasks, use **Machine State Pipeline** instead — it works out of the box with n-shot examples
- Large files (millions of rows) may timeout — test with small batches first

### Monitoring Jobs

```bash
# Check status (PENDING → RUNNING → COMPLETED / FAILED / CANCELLED)
curl -s "$BASE_URL/jos/jobs/$JOB_ID" -H "Authorization: Bearer $ATAI_API_KEY"

# View events/logs
curl -s "$BASE_URL/jos/jobs/$JOB_ID/events" -H "Authorization: Bearer $ATAI_API_KEY"

# List all jobs
curl -s "$BASE_URL/jos/jobs" -H "Authorization: Bearer $ATAI_API_KEY"
```

See also: [examples/create_batch_job.py](examples/create_batch_job.py), [3_batch_jobs/create_machine_state_job.sh](3_batch_jobs/create_machine_state_job.sh), [3_batch_jobs/create_machine_state_job_curl.md](3_batch_jobs/create_machine_state_job_curl.md)

### Downloading Outputs

Job outputs are available via `GET /v0.5/jos/jobs/{job_id}/outputs` which returns paginated output metadata with presigned S3 download URLs (1-hour expiry, no auth needed).

```bash
python 4_download_outputs/download_outputs.py <job_id> outputs/
# or
./4_download_outputs/download_outputs.sh <job_id> outputs/
```

See also: [4_download_outputs/download_outputs_curl.md](4_download_outputs/download_outputs_curl.md)

## 6. Evaluation

Compare Machine State predictions against ground truth:

```bash
python 5_evaluate/evaluate_results.py <job_id>
```

This downloads all output artifacts, maps predictions back to original rows via the `TimePoint` (timestamp) column, and computes accuracy metrics (confusion matrix, precision, recall, F1 score).

## 7. Fine-Tuning

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
