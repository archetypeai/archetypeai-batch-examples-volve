#!/usr/bin/env python3
"""
Convert Volve WITSML XML files to SLB-format CSVs for Archetype AI batch processing.

Usage:
    python volve_to_csv.py

Reads WITSML XML log files from data/volve/ and outputs:
    data/volve_csv/          - Per-well CSVs in SLB format
    data/volve_drilling.csv  - N-shot examples (drilling class)
    data/volve_not_drilling.csv - N-shot examples (not-drilling class)
    data/volve_inference.csv - Inference data (all wells combined)

Column mapping (Volve mnemonic -> SLB column):
    TIME -> DATE_TIME, BPOS -> BPOS, DBTM -> DBTM, TFLO -> FLWI,
    DMEA -> HDTH, HKLD -> HKLD, ROP -> ROP, RPM -> RPM,
    SPPA -> SPPA, SWOB -> WOB
"""

import csv
import glob
import os
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
VOLVE_DIR = os.path.join(DATA_DIR, "volve", "WITSML Realtime drilling data")
OUTPUT_DIR = os.path.join(DATA_DIR, "volve_csv")

NS = {"w": "http://www.witsml.org/schemas/1series"}

# Volve mnemonic -> SLB column name
CHANNEL_MAP = {
    "BPOS": "BPOS",
    "DBTM": "DBTM",
    "TFLO": "FLWI",
    "DMEA": "HDTH",
    "HKLD": "HKLD",
    "ROP": "ROP",
    "RPM": "RPM",
    "SPPA": "SPPA",
    "SWOB": "WOB",
}

# Extra channel for labeling (not included in model input)
LABEL_CHANNEL = "ACTC"

SLB_COLUMNS = ["DATE_TIME", "BPOS", "DBTM", "FLWI", "HDTH", "HKLD", "ROP", "RPM", "SPPA", "WOB"]
REQUIRED_MNEMONICS = set(CHANNEL_MAP.keys())

# Drilling heuristic thresholds (on raw values)
DRILLING_ROP_MIN = 0.0
DRILLING_RPM_MIN = 0.0
DRILLING_SPPA_MIN = 0.0

# N-shot sample sizes
N_SHOT_ROWS = 2000


def parse_witsml_log(xml_path: str) -> tuple:
    """Parse a WITSML XML log file. Returns (mnemonics, rows) or (None, None) if unusable."""
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError:
        return None, None

    root = tree.getroot()
    log_data = root.find(".//w:logData", NS)
    if log_data is None:
        return None, None

    mnem_list_el = log_data.find("w:mnemonicList", NS)
    if mnem_list_el is None or mnem_list_el.text is None:
        return None, None

    mnemonics = mnem_list_el.text.split(",")

    # Check if this log has enough of our target channels
    mnem_set = set(mnemonics)
    overlap = REQUIRED_MNEMONICS & mnem_set
    if len(overlap) < 5:  # Need at least 5 of 9 channels
        return None, None

    # Build index map
    idx_map = {}
    for i, m in enumerate(mnemonics):
        if m in CHANNEL_MAP or m == "TIME" or m == LABEL_CHANNEL:
            idx_map[m] = i

    if "TIME" not in idx_map:
        return None, None

    # Parse data rows
    rows = []
    for data_el in log_data.findall("w:data", NS):
        if data_el.text is None:
            continue
        values = data_el.text.split(",")
        row = {}

        # Parse timestamp
        time_str = values[idx_map["TIME"]] if idx_map["TIME"] < len(values) else ""
        if not time_str:
            continue
        try:
            dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            row["DATE_TIME"] = int(dt.timestamp())
        except (ValueError, OSError):
            continue

        # Parse sensor channels (always output as float for consistent typing)
        has_data = False
        for volve_mnem, slb_col in CHANNEL_MAP.items():
            if volve_mnem in idx_map and idx_map[volve_mnem] < len(values):
                val = values[idx_map[volve_mnem]]
                if val:
                    try:
                        row[slb_col] = f"{float(val)}"
                    except ValueError:
                        row[slb_col] = ""
                        continue
                    has_data = True
                else:
                    row[slb_col] = ""
            else:
                row[slb_col] = ""

        # Parse ACTC (rig mode) if available
        if LABEL_CHANNEL in idx_map and idx_map[LABEL_CHANNEL] < len(values):
            row["ACTC"] = values[idx_map[LABEL_CHANNEL]]
        else:
            row["ACTC"] = ""

        if has_data:
            rows.append(row)

    return mnemonics, rows


def is_drilling(row: dict) -> bool:
    """Heuristic: is this row from an active drilling period?"""
    try:
        rop = float(row.get("ROP", "") or 0)
        rpm = float(row.get("RPM", "") or 0)
        sppa = float(row.get("SPPA", "") or 0)
        return rop > DRILLING_ROP_MIN and rpm > DRILLING_RPM_MIN and sppa > DRILLING_SPPA_MIN
    except (ValueError, TypeError):
        return False


def row_is_complete(row: dict) -> bool:
    """Check if a row has all 9 sensor values (non-empty)."""
    for col in SLB_COLUMNS[1:]:  # Skip DATE_TIME
        if not row.get(col, ""):
            return False
    return True


