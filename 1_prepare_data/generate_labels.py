#!/usr/bin/env python3
"""
Step 2: Generate ACTC-based labels and split into n-shot + inference files.

Usage:
    python 1_prepare_data/generate_labels.py

Reads:  data/volve_raw.csv
Output:
    data/volve_raw_labeled.csv      - All rows with label column (for evaluation)
    data/volve_drilling.csv         - 2,000 n-shot drilling examples (no label)
    data/volve_not_drilling.csv     - 2,000 n-shot not-drilling examples (no label)
    data/volve_inference.csv        - Remaining rows for batch inference (no label)
    data/volve_quick_test_200.csv   - 200 random rows for quick testing (no label)

ACTC mapping:
    drilling:      ACTC in {1, 2}       (Drilling, Reaming)
    not_drilling:  ACTC in {3, 4, 8, 9} (Off Bottom, In Slips, Trip In Slips, Shut In)
    skipped:       ACTC in {-1, 0, 5, 19, 20, empty} (ambiguous/unknown)
"""

import csv
import os
import random
import time

random.seed(42)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
RAW_FILE = os.path.join(DATA_DIR, "volve_raw.csv")

DRILLING_CODES = {"1", "1.0", "2", "2.0"}
NOT_DRILLING_CODES = {"3", "3.0", "4", "4.0", "8", "8.0", "9", "9.0"}

SENSOR_COLUMNS = ["DATE_TIME", "BPOS", "DBTM", "FLWI", "HDTH", "HKLD", "ROP", "RPM", "SPPA", "WOB"]
N_SHOT_PER_CLASS = 2000
QUICK_TEST_SIZE = 200


def fmt_size(nbytes):
    if nbytes >= 1024 ** 3:
        return f"{nbytes / 1024**3:.2f} GB"
    if nbytes >= 1024 ** 2:
        return f"{nbytes / 1024**2:.0f} MB"
    return f"{nbytes / 1024:.0f} KB"


def main():
    print("=" * 60)
    print(" Step 2: Generate Labels and Split Data")
    print("=" * 60)
    print()

    # --- Read raw CSV and assign labels ---
    print("[1/3] Reading volve_raw.csv and assigning labels...")
    t0 = time.time()

    drilling_rows = []
    not_drilling_rows = []
    skipped = 0
    total = 0

    with open(RAW_FILE) as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            actc = row.get("ACTC", "").strip()

            if actc in DRILLING_CODES:
                row["label"] = "drilling"
                drilling_rows.append(row)
            elif actc in NOT_DRILLING_CODES:
                row["label"] = "not_drilling"
                not_drilling_rows.append(row)
            else:
                skipped += 1

            if total % 1_000_000 == 0:
                print(f"    Read {total:,} rows...")

    labeled_total = len(drilling_rows) + len(not_drilling_rows)
    print(f"  Total rows:    {total:,}")
    print(f"  Labeled:       {labeled_total:,} ({labeled_total/total*100:.1f}%)")
    print(f"    drilling:    {len(drilling_rows):,}")
    print(f"    not_drilling:{len(not_drilling_rows):,}")
    print(f"  Skipped:       {skipped:,} (ambiguous/unknown ACTC)")
    print(f"  Time: {time.time() - t0:.1f}s")
    print()

    # --- Write labeled CSV ---
    print("[2/3] Writing volve_raw_labeled.csv...")
    t0 = time.time()

    labeled_file = os.path.join(DATA_DIR, "volve_raw_labeled.csv")
    all_labeled = drilling_rows + not_drilling_rows
    all_labeled.sort(key=lambda r: int(r["DATE_TIME"]))

    with open(labeled_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SENSOR_COLUMNS + ["label"])
        writer.writeheader()
        for row in all_labeled:
            writer.writerow({col: row.get(col, "") for col in SENSOR_COLUMNS + ["label"]})

    print(f"  {len(all_labeled):,} rows, {fmt_size(os.path.getsize(labeled_file))} ({time.time() - t0:.1f}s)")
    print()

    # --- Split into n-shot + inference ---
    print("[3/3] Splitting into n-shot and inference files...")
    t0 = time.time()

    # Sample n-shots
    n_shot_drill = random.sample(drilling_rows, min(N_SHOT_PER_CLASS, len(drilling_rows)))
    n_shot_not_drill = random.sample(not_drilling_rows, min(N_SHOT_PER_CLASS, len(not_drilling_rows)))

    nshot_timestamps = set(r["DATE_TIME"] for r in n_shot_drill + n_shot_not_drill)

    # Remaining rows for inference
    inference_rows = [r for r in all_labeled if r["DATE_TIME"] not in nshot_timestamps]

    # Quick test sample from inference rows
    quick_test = random.sample(inference_rows, min(QUICK_TEST_SIZE, len(inference_rows)))

    # Write files (sensor columns only, no label)
    files_to_write = {
        "volve_drilling.csv": n_shot_drill,
        "volve_not_drilling.csv": n_shot_not_drill,
        "volve_inference.csv": inference_rows,
        "volve_quick_test_200.csv": quick_test,
    }

    for filename, rows in files_to_write.items():
        path = os.path.join(DATA_DIR, filename)
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=SENSOR_COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow({col: row.get(col, "") for col in SENSOR_COLUMNS})
        print(f"  {filename:<30} {len(rows):>10,} rows  {fmt_size(os.path.getsize(path)):>8}")

    print(f"\n  Time: {time.time() - t0:.1f}s")

    # --- Summary ---
    print()
    print("=" * 60)
    print(" Summary")
    print("=" * 60)
    print(f"  volve_raw_labeled.csv   {len(all_labeled):>10,} rows  (ground truth for evaluation)")
    print(f"  volve_drilling.csv      {len(n_shot_drill):>10,} rows  (n-shot: drilling)")
    print(f"  volve_not_drilling.csv  {len(n_shot_not_drill):>10,} rows  (n-shot: not_drilling)")
    print(f"  volve_inference.csv     {len(inference_rows):>10,} rows  (batch inference)")
    print(f"  volve_quick_test_200.csv{QUICK_TEST_SIZE:>10,} rows  (quick test)")
    print()
    print("  N-shot samples are excluded from inference and quick test files.")
    print()
    print("Done! Next steps:")
    print("  python 1_prepare_data/convert_to_activity_detection_jsonl.py data/volve_inference.csv data/volve_activity_200.jsonl --max-rows 200")
    print("  python 2_upload/upload_multipart.py data/volve_inference.csv")


if __name__ == "__main__":
    main()
