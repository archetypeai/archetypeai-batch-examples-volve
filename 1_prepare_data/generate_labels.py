#!/usr/bin/env python3
"""
Generate contiguous n-shot files, inference file, quick test, and optimizer
slice from volve_raw.csv.

Usage:
    python 1_prepare_data/generate_labels.py

Reads:
    data/volve_raw.csv

Output:
    data/volve_raw_labeled.csv      - All ACTC-labeled rows (sorted by DATE_TIME)
    data/volve_drilling.csv         - 2,000-row contiguous shot (longest drilling run)
    data/volve_not_drilling.csv     - 2,000-row contiguous shot (longest not_drilling run)
    data/volve_inference.csv        - Full labeled CSV minus the two shot row ranges
    data/volve_quick_test_200.csv   - 200-row contiguous block (cheap pipeline sanity check)
    data/volve_opt_slice.csv        - Class-balanced contiguous slice for the optimizer
                                      (2,000 drilling + 2,000 not_drilling)

Key changes from earlier random-sample prep:
  * Shots are 2,000 consecutive rows from a single time-AND-label contiguous
    run, preserving the temporal structure the omega model relies on.
    Previously, shots were `random.sample(drilling_rows, 2000)` etc -- rows
    scattered across 7.3M rows spanning 750 days and 14 wells. Preflight
    FAILed `timestamp_monotonic` on both shot files; the inference file
    ended up with 4,000 random per-row holes which the sliding window
    silently glues across.
  * Inference excludes only the two shot row ranges -- two clean contiguous
    holes instead of thousands of random per-row holes.
  * Adds volve_opt_slice.csv (class-balanced contiguous slice) for the
    96-combo grid search, mirroring the archetypeai-batch-examples-3w
    @24cae3f opt_slice pattern. A single-class quick test gives the
    optimizer no F1 signal; a class-balanced slice does.

ACTC label mapping:
    drilling:      ACTC in {1, 2}        (Drilling, Reaming)
    not_drilling:  ACTC in {3, 4, 8, 9}  (Off Bottom, In Slips, Trip In Slips, Shut In)
    skipped:       ACTC in {-1, 0, 5, 19, 20, empty} (ambiguous/unknown)

Run detection:
    volve_raw.csv is sorted globally by DATE_TIME across 14 wells whose
    recording periods overlap. We split class runs on:
      - label change
      - delta > 60s (well-boundary gap; median delta is 5s, p99.9 is 42s)
      - delta < 1s (timestamp collision between wells)
      - well_id change (if the volve_raw.csv has a well_id column)
    well_id is emitted by the newer volve_to_csv.py. If volve_raw.csv was
    produced by an older volve_to_csv.py without that column, we fall back
    to delta-based splitting only (which still catches well-boundary gaps
    but cannot detect the ~61K rows / 0.85% where two wells recorded at the
    same instant). Re-run volve_to_csv.py to enable strict per-well splits.
"""

import argparse
import csv
import json
import math
import os
import sys
import time

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
RAW_FILE = os.path.join(DATA_DIR, "volve_raw.csv")
LABELED_FILE = os.path.join(DATA_DIR, "volve_raw_labeled.csv")
ZSCORE_STATS_FILE = os.path.join(DATA_DIR, "volve_zscore_stats.json")

DRILLING_CODES = {"1", "1.0", "2", "2.0"}
NOT_DRILLING_CODES = {"3", "3.0", "4", "4.0", "8", "8.0", "9", "9.0"}

SENSOR_COLUMNS = ["DATE_TIME", "BPOS", "DBTM", "FLWI", "HDTH", "HKLD", "ROP", "RPM", "SPPA", "WOB"]
# The 9 physical channels (excludes DATE_TIME). These get z-scored; DATE_TIME stays raw.
SENSOR_NUMERIC_COLUMNS = ["BPOS", "DBTM", "FLWI", "HDTH", "HKLD", "ROP", "RPM", "SPPA", "WOB"]
LABELED_COLUMNS = SENSOR_COLUMNS + ["label"]
WELL_ID_COL = "well_id"  # optional; emitted by the newer volve_to_csv.py

