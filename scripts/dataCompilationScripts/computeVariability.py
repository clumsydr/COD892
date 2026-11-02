#!/usr/bin/env python3
"""
Per-run, per-window-size variability for downlink and uplink captures, plus the mean across runs.

  in : <ROOT>/<operator>/<location>/<date>/capture_*_downlink.csv
       <ROOT>/<operator>/<location>/<date>/capture_*_uplink.csv
  out: <ROOT>/<operator>/variability_per_run_<direction>.csv        (one row per run x window size)
       <ROOT>/variability_mean_<direction>.csv                      (one row per operator x window size)

Each capture CSV is one run (Capture Run Name = file name without .csv).

How variability is computed for one run and window size t:
  1. Split the run's rows (1 row = 1 s) into consecutive non-overlapping windows of t rows.
     A trailing partial window (fewer than t rows) is dropped.
  2. Average each window:                 w_1, w_2, ..., w_n
  3. Absolute difference of neighbours:   var_k = |w_(k+1) - w_k|,  k = 1 .. n-1
  4. Run variability = mean of var_k.

  Example, t = 2, th = 10,20,30,40,50,50,50,60,55,56
     windows   15, 35, 50, 55, 55.5
     diffs     20, 15, 5, 0.5
     variability = (20 + 15 + 5 + 0.5) / 4 = 10.125

A run with fewer than 2 complete windows for some t gets empty values for that t.
Mean CSV = plain mean of the per-run values across all runs of an operator (empty values skipped);
the "Runs" column says how many runs went into each mean.

Usage: edit the CONFIG block, then run  python capture_variability.py
"""
import sys
from pathlib import Path

import pandas as pd

# ───────────────────────────── CONFIG ──────────────────────────────
ROOT = Path("results/dummyVC/allMetrics")
OPERATORS = None                   
DIRECTIONS = ["downlink", "uplink"]
FILE_PATTERN = "*/*/capture_*_{direction}.csv"     # <location>/<date>/capture_*_<direction>.csv

WINDOW_SIZES = [1, 2, 5, 10, 20, 50]

# output column -> input column candidates (first one found in the file is used)
PARAMS = {
    "Throughput Variability":            ["Download (Mbps)", "Upload (Mbps)", "Throughput (Mbps)"],
    "PHY Throughput Variability":        ["PHY Throughput (Mbps)"],
    "Resource Block Variability":        ["Resource Blocks"],
    "MIMO Variability":                  ["MIMO (layers)"],
    "Retransmission Rate Variability":   ["Retransmission Rate (%)"],
    "MCS Variability":                   ["MCS"],
}

OUT_PER_RUN = "variability_per_run_{direction}.csv"
OUT_MEAN = "variability_mean_{direction}.csv"
DECIMALS = 4
# ───────────────────────────────────────────────────────────────────


def log(msg):
    print(msg, flush=True)


def find_col(df, candidates):
    lower = {c.strip().lower(): c for c in df.columns}
    for name in candidates:
        if name.lower() in lower:
            return lower[name.lower()]
    return None


def run_variability(x, t):
    """x: 1-D numeric Series in time order. Mean of |neighbouring window mean differences|."""
    n_win = len(x) // t
    # if n_win < 2:
    #     return float("nan")
    v = x.iloc[: n_win * t].reset_index(drop=True)
    means = v.groupby(v.index // t).mean()          # window means (empty values skipped)
    return means.diff().abs().iloc[1:].mean()


def process_file(path, warned):
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]

    cols = {}
    for out_col, candidates in PARAMS.items():
        c = find_col(df, candidates)
        if c is None:
            if out_col not in warned:
                log(f"    ! none of {candidates} found in {path.name} -> '{out_col}' left empty")
                warned.add(out_col)
            cols[out_col] = None
        else:
            cols[out_col] = pd.to_numeric(df[c], errors="coerce")

    rows = []
    for t in WINDOW_SIZES:
        row = {"Capture Run Name": path.stem, "Window Size": t}
        for out_col, x in cols.items():
            row[out_col] = float("nan") if x is None else run_variability(x, t)
        rows.append(row)
    if len(df) < 2 * max(WINDOW_SIZES):
        too_big = [t for t in WINDOW_SIZES if len(df) < 2 * t]
        log(f"    ! {path.name}: {len(df)} rows, too short for window size(s) {too_big}")
    return rows


def main():
    if not ROOT.is_dir():
        sys.exit(f"{ROOT} not found")
    ops = [p for p in sorted(ROOT.iterdir())
           if p.is_dir() and (OPERATORS is None or p.name.lower() in {o.lower() for o in OPERATORS})]
    if not ops:
        sys.exit(f"No operator folders found under {ROOT}")

    for direction in DIRECTIONS:
        mean_parts = []
        for op in ops:
            files = sorted(op.glob(FILE_PATTERN.format(direction=direction)))
            if not files:
                log(f"[{op.name}] no {direction} captures found")
                continue
            log(f"[{op.name}] {direction}: {len(files)} run(s)")

            rows, warned = [], set()
            for f in files:
                rel = f.relative_to(op).parts                 # (location, date, file)
                for r in process_file(f, warned):
                    rows.append({"Operator": op.name, "Location": rel[0], "Date": rel[1], **r})
            per_run = pd.DataFrame(rows)

            dest = op / OUT_PER_RUN.format(direction=direction)
            per_run.round(DECIMALS).to_csv(dest, index=False)
            log(f"    per-run -> {dest}")

            param_cols = list(PARAMS)
            g = per_run.groupby("Window Size", sort=True)
            mean = g[param_cols].mean()
            mean["Runs"] = g["Throughput Variability"].count()   # runs long enough for this t
            mean = mean.reset_index()
            mean.insert(0, "Operator", op.name)
            mean_parts.append(mean)

        if mean_parts:
            out = pd.concat(mean_parts, ignore_index=True)
            dest = ROOT / OUT_MEAN.format(direction=direction)
            out.round(DECIMALS).to_csv(dest, index=False)
            log(f"[all] {direction} mean -> {dest}")


if __name__ == "__main__":
    main()