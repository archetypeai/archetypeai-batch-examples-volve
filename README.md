# Archetype AI Batch Processing Examples

Examples for uploading large files to the Archetype AI platform using the new multipart presigned URL upload API.

## Setup

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

## Dataset

These examples use the [HIGGS dataset](https://archive.ics.uci.edu/dataset/280/higgs) (UCI ML Repository) — 11M rows, 7.5 GB CSV, binary classification (Higgs boson signal vs background).

### Download

```bash
mkdir -p data
curl -L -o data/higgs.zip https://archive.ics.uci.edu/static/public/280/higgs.zip
cd data && unzip higgs.zip && gunzip HIGGS.csv.gz && cd ..
```

### Prepare Data

Split the raw HIGGS.csv into files for n-shot examples, batch inference, fine-tuning, and evaluation:

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

## Upload API Flow

The multipart upload uses a 3-step presigned URL flow:

```
1. POST /v0.5/files/uploads/initiate   → server returns presigned S3 URLs
2. PUT  each part to presigned URL      → upload directly to S3, collect ETags
3. POST /v0.5/files/uploads/{id}/complete → finalize with ETags
```

The server automatically selects `simple` or `multipart` strategy based on file size.

## Examples

### 1. Python (`examples/upload_multipart.py`)

Full-featured upload with progress bar, speed tracking, and ETA.

```bash
python examples/upload_multipart.py data/HIGGS.csv
```

Output:
```
============================================================
 Archetype AI Multipart Upload
============================================================
 File:     HIGGS.csv
 Size:     7.49 GB (8,035,497,980 bytes)
 Endpoint: https://api.dev.u1.archetypeai.app/v0.5
============================================================

[1/3] Initiating upload...
      upload_id : upl_abc123...
      strategy  : multipart
      parts     : 20 x 400 MB

[2/3] Uploading 20 parts to S3...

  Part  1/20  [████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]   5.2%   0.39 GB/7.49 GB   45.2 MB/s  ETA   161s
  Part  2/20  [████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]  10.4%   0.78 GB/7.49 GB   42.1 MB/s  ETA   153s
  ...

[3/3] Completing upload...
      file_uid: fil_xyz789...
      status:   Registered
```

### 2. Shell Script (`examples/upload_multipart.sh`)

Bash implementation using `curl` and `dd` for chunked file reads.

```bash
chmod +x examples/upload_multipart.sh
./examples/upload_multipart.sh data/HIGGS.csv
```

Output:
```
============================================================
 Archetype AI Multipart Upload (Shell)
============================================================
 File:     HIGGS.csv
 Size:     7.49 GB (8035497980 bytes)

[1/3] Initiating upload...
      upload_id : upl_abc123...
      strategy  : multipart
      parts     : 20 x 400 MB

[2/3] Uploading 20 parts to S3...

  Part  1/20  [  5%]  0.39 GB/7.49 GB  45 MB/s  ETag: abc123def456...  ETA: 161s
  Part  2/20  [ 10%]  0.78 GB/7.49 GB  42 MB/s  ETag: 789ghi012jkl...  ETA: 153s
  ...

[3/3] Completing upload...
 DONE  file_uid: fil_xyz789...
```

### 3. curl Commands (`examples/upload_multipart_curl.md`)

Step-by-step curl commands for manual execution or integration into other tools. See [examples/upload_multipart_curl.md](examples/upload_multipart_curl.md).

```bash
# Quick initiate example
curl -s -X POST "$BASE_URL/files/uploads/initiate" \
  -H "Authorization: Bearer $ATAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"filename":"HIGGS.csv","file_type":"text/csv","num_bytes":8035497980}'
```

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v0.5/files/uploads/initiate` | POST | Initiate upload, get presigned URLs |
| `{presigned_url}` | PUT | Upload part directly to S3 |
| `/v0.5/files/uploads/{upload_id}/complete` | POST | Finalize upload with ETags |
| `/v0.5/files/uploads/{upload_id}/abort` | POST | Cancel in-progress upload |
| `/v0.5/files` | POST | Simple upload (< 255 MB) |
| `/v0.5/files/info` | GET | List file storage summary |
| `/v0.5/files/metadata` | GET | List all file metadata |

## License

Apache 2.0
