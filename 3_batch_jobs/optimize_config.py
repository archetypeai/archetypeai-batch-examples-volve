#!/usr/bin/env python3
"""
Automatically optimize Machine State pipeline config by running iterations
with the quick test dataset (volve_quick_test_200.csv).

Usage:
    python 3_batch_jobs/optimize_config.py

Searches over window_size, n_neighbors, metric, and weights to find the
config that produces the best accuracy against ACTC ground truth labels.

Prerequisites:
    - Upload volve_quick_test_200.csv, volve_drilling.csv, volve_not_drilling.csv
    - Generate labels: python 1_prepare_data/generate_labels.py
"""

import csv
import io
import itertools
import json
import os
import sys
import time

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
with open(ENV_PATH) as f:
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k] = v

API_KEY = os.environ["ATAI_API_KEY"]
API_ENDPOINT = os.environ["ATAI_API_ENDPOINT"]
BASE_URL = f"{API_ENDPOINT}/v0.5"
AUTH = {"Authorization": f"Bearer {API_KEY}"}
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# ---------------------------------------------------------------------------
# Search grid
# ---------------------------------------------------------------------------
PARAM_GRID = {
    "window_size": [16, 32, 64, 128],
    "n_neighbors": [3, 5, 7, 11],
    "metric": ["euclidean", "cosine", "manhattan"],
    "weights": ["uniform", "distance"],
}

# Fixed params
FIXED_PARAMS = {
    "batch_size": 8,
    "data_columns": ["BPOS", "DBTM", "FLWI", "HDTH", "HKLD", "ROP", "RPM", "SPPA", "WOB"],
    "flush_every_n_iteration": 1000,
    "model_type": "omega_1_3_surface",
    "timestamp_column": "DATE_TIME",
}

INFERENCE_FILE = "volve_quick_test_200.csv"
N_SHOT_FILES = [
    {"file_id": "volve_drilling.csv", "metadata": {"class": "drilling"}},
    {"file_id": "volve_not_drilling.csv", "metadata": {"class": "not_drilling"}},
]

POSITIVE_CLASS = "drilling"
NEGATIVE_CLASS = "not_drilling"
TERMINAL_STATUSES = {"COMPLETED", "FAILED", "CANCELLED"}


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------
def create_job(name: str, config: dict) -> dict:
    payload = {
        "name": name,
        "pipeline_type": "batch",
        "pipeline_key": "machine-state-job-pipeline",
        "inputs": {
            "worker.inference": [{"file_id": INFERENCE_FILE}],
            "worker.n_shots": N_SHOT_FILES,
        },
        "parameters": {
            "worker": {
                "parallelism": 1,
                "config": config,
            }
        },
    }
    resp = requests.post(
        f"{BASE_URL}/jos/jobs",
        headers={**AUTH, "Content-Type": "application/json"},
        json=payload,
    )
    resp.raise_for_status()
    return resp.json()


def wait_for_job(job_id: str, poll_interval: int = 10) -> str:
    while True:
        resp = requests.get(f"{BASE_URL}/jos/jobs/{job_id}", headers=AUTH)
        resp.raise_for_status()
        status = resp.json()["status"]
        if status in TERMINAL_STATUSES:
            return status
        time.sleep(poll_interval)


def get_predictions(job_id: str) -> dict:
    predictions = {}
    offset = 0
    while True:
        resp = requests.get(
            f"{BASE_URL}/jos/jobs/{job_id}/outputs",
            headers=AUTH,
            params={"limit": 50, "offset": offset},
        )
        resp.raise_for_status()
        data = resp.json()
        for out in data["outputs"]:
            r = requests.get(out["data"]["ref"])
            r.raise_for_status()
            reader = csv.DictReader(io.StringIO(r.text))
            for row in reader:
                ts_key = "DATE_TIME" if "DATE_TIME" in row else "TimePoint"
                predictions[int(row[ts_key])] = row["Prediction"]
        if offset + 50 >= data["total"]:
            break
        offset += 50
    return predictions


def load_labels() -> dict:
    labels = {}
    labeled_file = os.path.join(DATA_DIR, "volve_raw_labeled.csv")
    with open(labeled_file) as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = int(row["DATE_TIME"])
            label = row.get("label", "").strip()
            if label in (POSITIVE_CLASS, NEGATIVE_CLASS):
                labels[ts] = label
    return labels


