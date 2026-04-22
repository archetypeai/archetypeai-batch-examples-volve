#!/usr/bin/env python3
"""
Convert drilling CSV to JSONL format for Activity Detection Pipeline.

Usage:
    python convert_to_activity_detection_jsonl.py data/volve_inference.csv data/volve_inference.jsonl --max-rows 100

Input format (per line):
    {"system": "...", "instruction": "...", "prompt": "..."}

See: https://github.com/archetypeai/atai_core/tree/main/services/jos_service/nano_inference#input-format
"""

import csv
import json
import os
import sys
import time

SYSTEM = """You are a drilling operations analyst. You analyze real-time sensor data from oil and gas drilling rigs.

Sensor channel definitions:
- BPOS: Block Position — height of the traveling block (m)
- DBTM: Bit Depth — depth of the drill bit below surface (m)
- FLWI: Flow In — mud flow rate pumped into the hole (L/min)
- HDTH: Hole Depth — total depth of the hole drilled so far (m)
- HKLD: Hookload — weight hanging from the hook/traveling block (kkgf)
- ROP: Rate of Penetration — speed at which the hole gets deeper (m/h)
- RPM: Rotary Speed — drill string rotation speed (rpm)
- SPPA: Standpipe Pressure — mud pump pressure (kPa)
- WOB: Weight on Bit — downward force applied to the drill bit (kkgf)"""

INSTRUCTION = "Describe the current rig state based on these sensor readings. What activity is the rig performing? Are there any notable patterns or concerns?"

FEATURE_COLUMNS = [
    "BPOS", "DBTM", "FLWI", "HDTH", "HKLD",
    "ROP", "RPM", "SPPA", "WOB",
]


def row_to_record(row: dict) -> dict:
    """Convert a CSV row to a Activity Detection record."""
    features_text = ", ".join(
        f"{col}: {row[col]}" for col in FEATURE_COLUMNS
    )
    return {
        "system": SYSTEM,
        "instruction": INSTRUCTION,
        "prompt": features_text,
    }


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <input.csv> <output.jsonl> [--max-rows N]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    max_rows = None
    if "--max-rows" in sys.argv:
        max_rows = int(sys.argv[sys.argv.index("--max-rows") + 1])

    print(f"Input:  {input_path}")
    print(f"Output: {output_path}")
    if max_rows:
        print(f"Max rows: {max_rows:,}")
    print()

    t0 = time.time()
    count = 0

    with open(input_path, "r") as fin, open(output_path, "w") as fout:
        reader = csv.DictReader(fin)
        for row in reader:
            record = row_to_record(row)
            fout.write(json.dumps(record) + "\n")
            count += 1
            if count % 100_000 == 0:
                print(f"  Converted {count:,} rows...")
            if max_rows and count >= max_rows:
                break

    elapsed = time.time() - t0
    size = os.path.getsize(output_path)
    size_str = f"{size / 1024:.0f} KB" if size < 1024**2 else f"{size / 1024**2:.0f} MB"

    print(f"\nDone! {count:,} records in {elapsed:.1f}s ({size_str})")


if __name__ == "__main__":
    main()
