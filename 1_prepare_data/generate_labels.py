#!/usr/bin/env python3
"""
Generate ground truth labels for volve_inference.csv using ACTC rig mode codes
from the per-well CSVs.

Usage:
    python 1_prepare_data/generate_labels.py

Reads:
    data/volve_csv/*.csv  (per-well CSVs with ACTC column)
    data/volve_inference.csv

Outputs:
    data/volve_inference_labeled.csv  (volve_inference.csv + label column)

ACTC mapping:
    drilling:      ACTC in {1, 2}     (Drilling, Reaming)
    not_drilling:  ACTC in {3, 4, 8, 9} (Off Bottom, In Slips, Trip In Slips, Shut In)
    skipped:       ACTC in {-1, 0, 5, 19, 20, empty} (ambiguous/unknown)
"""

import csv
import glob
import os
import time

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
WELL_CSV_DIR = os.path.join(DATA_DIR, "volve_csv")
INFERENCE_FILE = os.path.join(DATA_DIR, "volve_inference.csv")
OUTPUT_FILE = os.path.join(DATA_DIR, "volve_inference_labeled.csv")

DRILLING_CODES = {"1", "1.0", "2", "2.0"}
NOT_DRILLING_CODES = {"3", "3.0", "4", "4.0", "8", "8.0", "9", "9.0"}


def main():
    print("=" * 60)
    print(" Generate Ground Truth Labels")
    print("=" * 60)
    print()

    # Step 1: Build timestamp → ACTC lookup from per-well CSVs
    print("[1/3] Loading ACTC codes from per-well CSVs...")
    t0 = time.time()

    actc_lookup = {}
    well_files = sorted(glob.glob(os.path.join(WELL_CSV_DIR, "*.csv")))

    for f in well_files:
        with open(f) as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                ts = row.get("DATE_TIME", "").strip()
                actc = row.get("ACTC", "").strip()
                if ts and actc:
                    actc_lookup[ts] = actc

    print(f"  Loaded {len(actc_lookup):,} ACTC entries from {len(well_files)} wells ({time.time() - t0:.1f}s)")
    print()

    # Step 2: Map ACTC to labels
    print("[2/3] Mapping ACTC codes to labels...")

    drilling_count = 0
    not_drilling_count = 0
    skipped_count = 0

    label_lookup = {}
    for ts, actc in actc_lookup.items():
        if actc in DRILLING_CODES:
            label_lookup[ts] = "drilling"
            drilling_count += 1
        elif actc in NOT_DRILLING_CODES:
            label_lookup[ts] = "not_drilling"
            not_drilling_count += 1
        else:
            skipped_count += 1

    print(f"  drilling:     {drilling_count:>10,}")
    print(f"  not_drilling: {not_drilling_count:>10,}")
    print(f"  skipped:      {skipped_count:>10,}  (ambiguous/unknown ACTC)")
    print()

    # Step 3: Add labels to volve_inference.csv
    print("[3/3] Writing labeled inference file...")
    t0 = time.time()

    labeled = 0
    unlabeled = 0
    total = 0

    with open(INFERENCE_FILE) as fin, open(OUTPUT_FILE, "w", newline="") as fout:
        reader = csv.DictReader(fin)
        fieldnames = reader.fieldnames + ["label"]
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()

        for row in reader:
            total += 1
            ts = row["DATE_TIME"]
            label = label_lookup.get(ts, "")

            if label:
                row["label"] = label
                writer.writerow(row)
                labeled += 1
            else:
                unlabeled += 1

            if total % 1_000_000 == 0:
                print(f"    Processed {total:,} rows...")

    size = os.path.getsize(OUTPUT_FILE)
    if size >= 1024 ** 3:
        size_str = f"{size / 1024**3:.2f} GB"
    elif size >= 1024 ** 2:
        size_str = f"{size / 1024**2:.0f} MB"
    else:
        size_str = f"{size / 1024:.0f} KB"

    print(f"  Write time: {time.time() - t0:.1f}s")
    print()
    print("=" * 60)
    print(" Summary")
    print("=" * 60)
    print(f"  Input:         {INFERENCE_FILE}")
    print(f"  Output:        {OUTPUT_FILE}")
    print(f"  Total rows:    {total:,}")
    print(f"  Labeled:       {labeled:,} ({labeled/total*100:.1f}%)")
    print(f"  Unlabeled:     {unlabeled:,} ({unlabeled/total*100:.1f}%)  (no ACTC or ambiguous)")
    print(f"  File size:     {size_str}")


if __name__ == "__main__":
    main()