def evaluate(predictions: dict, labels: dict) -> dict:
    tp = fp = tn = fn = 0
    matched = 0
    for ts, pred in predictions.items():
        if ts not in labels:
            continue
        matched += 1
        actual = labels[ts]
        if pred == POSITIVE_CLASS and actual == POSITIVE_CLASS:
            tp += 1
        elif pred == POSITIVE_CLASS and actual == NEGATIVE_CLASS:
            fp += 1
        elif pred == NEGATIVE_CLASS and actual == NEGATIVE_CLASS:
            tn += 1
        elif pred == NEGATIVE_CLASS and actual == POSITIVE_CLASS:
            fn += 1

    total = tp + fp + tn + fn
    accuracy = (tp + tn) / total if total else 0
    precision = tp / (tp + fp) if (tp + fp) else 0
    recall = tp / (tp + fn) if (tp + fn) else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0

    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "matched": matched,
        "predictions": len(predictions),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 80)
    print(" Machine State Config Optimizer")
    print("=" * 80)
    print()

    # Load labels once
    print("Loading ground truth labels...")
    labels = load_labels()
    print(f"  {len(labels):,} labels loaded")
    print()

    # Generate all combinations
    keys = list(PARAM_GRID.keys())
    values = list(PARAM_GRID.values())
    combos = list(itertools.product(*values))
    total_combos = len(combos)

    print(f"Search grid: {' x '.join(f'{k}({len(v)})' for k, v in PARAM_GRID.items())}")
    print(f"Total combinations: {total_combos}")
    print()

    results = []
    start_time = time.time()

    for i, combo in enumerate(combos):
        params = dict(zip(keys, combo))
        config = {
            **FIXED_PARAMS,
            "reader_config": {"step_size": 1, "window_size": params["window_size"]},
            "classifier_config": {
                "n_neighbors": params["n_neighbors"],
                "metric": params["metric"],
                "weights": params["weights"],
            },
        }

        name = f"opt-w{params['window_size']}-k{params['n_neighbors']}-{params['metric'][:3]}-{params['weights'][:3]}"
        print(f"[{i+1}/{total_combos}] {name}...", end=" ", flush=True)

        try:
            # Create job
            job = create_job(name, config)
            job_id = job["id"]

            # Wait for completion
            status = wait_for_job(job_id)

            if status != "COMPLETED":
                print(f"FAILED ({status})")
                results.append({**params, "accuracy": 0, "f1": 0, "status": status, "job_id": job_id})
                continue

            # Evaluate
            predictions = get_predictions(job_id)
            metrics = evaluate(predictions, labels)

            print(f"acc={metrics['accuracy']:.3f}  f1={metrics['f1']:.3f}  "
                  f"(tp={metrics['tp']} fp={metrics['fp']} fn={metrics['fn']} tn={metrics['tn']})")

            results.append({
                **params,
                **metrics,
                "status": "COMPLETED",
                "job_id": job_id,
            })

        except Exception as e:
            print(f"ERROR: {e}")
            results.append({**params, "accuracy": 0, "f1": 0, "status": f"ERROR: {e}"})

    elapsed = time.time() - start_time

    # Sort by accuracy
    results.sort(key=lambda r: r.get("accuracy", 0), reverse=True)

    # Print results table
    print()
    print("=" * 80)
    print(" Results (sorted by accuracy)")
    print("=" * 80)
    print()
    print(f"{'Rank':<5} {'window':>6} {'k':>3} {'metric':<10} {'weights':<8} "
          f"{'acc':>6} {'prec':>6} {'recall':>6} {'f1':>6} {'preds':>6}")
    print("-" * 80)

    for rank, r in enumerate(results, 1):
        if r.get("status") != "COMPLETED":
            print(f"{rank:<5} {r['window_size']:>6} {r['n_neighbors']:>3} {r['metric']:<10} {r['weights']:<8} "
                  f"{'--':>6} {'--':>6} {'--':>6} {'--':>6} {r['status']}")
        else:
            print(f"{rank:<5} {r['window_size']:>6} {r['n_neighbors']:>3} {r['metric']:<10} {r['weights']:<8} "
                  f"{r['accuracy']:>6.3f} {r['precision']:>6.3f} {r['recall']:>6.3f} {r['f1']:>6.3f} "
                  f"{r.get('predictions', 0):>6}")

    # Best config
    best = results[0]
    print()
    print("=" * 80)
    print(" Best Config")
    print("=" * 80)
    print(f"  window_size:  {best['window_size']}")
    print(f"  n_neighbors:  {best['n_neighbors']}")
    print(f"  metric:       {best['metric']}")
    print(f"  weights:      {best['weights']}")
    print()
    print(f"  Accuracy:     {best.get('accuracy', 0):.4f}")
    print(f"  F1:           {best.get('f1', 0):.4f}")
    print(f"  Precision:    {best.get('precision', 0):.4f}")
    print(f"  Recall:       {best.get('recall', 0):.4f}")
    print()
    print(f"  Total time:   {elapsed/60:.1f} min ({total_combos} combinations)")
    print()

    # Save results
    results_file = os.path.join(DATA_DIR, "optimization_results.json")
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  Results saved to: {results_file}")

    # Print best config YAML
    print()
    print("  Recommended config:")
    print("  ```yaml")
    print("  worker:")
    print("    parallelism: 1")
    print("    config:")
    print(f"      model_type: \"{FIXED_PARAMS['model_type']}\"")
    print(f"      batch_size: {FIXED_PARAMS['batch_size']}")
    print(f"      timestamp_column: \"{FIXED_PARAMS['timestamp_column']}\"")
    print(f"      data_columns: {json.dumps(FIXED_PARAMS['data_columns'])}")
    print("      reader_config:")
    print(f"        window_size: {best['window_size']}")
    print("        step_size: 1")
    print("      classifier_config:")
    print(f"        n_neighbors: {best['n_neighbors']}")
    print(f"        metric: \"{best['metric']}\"")
    print(f"        weights: \"{best['weights']}\"")
    print(f"      flush_every_n_iteration: {FIXED_PARAMS['flush_every_n_iteration']}")
    print("  ```")


if __name__ == "__main__":
    main()
