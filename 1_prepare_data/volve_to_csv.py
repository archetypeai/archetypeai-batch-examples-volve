#!/usr/bin/env python3
"""
Step 1: Convert Volve WITSML XML files to a single raw CSV.

Usage:
    python 1_prepare_data/volve_to_csv.py

Reads:  data/volve/WITSML Realtime drilling data/
Output: data/volve_raw.csv (all wells, 9 sensor columns + DATE_TIME + ACTC)
"""

import csv
import glob
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
VOLVE_DIR = os.path.join(DATA_DIR, "volve", "WITSML Realtime drilling data")
OUTPUT_FILE = os.path.join(DATA_DIR, "volve_raw.csv")

NS = {"w": "http://www.witsml.org/schemas/1series"}

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

LABEL_CHANNEL = "ACTC"
REQUIRED_MNEMONICS = set(CHANNEL_MAP.keys())
OUTPUT_COLUMNS = ["DATE_TIME", "BPOS", "DBTM", "FLWI", "HDTH", "HKLD", "ROP", "RPM", "SPPA", "WOB", "ACTC"]


def parse_witsml_log(xml_path: str) -> list:
    """Parse a WITSML XML log file. Returns list of row dicts or empty list."""
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError:
        return []

    root = tree.getroot()
    log_data = root.find(".//w:logData", NS)
    if log_data is None:
        return []

    mnem_list_el = log_data.find("w:mnemonicList", NS)
    if mnem_list_el is None or mnem_list_el.text is None:
        return []

    mnemonics = mnem_list_el.text.split(",")
    mnem_set = set(mnemonics)
    if len(REQUIRED_MNEMONICS & mnem_set) < 5:
        return []

    idx_map = {}
    for i, m in enumerate(mnemonics):
        if m in CHANNEL_MAP or m == "TIME" or m == LABEL_CHANNEL:
            idx_map[m] = i

    if "TIME" not in idx_map:
        return []

    rows = []
    for data_el in log_data.findall("w:data", NS):
        if data_el.text is None:
            continue
        values = data_el.text.split(",")
        row = {}

        time_str = values[idx_map["TIME"]] if idx_map["TIME"] < len(values) else ""
        if not time_str:
            continue
        try:
            dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            row["DATE_TIME"] = int(dt.timestamp())
        except (ValueError, OSError):
            continue

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

        if LABEL_CHANNEL in idx_map and idx_map[LABEL_CHANNEL] < len(values):
            row["ACTC"] = values[idx_map[LABEL_CHANNEL]]
        else:
            row["ACTC"] = ""

        if has_data:
            rows.append(row)

    return rows


def row_is_complete(row: dict) -> bool:
    """Check if a row has all 9 sensor values (non-empty)."""
    for col in OUTPUT_COLUMNS[1:-1]:  # Skip DATE_TIME and ACTC
        if not row.get(col, ""):
            return False
    return True


def main():
    print("=" * 60)
    print(" Step 1: Volve WITSML to Raw CSV")
    print("=" * 60)
    print()

    well_dirs = sorted(glob.glob(os.path.join(VOLVE_DIR, "*")))
    well_dirs = [d for d in well_dirs if os.path.isdir(d)]
    print(f"Found {len(well_dirs)} well directories")
    print()

    all_rows = []
    t0 = time.time()

    for well_dir in well_dirs:
        well_name = os.path.basename(well_dir)
        log_files = sorted(glob.glob(os.path.join(well_dir, "**", "*.xml"), recursive=True))
        log_files = [f for f in log_files if "/log/" in f]

        if not log_files:
            continue

        well_rows = []
        usable_files = 0

        for xml_path in log_files:
            rows = parse_witsml_log(xml_path)
            if rows:
                well_rows.extend(rows)
                usable_files += 1

        if not well_rows:
            continue

        # Deduplicate by timestamp
        seen_ts = set()
        deduped = []
        for row in well_rows:
            ts = row["DATE_TIME"]
            if ts not in seen_ts:
                seen_ts.add(ts)
                deduped.append(row)

        complete = [r for r in deduped if row_is_complete(r)]
        all_rows.extend(complete)

        print(f"  {well_name}: {usable_files} files -> {len(complete):,} complete rows")

    # Sort by timestamp
    all_rows.sort(key=lambda r: r["DATE_TIME"])

    print()
    print(f"  Total: {len(all_rows):,} rows ({time.time() - t0:.1f}s)")
    print()

    # Write raw CSV
    print(f"Writing {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for row in all_rows:
            writer.writerow({col: row.get(col, "") for col in OUTPUT_COLUMNS})

    size = os.path.getsize(OUTPUT_FILE)
    size_str = f"{size / 1024**2:.0f} MB" if size < 1024**3 else f"{size / 1024**3:.2f} GB"
    print(f"  {len(all_rows):,} rows, {size_str}")
    print()
    print("Done! Next step: python 1_prepare_data/generate_labels.py")


if __name__ == "__main__":
    main()
