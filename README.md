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

These examples use the [HIGGS dataset](https://archive.ics.uci.edu/dataset/280/higgs) (UCI ML Repository) — 11M rows, 7.5 GB CSV, binary classification.

```bash
# Download and extract
curl -L -o data/higgs.zip https://archive.ics.uci.edu/static/public/280/higgs.zip
cd data && unzip higgs.zip && gunzip HIGGS.csv.gz && cd ..
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
