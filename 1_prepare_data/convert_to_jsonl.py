#!/usr/bin/env python3
"""
Convert drilling CSV to JSONL format for Newton fine-tuning.

Usage:
    python convert_to_jsonl.py data/volve_drilling.csv data/volve_train.jsonl
    python convert_to_jsonl.py data/volve_drilling.csv data/volve_train.jsonl --max-rows 1000

Expects CSV with columns: DATE_TIME, BPOS, DBTM, FLWI, HDTH, HKLD, ROP, RPM, SPPA, WOB
and a 'label' column with values 'drilling' or 'not_drilling'.
"""

import csv
import json
import os
import sys
import time

INSTRUCTION = (
    "You are a drilling operations analyst. Given sensor measurements from a "
    "drilling rig, classify whether the rig is actively drilling or not.\n"
    "Respond with 'drilling' or 'not_drilling'.\n"
)

FEATURE_COLUMNS = [
    "BPOS", "DBTM", "FLWI", "HDTH", "HKLD",
    "ROP", "RPM", "SPPA", "WOB",
]


def row_to_example(row: dict, label: str) -> dict:
    """Convert a CSV row to a fine-tuning example."""
    features_text = ", ".join(
        f"{col}: {row[col]}" for col in FEATURE_COLUMNS
    )

    event_data = {
        "lens_parameters": {
            "instruction": INSTRUCTION,
            "inputs": [
                {
                    "type": "data.text",
                    "event_data": {"contents": features_text},
                }
            ],
            "outputs": [
                {
                    "type": "data.text",
                    "event_data": {"contents": label},
                }
            ],
        }
    }

    return {
        "type": "data.example",
        "event_data": json.dumps(event_data),
    }


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <input.csv> <output.jsonl> [--max-rows N] [--label LABEL]")
        print()
        print("  --label LABEL  Assign this label to all rows (e.g., 'drilling' or 'not_drilling').")
        print("                 If omitted, expects a 'label' column in the CSV.")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    max_rows = None
    if "--max-rows" in sys.argv:
        max_rows = int(sys.argv[sys.argv.index("--max-rows") + 1])

    fixed_label = None
    if "--label" in sys.argv:
        fixed_label = sys.argv[sys.argv.index("--label") + 1]

    print(f"Input:  {input_path}")
    print(f"Output: {output_path}")
    if max_rows:
        print(f"Max rows: {max_rows:,}")
    if fixed_label:
        print(f"Label:  {fixed_label}")
    print()

    t0 = time.time()
    count = 0

    with open(input_path, "r") as fin, open(output_path, "w") as fout:
        reader = csv.DictReader(fin)
        for row in reader:
            label = fixed_label or row.get("label", "")
            if not label:
                continue
            example = row_to_example(row, label)
            fout.write(json.dumps(example) + "\n")
            count += 1
            if count % 100_000 == 0:
                print(f"  Converted {count:,} rows...")
            if max_rows and count >= max_rows:
                break

    elapsed = time.time() - t0
    size = os.path.getsize(output_path)
    if size >= 1024 ** 3:
        size_str = f"{size / 1024**3:.2f} GB"
    elif size >= 1024 ** 2:
        size_str = f"{size / 1024**2:.0f} MB"
    else:
        size_str = f"{size / 1024:.0f} KB"

    print(f"\nDone! {count:,} examples in {elapsed:.1f}s ({size_str})")


if __name__ == "__main__":
    main()