N_SHOT_PER_CLASS = 2000
QUICK_TEST_SIZE = 200
OPT_SLICE_PER_CLASS = 2000

# Within-run timestamp delta limits (seconds). Splits runs when crossed.
MAX_DELTA = 60   # p99.9 of deltas in volve_raw_labeled.csv is 42s; 60s is generous
MIN_DELTA = 1    # delta == 0 means a duplicate-ts collision (two wells at same instant)

CLASS_NAMES = ["drilling", "not_drilling"]


def fmt_size(nbytes):
    if nbytes >= 1024 ** 3:
        return f"{nbytes / 1024**3:.2f} GB"
    if nbytes >= 1024 ** 2:
        return f"{nbytes / 1024**2:.0f} MB"
    return f"{nbytes / 1024:.0f} KB"


def label_for_actc(actc: str) -> str:
    actc = actc.strip()
    if actc in DRILLING_CODES:
        return "drilling"
    if actc in NOT_DRILLING_CODES:
        return "not_drilling"
    return ""  # skipped


def find_class_runs(rows: list, use_well_id: bool) -> dict:
    """Return {class: [(start_idx, end_idx, length), ...]} sorted by length desc.

    Splits on: label change, delta > MAX_DELTA, delta < MIN_DELTA, or (if
    use_well_id) a change in well_id. The well_id split is the strongest
    safeguard: without it the global-by-DATE_TIME sort can silently interleave
    rows from two wells whose recording periods overlap.
    """
    runs = {c: [] for c in CLASS_NAMES}
    if not rows:
        return runs

    current_label = rows[0]["label"]
    current_well = rows[0].get(WELL_ID_COL, "") if use_well_id else None
    current_start = 0
    prev_ts = int(rows[0]["DATE_TIME"])
    n = len(rows)

    for i in range(1, n):
        ts = int(rows[i]["DATE_TIME"])
        label = rows[i]["label"]
        well = rows[i].get(WELL_ID_COL, "") if use_well_id else None
        delta = ts - prev_ts
        split = (
            label != current_label
            or delta > MAX_DELTA
            or delta < MIN_DELTA
            or (use_well_id and well != current_well)
        )
        if split:
            length = i - current_start
            if current_label in runs:
                runs[current_label].append((current_start, i, length))
            current_label = label
            current_well = well
            current_start = i
        prev_ts = ts

    # final
    length = n - current_start
    if current_label in runs:
        runs[current_label].append((current_start, n, length))

    for cls in runs:
        runs[cls].sort(key=lambda r: r[2], reverse=True)
    return runs


def compute_zscore_stats(rows: list) -> tuple:
    """Compute global per-channel mean and std across all labeled rows.

    Returns (means, stds) as dicts keyed by column name. Standard deviations
    < 1e-12 are clamped to 1.0 to avoid division-by-zero on constant columns.
    """
    sums = {c: 0.0 for c in SENSOR_NUMERIC_COLUMNS}
    sumsq = {c: 0.0 for c in SENSOR_NUMERIC_COLUMNS}
    counts = {c: 0 for c in SENSOR_NUMERIC_COLUMNS}
    for row in rows:
        for c in SENSOR_NUMERIC_COLUMNS:
            v = row.get(c, "")
            if v == "" or v is None:
                continue
            try:
                x = float(v)
            except ValueError:
                continue
            if math.isnan(x):
                continue
            sums[c] += x
            sumsq[c] += x * x
            counts[c] += 1
    means = {}
    stds = {}
    for c in SENSOR_NUMERIC_COLUMNS:
        n = counts[c]
        if n == 0:
            means[c] = 0.0
            stds[c] = 1.0
            continue
        m = sums[c] / n
        var = max(0.0, sumsq[c] / n - m * m)
        s = math.sqrt(var)
        means[c] = m
        stds[c] = s if s >= 1e-12 else 1.0
    return means, stds


