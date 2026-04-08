# Archetype AI Batch Processing Examples

Examples for batch upload, batch inference, and batch fine-tuning on the Archetype AI platform.

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

These examples use the [HIGGS dataset](https://archive.ics.uci.edu/dataset/280/higgs) (UCI ML Repository) — 11M rows, 7.5 GB CSV, binary classification (Higgs boson signal vs background).

```bash
mkdir -p data
curl -L -o data/higgs.zip https://archive.ics.uci.edu/static/public/280/higgs.zip
cd data && unzip higgs.zip && gunzip HIGGS.csv.gz && cd ..
```

## 3. Prepare Data

Split the raw `HIGGS.csv` into files for n-shot examples, batch inference, fine-tuning, and evaluation:

```bash
python prepare_data.py
```

This produces the following files in `data/`:

| File | Rows | Size | Description |
|------|------|------|-------------|
| `higgs_boson.csv` | 1,000 | 691 KB | N-shot examples — Higgs boson signal (label=1) |
| `higgs_no_boson.csv` | 1,000 | 691 KB | N-shot examples — background (label=0) |
| `higgs_no_label.csv` | 11,000,000 | 7.23 GB | All rows with label removed — for batch inference |
| `higgs_train.csv` | 8,798,400 | 5.80 GB | 80% training split — for fine-tuning Newton |
| `higgs_test_label.csv` | 2,199,600 | 1.45 GB | 20% test split with labels — ground truth |
| `higgs_test_no_label.csv` | 2,199,600 | 1.45 GB | 20% test split without labels — for inference |

Notes:
- All files include a header row with column names
- Labels are integer `1` (boson) / `0` (no boson)
- The 2,000 n-shot samples are excluded from train/test splits
- Dataset is roughly balanced: 5.83M boson vs 5.17M no-boson
- Random seed is fixed (42) for reproducibility

### Workflow

```
1. Upload n-shot examples (higgs_boson.csv, higgs_no_boson.csv) to Newton
2. Run batch inference on higgs_no_label.csv using Newton with n-shot examples
3. Fine-tune Newton with higgs_train.csv
4. Run batch inference on higgs_test_no_label.csv using fine-tuned Newton
5. Compare results against higgs_test_label.csv
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
python examples/upload_multipart.py data/higgs_no_label.csv
python examples/upload_multipart.py data/higgs_boson.csv
python examples/upload_multipart.py data/higgs_no_boson.csv
python examples/upload_multipart.py data/higgs_train.csv
python examples/upload_multipart.py data/higgs_test_no_label.csv
```

Output:
```
============================================================
 Archetype AI Multipart Upload
============================================================
 File:     higgs_no_label.csv
 Size:     7.23 GB (7,760,498,260 bytes)
 Endpoint: https://api.dev.u1.archetypeai.app/v0.5
============================================================

[1/3] Initiating upload...
      upload_id : upl_0h5k39kek18598nph15s7bgr2c
      file_uid  : fil_1xvbr0n4yd896s1hmhfj33h1wb
      strategy  : multipart
      parts     : 19 x 400 MB

[2/3] Uploading 19 parts to S3...

  Part  1/19  [██░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]   5.4%    400 MB/7.23 GB   31.8 MB/s  ETA   224s
  Part  2/19  [████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]  10.8%    800 MB/7.23 GB   30.7 MB/s  ETA   214s
  ...

[3/3] Completing upload...
      file_uid: fil_1xvbr0n4yd896s1hmhfj33h1wb
      status:   Registered
```

### Shell Script

```bash
chmod +x examples/upload_multipart.sh

./examples/upload_multipart.sh data/higgs_no_label.csv
./examples/upload_multipart.sh data/higgs_boson.csv
./examples/upload_multipart.sh data/higgs_no_boson.csv
./examples/upload_multipart.sh data/higgs_train.csv
./examples/upload_multipart.sh data/higgs_test_no_label.csv
```

### curl Commands

Step-by-step curl commands for manual execution. See [examples/upload_multipart_curl.md](examples/upload_multipart_curl.md).

```bash
# Initiate upload for each file
for FILE in higgs_no_label.csv higgs_boson.csv higgs_no_boson.csv higgs_train.csv higgs_test_no_label.csv; do
  FILE_SIZE=$(stat -f%z "data/$FILE")
  curl -s -X POST "$BASE_URL/files/uploads/initiate" \
    -H "Authorization: Bearer $ATAI_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"filename\":\"$FILE\",\"file_type\":\"text/csv\",\"num_bytes\":$FILE_SIZE}"
  echo
done
```

## Batch Job Examples

### 1. Python (`examples/create_batch_job.py`)

Creates a job, polls status, and displays events on completion.

```bash
python examples/create_batch_job.py
```

### 2. Shell Script (`examples/create_batch_job.sh`)

Bash implementation with status polling and event display.

```bash
chmod +x examples/create_batch_job.sh
./examples/create_batch_job.sh
```

### 3. curl Commands (`examples/create_batch_job_curl.md`)

Step-by-step curl commands. See [examples/create_batch_job_curl.md](examples/create_batch_job_curl.md).

```bash
# Quick create example
curl -s -X POST "$BASE_URL/jos/jobs" \
  -H "Authorization: Bearer $ATAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"my-job","pipeline_type":"batch","pipeline_key":"machine-state-job-pipeline","inputs":{...},"parameters":{...}}'

# Check status
curl -s "$BASE_URL/jos/jobs/$JOB_ID" -H "Authorization: Bearer $ATAI_API_KEY"

# View events
curl -s "$BASE_URL/jos/jobs/$JOB_ID/events" -H "Authorization: Bearer $ATAI_API_KEY"
```

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

## License

Apache 2.0
