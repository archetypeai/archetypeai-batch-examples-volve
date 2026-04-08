#!/usr/bin/env python3
"""
Prepare HIGGS.csv into multiple files for Archetype AI batch processing.

Outputs (in data/):
  1. higgs_boson.csv        - 1000 n-shot examples (label=1)
  2. higgs_no_boson.csv     - 1000 n-shot examples (label=0)
  3. higgs_no_label.csv     - All 11M rows, label column removed
  4. higgs_train.csv        - 80% of non-n-shot rows (with label)
  5. higgs_test_label.csv   - 20% of non-n-shot rows (with label)
  6. higgs_test_no_label.csv- Same rows as test_label but without label
"""

import os
import random
import time

random.seed(42)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
INPUT_FILE = os.path.join(DATA_DIR, "HIGGS.csv")

HEADER_FULL = "label,lepton_pT,lepton_eta,lepton_phi,missing_energy_magnitude,missing_energy_phi,jet_1_pt,jet_1_eta,jet_1_phi,jet_1_b-tag,jet_2_pt,jet_2_eta,jet_2_phi,jet_2_b-tag,jet_3_pt,jet_3_eta,jet_3_phi,jet_3_b-tag,jet_4_pt,jet_4_eta,jet_4_phi,jet_4_b-tag,m_jj,m_jjj,m_lv,m_jlv,m_bb,m_wbb,m_wwbb"
HEADER_NO_LABEL = ",".join(HEADER_FULL.split(",")[1:])

N_SHOT_PER_CLASS = 1000
TRAIN_RATIO = 0.80


def fmt_count(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def convert_label(raw_label):
    """Convert '1.000...' or '0.000...' to '1' or '0'."""
    return "1" if raw_label.startswith("1") else "0"


def strip_label(line):
    """Remove the label (first field) from a CSV line."""
    return line[line.index(",") + 1:]


def main():
    print("=" * 60)
    print(" HIGGS Data Preparation")
    print("=" * 60)
    print()

    # --- Pass 1: Collect indices by label --------------------------------
    print("[1/4] Scanning rows by label...")
    t0 = time.time()

    boson_indices = []
    no_boson_indices = []

    with open(INPUT_FILE, "r") as f:
        for i, line in enumerate(f):
            if line.startswith("1"):
                boson_indices.append(i)
            else:
                no_boson_indices.append(i)
            if (i + 1) % 1_000_000 == 0:
                print(f"  Scanned {fmt_count(i + 1)} rows...")

    total = i + 1
    print(f"  Total: {fmt_count(total)} rows "
          f"({fmt_count(len(boson_indices))} boson, {fmt_count(len(no_boson_indices))} no-boson)")
    print(f"  Scan time: {time.time() - t0:.1f}s")
    print()

    # --- Sample n-shot and split train/test ------------------------------
    print("[2/4] Sampling n-shot and splitting train/test...")

    nshot_boson = set(random.sample(boson_indices, N_SHOT_PER_CLASS))
    nshot_no_boson = set(random.sample(no_boson_indices, N_SHOT_PER_CLASS))
    nshot_all = nshot_boson | nshot_no_boson

    remaining_indices = [i for i in range(total) if i not in nshot_all]
    random.shuffle(remaining_indices)

    split_point = int(len(remaining_indices) * TRAIN_RATIO)
    train_set = set(remaining_indices[:split_point])
    test_set = set(remaining_indices[split_point:])

    print(f"  N-shot:  {len(nshot_boson)} boson + {len(nshot_no_boson)} no-boson = {len(nshot_all)}")
    print(f"  Train:   {fmt_count(len(train_set))} rows")
    print(f"  Test:    {fmt_count(len(test_set))} rows")
    print()

    # --- Pass 2: Write all output files ----------------------------------
    print("[3/4] Writing output files (single pass)...")
    t0 = time.time()

    paths = {
        "boson": os.path.join(DATA_DIR, "higgs_boson.csv"),
        "no_boson": os.path.join(DATA_DIR, "higgs_no_boson.csv"),
        "no_label": os.path.join(DATA_DIR, "higgs_no_label.csv"),
        "train": os.path.join(DATA_DIR, "higgs_train.csv"),
        "test_label": os.path.join(DATA_DIR, "higgs_test_label.csv"),
        "test_no_label": os.path.join(DATA_DIR, "higgs_test_no_label.csv"),
    }

    files = {k: open(p, "w") for k, p in paths.items()}

    # Write headers
    files["boson"].write(HEADER_FULL + "\n")
    files["no_boson"].write(HEADER_FULL + "\n")
    files["no_label"].write(HEADER_NO_LABEL + "\n")
    files["train"].write(HEADER_FULL + "\n")
    files["test_label"].write(HEADER_FULL + "\n")
    files["test_no_label"].write(HEADER_NO_LABEL + "\n")

    counts = {k: 0 for k in files}

    with open(INPUT_FILE, "r") as f:
        for i, line in enumerate(f):
            line = line.rstrip("\n")
            label = convert_label(line)
            features = strip_label(line)
            labeled_line = label + "," + features + "\n"
            features_line = features + "\n"

            # All rows go to no_label
            files["no_label"].write(features_line)
            counts["no_label"] += 1

            if i in nshot_boson:
                files["boson"].write(labeled_line)
                counts["boson"] += 1
            elif i in nshot_no_boson:
                files["no_boson"].write(labeled_line)
                counts["no_boson"] += 1
            elif i in train_set:
                files["train"].write(labeled_line)
                counts["train"] += 1
            elif i in test_set:
                files["test_label"].write(labeled_line)
                counts["test_label"] += 1
                files["test_no_label"].write(features_line)
                counts["test_no_label"] += 1

            if (i + 1) % 1_000_000 == 0:
                print(f"  Processed {fmt_count(i + 1)} rows...")

    for fh in files.values():
        fh.close()

    print(f"  Write time: {time.time() - t0:.1f}s")
    print()

    # --- Summary ---------------------------------------------------------
    print("[4/4] Summary")
    print()
    print(f"  {'File':<30} {'Rows':>12} {'Size':>10}")
    print(f"  {'-'*30} {'-'*12} {'-'*10}")
    for key, path in paths.items():
        size = os.path.getsize(path)
        if size >= 1024 ** 3:
            size_str = f"{size / 1024**3:.2f} GB"
        elif size >= 1024 ** 2:
            size_str = f"{size / 1024**2:.0f} MB"
        else:
            size_str = f"{size / 1024:.0f} KB"
        print(f"  {os.path.basename(path):<30} {counts[key]:>12,} {size_str:>10}")

    print()
    print("Done!")


if __name__ == "__main__":
    main()