def main():
    print("=" * 60)
    print(" Volve WITSML to SLB CSV Converter")
    print("=" * 60)
    print()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Find all wells
    well_dirs = sorted(glob.glob(os.path.join(VOLVE_DIR, "*")))
    well_dirs = [d for d in well_dirs if os.path.isdir(d)]

    print(f"Found {len(well_dirs)} well directories")
    print()

    # Process each well
    all_rows = []
    well_stats = []
    t0 = time.time()

    for well_dir in well_dirs:
        well_name = os.path.basename(well_dir)
        xml_files = sorted(glob.glob(os.path.join(well_dir, "**", "*.xml"), recursive=True))
        log_files = [f for f in xml_files if "/log/" in f]

        if not log_files:
            continue

        well_rows = []
        usable_files = 0

        for xml_path in log_files:
            mnemonics, rows = parse_witsml_log(xml_path)
            if rows:
                well_rows.extend(rows)
                usable_files += 1

        if not well_rows:
            continue

        # Sort by timestamp
        well_rows.sort(key=lambda r: r["DATE_TIME"])

        # Deduplicate by timestamp
        seen_ts = set()
        deduped = []
        for row in well_rows:
            ts = row["DATE_TIME"]
            if ts not in seen_ts:
                seen_ts.add(ts)
                deduped.append(row)
        well_rows = deduped

        # Write per-well CSV
        well_csv = os.path.join(OUTPUT_DIR, f"{well_name}.csv")
        with open(well_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=SLB_COLUMNS + ["ACTC"])
            writer.writeheader()
            for row in well_rows:
                writer.writerow({col: row.get(col, "") for col in SLB_COLUMNS + ["ACTC"]})

        complete_rows = [r for r in well_rows if row_is_complete(r)]
        drilling_rows = [r for r in complete_rows if is_drilling(r)]
        not_drilling_rows = [r for r in complete_rows if not is_drilling(r)]

        stat = {
            "well": well_name,
            "files": usable_files,
            "rows": len(well_rows),
            "complete": len(complete_rows),
            "drilling": len(drilling_rows),
            "not_drilling": len(not_drilling_rows),
        }
        well_stats.append(stat)
        all_rows.extend(complete_rows)

        print(f"  {well_name}")
        print(f"    {usable_files} files -> {len(well_rows):,} rows "
              f"({len(complete_rows):,} complete, "
              f"{len(drilling_rows):,} drilling, {len(not_drilling_rows):,} not-drilling)")

    print()
    print(f"  Total: {len(all_rows):,} complete rows from {len(well_stats)} wells ({time.time() - t0:.1f}s)")
    print()

    # Sort all rows by timestamp
    all_rows.sort(key=lambda r: r["DATE_TIME"])

    # Split into drilling / not-drilling
    drilling = [r for r in all_rows if is_drilling(r)]
    not_drilling = [r for r in all_rows if not is_drilling(r)]

    print(f"  Drilling rows:     {len(drilling):,}")
    print(f"  Not-drilling rows: {len(not_drilling):,}")
    print()

    # Create n-shot files (sample from each class)
    import random
    random.seed(42)

    n_shot_drill = random.sample(drilling, min(N_SHOT_ROWS, len(drilling)))
    n_shot_not_drill = random.sample(not_drilling, min(N_SHOT_ROWS, len(not_drilling)))

    # Remove n-shot rows from inference pool
    nshot_timestamps = set(r["DATE_TIME"] for r in n_shot_drill + n_shot_not_drill)
    inference_rows = [r for r in all_rows if r["DATE_TIME"] not in nshot_timestamps]

    # Write n-shot files
    for filename, rows in [
        ("volve_drilling.csv", n_shot_drill),
        ("volve_not_drilling.csv", n_shot_not_drill),
    ]:
        path = os.path.join(DATA_DIR, filename)
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=SLB_COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow({col: row.get(col, "") for col in SLB_COLUMNS})
        size = os.path.getsize(path)
        print(f"  Wrote {filename}: {len(rows):,} rows ({size / 1024:.0f} KB)")

    # Write inference file
    inference_path = os.path.join(DATA_DIR, "volve_inference.csv")
    with open(inference_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SLB_COLUMNS)
        writer.writeheader()
        for row in inference_rows:
            writer.writerow({col: row.get(col, "") for col in SLB_COLUMNS})
    size = os.path.getsize(inference_path)
    if size >= 1024 ** 3:
        size_str = f"{size / 1024**3:.2f} GB"
    elif size >= 1024 ** 2:
        size_str = f"{size / 1024**2:.0f} MB"
    else:
        size_str = f"{size / 1024:.0f} KB"
    print(f"  Wrote volve_inference.csv: {len(inference_rows):,} rows ({size_str})")

    print()
    print("=" * 60)
    print(" Summary")
    print("=" * 60)
    print(f"  Wells processed:     {len(well_stats)}")
    print(f"  Total complete rows: {len(all_rows):,}")
    print(f"  N-shot drilling:     {len(n_shot_drill):,} rows")
    print(f"  N-shot not-drilling: {len(n_shot_not_drill):,} rows")
    print(f"  Inference:           {len(inference_rows):,} rows")
    print()
    print(f"  Output directory:    {OUTPUT_DIR}/")
    print(f"  N-shot files:        data/volve_drilling.csv, data/volve_not_drilling.csv")
    print(f"  Inference file:      data/volve_inference.csv")
    print()
    print("  Attribution: Data from Equinor Volve Data Village (CC BY 4.0 modified).")
    print("  https://www.equinor.com/energy/volve-data-sharing")


if __name__ == "__main__":
    main()
