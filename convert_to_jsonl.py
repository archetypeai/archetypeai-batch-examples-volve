#!/usr/bin/env python3
"""
Convert HIGGS CSV to JSONL format for Newton fine-tuning.

Usage:
    python convert_to_jsonl.py data/higgs_train.csv data/higgs_train.jsonl
    python convert_to_jsonl.py data/higgs_train.csv data/higgs_train.jsonl --max-rows 1000
"""

import csv
import json
import os
import sys
import time

INSTRUCTION = (
    "You are a particle physics classifier. Given sensor measurements from a "
    "particle detector, classify whether the collision produced a Higgs boson.\n"
    "Respond with 'boson' or 'no_boson'.\n"
)

LABEL_MAP = {"1": "boson", "0": "no_boson"}

FEATURE_COLUMNS = [
    "lepton_pT", "lepton_eta", "lepton_phi",
    "missing_energy_magnitude", "missing_energy_phi",
    "jet_1_pt", "jet_1_eta", "jet_1_phi", "jet_1_b-tag",
    "jet_2_pt", "jet_2_eta", "jet_2_phi", "jet_2_b-tag",
    "jet_3_pt", "jet_3_eta", "jet_3_phi", "jet_3_b-tag",
    "jet_4_pt", "jet_4_eta", "jet_4_phi", "jet_4_b-tag",
    "m_jj", "m_jjj", "m_lv", "m_jlv", "m_bb", "m_wbb", "m_wwbb",
]


def row_to_example(row: dict) -> dict:
    """Convert a CSV row to a fine-tuning example."""
    # Build input text from features
    features_text = ", ".join(
        f"{col}: {float(row[col]):.6f}" for col in FEATURE_COLUMNS
    )

    label = LABEL_MAP[row["label"]]

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
            if "label" not in row:
                continue
            example = row_to_example(row)
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