def write_csv(path: str, rows: list, fields: list, means: dict = None, stds: dict = None):
    """Write rows to a CSV. If means/stds are provided, z-score the
    SENSOR_NUMERIC_COLUMNS in-place per row using `(x - mean) / std`.
    DATE_TIME, label, and any other non-numeric columns pass through.
    """
    zscore = means is not None and stds is not None
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            out = {}
            for col in fields:
                v = row.get(col, "")
                if zscore and col in SENSOR_NUMERIC_COLUMNS and v != "" and v is not None:
                    try:
                        x = float(v)
                        out[col] = f"{(x - means[col]) / stds[col]:.6f}"
                        continue
                    except ValueError:
                        pass
                out[col] = v
            writer.writerow(out)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Generate contiguous n-shot, inference, quick-test, and opt-slice "
            "files for the Volve drilling dataset. Z-scoring is applied by "
            "default; pass --no-zscore to skip it (recommended when running on "
            "the fine-tuned omega_1_3_surface encoder, whose training "
            "distribution matched raw drilling-sensor scales — see README)."
        )
    )
    parser.add_argument(
        "--no-zscore",
        dest="zscore",
        action="store_false",
        help="Skip global per-channel z-scoring. Output CSVs keep raw sensor "
             "values; volve_zscore_stats.json is not written.",
    )
    parser.set_defaults(zscore=True)
    args = parser.parse_args()

    print("=" * 60)
    print(" Generate Contiguous N-Shot, Inference, Quick Test, and Opt-Slice (Volve)")
    print("=" * 60)
    print()

    if not os.path.exists(RAW_FILE):
        print(f"  ERROR: {RAW_FILE} not found.")
        print(f"  Run 'python 1_prepare_data/volve_to_csv.py' first.")
        sys.exit(1)

    # --- Stage 1: read + label + sort ---------------------------------------
    print("[1/5] Reading volve_raw.csv and assigning labels...")
    t0 = time.time()

    labeled = []
    total = skipped = 0
    has_well_id = False
    with open(RAW_FILE) as f:
        reader = csv.DictReader(f)
        has_well_id = WELL_ID_COL in (reader.fieldnames or [])
        for row in reader:
            total += 1
            label = label_for_actc(row.get("ACTC", ""))
            if not label:
                skipped += 1
                continue
            row["label"] = label
            labeled.append(row)
            if total % 1_000_000 == 0:
                print(f"    Read {total:,} rows...")

    labeled.sort(key=lambda r: int(r["DATE_TIME"]))
    print(f"      well_id column: {'PRESENT (per-well run detection enabled)' if has_well_id else 'MISSING (falling back to delta-based run detection; re-run volve_to_csv.py to get strict per-well splits)'}")
    counts = {c: 0 for c in CLASS_NAMES}
    for r in labeled:
        counts[r["label"]] += 1
    print(f"  Total: {total:,}  Labeled: {len(labeled):,}  Skipped: {skipped:,}")
    for c in CLASS_NAMES:
        print(f"    {c}: {counts[c]:,} ({100 * counts[c] / len(labeled):.1f}% of labeled)")
    print(f"  ({time.time() - t0:.1f}s)")
    print()

    # --- Stage 1b: (optionally) compute global z-score stats ----------------
    if args.zscore:
        print("      Computing per-channel z-score stats over labeled rows...")
        t0 = time.time()
        means, stds = compute_zscore_stats(labeled)
        stats_doc = {
            "n_rows": len(labeled),
            "columns": SENSOR_NUMERIC_COLUMNS,
            "mean": {c: means[c] for c in SENSOR_NUMERIC_COLUMNS},
            "std": {c: stds[c] for c in SENSOR_NUMERIC_COLUMNS},
        }
        with open(ZSCORE_STATS_FILE, "w") as f:
            json.dump(stats_doc, f, indent=2)
        print(f"      stats written to {os.path.basename(ZSCORE_STATS_FILE)}  ({time.time() - t0:.1f}s)")
        for c in SENSOR_NUMERIC_COLUMNS:
            print(f"        {c:<6} mean={means[c]:>14.3f}  std={stds[c]:>14.3f}")
        print()
        label_suffix = " (z-scored)"
    else:
        means, stds = None, None
        print("      --no-zscore: skipping z-score computation; output CSVs will contain raw values")
        # Remove any stale stats file so consumers don't think the data is z-scored.
        if os.path.exists(ZSCORE_STATS_FILE):
            os.remove(ZSCORE_STATS_FILE)
            print(f"      removed stale {os.path.basename(ZSCORE_STATS_FILE)}")
        print()
        label_suffix = " (raw values)"

    # Write the labeled CSV (sensor columns + label, sorted by DATE_TIME)
    print(f"      Writing volve_raw_labeled.csv{label_suffix}...")
    t0 = time.time()
    write_csv(LABELED_FILE, labeled, LABELED_COLUMNS, means=means, stds=stds)
    print(f"      {len(labeled):,} rows  {fmt_size(os.path.getsize(LABELED_FILE))}  "
          f"({time.time() - t0:.1f}s)")
    print()

    # --- Stage 2: find class runs --------------------------------------------
    split_criteria = ("delta <= 60s, label-contiguous"
                      + (", well_id-contiguous" if has_well_id else ""))
    print(f"[2/5] Finding class runs ({split_criteria})...")
    t0 = time.time()
    runs = find_class_runs(labeled, use_well_id=has_well_id)
    for cls in CLASS_NAMES:
        top = runs[cls][:3]
        print(f"      {cls}: {len(runs[cls]):,} runs, top 3 lengths = "
              f"{[r[2] for r in top]}")
    print(f"  ({time.time() - t0:.1f}s)")

    # Sanity allocation: need at least 3 runs per class long enough for
    # shot (2000) + opt_slice (2000) + quick_test (200).
    for cls in CLASS_NAMES:
        if len(runs[cls]) < 3:
            print(f"  ERROR: {cls} has only {len(runs[cls])} runs, need >= 3")
            sys.exit(1)
        if runs[cls][0][2] < N_SHOT_PER_CLASS:
            print(f"  ERROR: longest {cls} run is {runs[cls][0][2]} rows, "
                  f"need {N_SHOT_PER_CLASS} for shot")
            sys.exit(1)
        if runs[cls][1][2] < OPT_SLICE_PER_CLASS:
            print(f"  ERROR: 2nd-longest {cls} run is {runs[cls][1][2]} rows, "
                  f"need {OPT_SLICE_PER_CLASS} for opt_slice")
            sys.exit(1)
        if runs[cls][2][2] < QUICK_TEST_SIZE:
            print(f"  ERROR: 3rd-longest {cls} run is {runs[cls][2][2]} rows, "
                  f"need {QUICK_TEST_SIZE} for quick test")
            sys.exit(1)
    print()

    # --- Stage 3: shots ------------------------------------------------------
    print(f"[3/5] Writing contiguous shots ({N_SHOT_PER_CLASS} rows each)...")
    t0 = time.time()

    shot_ranges = {}
    for cls in CLASS_NAMES:
        run = runs[cls][0]  # longest
        s = run[0]
        e = s + N_SHOT_PER_CLASS
        shot_ranges[cls] = (s, e)
        path = os.path.join(DATA_DIR, f"volve_{cls}.csv")
        write_csv(path, labeled[s:e], SENSOR_COLUMNS, means=means, stds=stds)
        print(f"  volve_{cls}.csv{' ' * (24 - len(cls))} {N_SHOT_PER_CLASS:>6} rows  "
              f"src=longest {cls} run (idx [{s},{e})){label_suffix}")
    print(f"  ({time.time() - t0:.1f}s)")
    print()

    # --- Stage 4: inference (labeled minus shot ranges) ----------------------
    print("[4/5] Writing volve_inference.csv (labeled minus shot ranges)...")
    t0 = time.time()

    excluded_idx = set()
    for cls, (s, e) in shot_ranges.items():
        excluded_idx.update(range(s, e))

    inference_path = os.path.join(DATA_DIR, "volve_inference.csv")
    inference_rows = [r for i, r in enumerate(labeled) if i not in excluded_idx]
    write_csv(inference_path, inference_rows, SENSOR_COLUMNS, means=means, stds=stds)
    print(f"  volve_inference.csv  {len(inference_rows):,} rows  "
          f"(excluded {len(labeled) - len(inference_rows):,} shot rows)  "
          f"{fmt_size(os.path.getsize(inference_path))}{label_suffix}  ({time.time() - t0:.1f}s)")
    print()

    # --- Stage 5: quick test + opt_slice -------------------------------------
    print(f"[5/5] Writing volve_quick_test_200.csv and volve_opt_slice.csv...")
    t0 = time.time()

    # quick_test: 200 contiguous rows from the 3rd-longest drilling run
    qt_run = runs["drilling"][2]
    qt_s = qt_run[0]
    qt_e = qt_s + QUICK_TEST_SIZE
    qt_path = os.path.join(DATA_DIR, "volve_quick_test_200.csv")
    write_csv(qt_path, labeled[qt_s:qt_e], SENSOR_COLUMNS, means=means, stds=stds)
    print(f"  volve_quick_test_200.csv  {QUICK_TEST_SIZE} rows  "
          f"(from 3rd-longest drilling run, idx [{qt_s},{qt_e}))")

    # opt_slice: 2,000 from 2nd-longest drilling + 2,000 from 2nd-longest not_drilling
    opt_drill = runs["drilling"][1]
    opt_nd = runs["not_drilling"][1]
    opt_drill_part = labeled[opt_drill[0]:opt_drill[0] + OPT_SLICE_PER_CLASS]
    opt_nd_part = labeled[opt_nd[0]:opt_nd[0] + OPT_SLICE_PER_CLASS]
    opt_path = os.path.join(DATA_DIR, "volve_opt_slice.csv")
    write_csv(opt_path, opt_drill_part + opt_nd_part, SENSOR_COLUMNS, means=means, stds=stds)
    print(f"  volve_opt_slice.csv       {2 * OPT_SLICE_PER_CLASS:,} rows  "
          f"({OPT_SLICE_PER_CLASS} drilling from 2nd-longest drilling run, "
          f"{OPT_SLICE_PER_CLASS} not_drilling from 2nd-longest not_drilling run)")
    print(f"  ({time.time() - t0:.1f}s)")
    print()

    # --- Summary -------------------------------------------------------------
    print("=" * 60)
    print(" Summary")
    print("=" * 60)
    print(f"  volve_raw_labeled.csv     {len(labeled):>10,} rows  (ground truth for evaluation)")
    print(f"  volve_drilling.csv        {N_SHOT_PER_CLASS:>10,} rows  (contiguous; longest drilling run)")
    print(f"  volve_not_drilling.csv    {N_SHOT_PER_CLASS:>10,} rows  (contiguous; longest not_drilling run)")
    print(f"  volve_inference.csv       {len(inference_rows):>10,} rows  "
          f"(full labeled CSV minus shot ranges)")
    print(f"  volve_quick_test_200.csv  {QUICK_TEST_SIZE:>10,} rows  "
          f"(contiguous from 3rd-longest drilling run)")
    print(f"  volve_opt_slice.csv       {2 * OPT_SLICE_PER_CLASS:>10,} rows  "
          f"(class-balanced contiguous slice)")
    print()
    print("Done! Next steps:")
    print("  python 1_prepare_data/convert_to_activity_detection_jsonl.py data/volve_inference.csv data/volve_activity_200.jsonl --max-rows 200")
    print("  python 2_upload/upload_multipart.py data/volve_inference.csv")


if __name__ == "__main__":
    main()
