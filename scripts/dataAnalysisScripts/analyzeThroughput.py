#!/usr/bin/env python3
"""
Packet CSVs (from pcap_to_csv.py) -> throughput per time window.

Input : every packet CSV under <IN_ROOT>/<operator>/<location>/<date>/capture_*/
        (e.g. capture_*.csv and speedtest_qmdl_*/speedtest_*.csv)
        columns: timestamp, length, src_ip, dst_ip, direction
Output: same folder, <input name>_throughput_<window>.csv
        columns: Timestamp, Download (Mbps), Upload (Mbps)

Timestamp = start of each window, in seconds since the capture's first packet.
Throughput = bytes in the window * 8 / 1e6 / window length (so it is always Mbps).
Windows with no packets are 0. Packets with direction "other" are ignored.

Usage:
  python packets_to_throughput.py --window 1s
  python packets_to_throughput.py --window 10ms
  python packets_to_throughput.py --window 100ms some_capture.csv     # just this file
"""
import argparse
import math
import sys
import traceback
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# ───────────────────────────── CONFIG ──────────────────────────────
IN_ROOT = Path("results/Throughput")

OPERATORS = None          # None = every operator folder in IN_ROOT; or e.g. ["Airtel", "Jio"]
LOCATIONS = ["indoor_Bharti501"]

START_DATE, END_DATE = date(2026, 10, 6), date(2026, 10, 13)   # both inclusive
DATES = [(START_DATE + timedelta(days=i)).strftime("%Y%m%d")
         for i in range((END_DATE - START_DATE).days + 1)]

OVERWRITE = True          # False: skip captures whose output for this window already exists
# ───────────────────────────────────────────────────────────────────

PACKET_COLS = {"timestamp", "length", "direction"}
OUT_COLS = ["Timestamp", "Download (Mbps)", "Upload (Mbps)"]


def log(msg):
    print(msg, flush=True)


def parse_window(text):
    """'10ms', '1s', '0.5s', '100ms' or a bare number of seconds -> seconds (float)."""
    try:
        sec = float(text)
    except ValueError:
        sec = pd.Timedelta(text).total_seconds()
    if sec <= 0:
        raise ValueError
    return sec


def window_tag(sec):
    return f"{sec:g}s" if sec >= 1 else f"{sec * 1000:g}ms"


def ci_child(parent, name):
    """Case-insensitive child lookup; returns None if parent is None / missing."""
    if parent is None or not parent.is_dir():
        return None
    p = parent / name
    if p.exists():
        return p
    for c in parent.iterdir():
        if c.name.lower() == name.lower():
            return c
    return None


def is_packet_csv(path):
    """True if the CSV has the packet columns (skips per-second files and earlier outputs)."""
    if path.name.startswith("._") or "_throughput_" in path.name:
        return False
    try:
        cols = set(pd.read_csv(path, nrows=0).columns)
    except Exception:
        return False
    return PACKET_COLS <= cols


def collect_files():
    if not IN_ROOT.is_dir():
        sys.exit(f"{IN_ROOT} not found")
    if OPERATORS:
        op_dirs = [d for d in (ci_child(IN_ROOT, op) for op in OPERATORS) if d is not None]
    else:
        op_dirs = sorted(p for p in IN_ROOT.iterdir() if p.is_dir())

    files = []
    for op_dir in op_dirs:
        for loc in LOCATIONS:
            loc_dir = ci_child(op_dir, loc)
            if loc_dir is None:
                log(f"- no folder {op_dir.name}/{loc}, skipping")
                continue
            for d in DATES:
                date_dir = ci_child(loc_dir, d)
                if date_dir is None:
                    continue
                for cap in sorted(p for p in date_dir.glob("capture_*") if p.is_dir()):
                    # any packet CSV in the capture folder or its subfolders
                    # (e.g. capture_*.csv, speedtest_qmdl_*/speedtest_*.csv)
                    found = [f for f in sorted(cap.rglob("*.csv")) if is_packet_csv(f)]
                    if not found:
                        log(f"- no packet CSV in {cap}")
                    files.extend(found)
    return files


def throughput(path, win):
    df = pd.read_csv(path, usecols=["timestamp", "length", "direction"])
    df = df.dropna(subset=["timestamp", "length"])
    if df.empty:
        return pd.DataFrame(columns=OUT_COLS)

    t0 = df["timestamp"].min()
    df["bin"] = np.floor((df["timestamp"] - t0) / win).astype(np.int64)
    n_bins = int(df["bin"].max()) + 1

    bins = np.arange(n_bins)
    scale = 8 / 1e6 / win            # bytes per window -> Mbps
    out = pd.DataFrame({"Timestamp": bins * win})
    for direction, col in (("downlink", "Download (Mbps)"), ("uplink", "Upload (Mbps)")):
        b = df.loc[df["direction"] == direction].groupby("bin")["length"].sum()
        out[col] = b.reindex(bins, fill_value=0).to_numpy() * scale

    # clean timestamps: whole seconds as int, otherwise rounded to the window's precision
    if float(win).is_integer():
        out["Timestamp"] = out["Timestamp"].round().astype(np.int64)
    else:
        decimals = max(0, -math.floor(math.log10(win))) + 2
        out["Timestamp"] = out["Timestamp"].round(decimals)
    out[OUT_COLS[1:]] = out[OUT_COLS[1:]].round(4)
    return out


def main():
    ap = argparse.ArgumentParser(description="Packet CSV -> throughput per window")
    ap.add_argument("--window", "-w", required=True,
                    help="window size, e.g. 10ms, 100ms, 1s, 0.5s (bare number = seconds)")
    ap.add_argument("files", nargs="*", help="optional packet CSVs (default: use CONFIG)")
    args = ap.parse_args()

    try:
        win = parse_window(args.window)
    except ValueError:
        sys.exit(f"Invalid window '{args.window}'. Use e.g. 10ms, 100ms, 1s.")
    tag = window_tag(win)

    files = [Path(f) for f in args.files] if args.files else collect_files()
    if not files:
        sys.exit("No packet CSVs found.")
    log(f"Window {tag}: {len(files)} file(s)")

    ok = failed = skipped = 0
    for f in files:
        dest = f.with_name(f"throughput_{tag}_{f.stem}.csv")
        if dest.exists() and not OVERWRITE:
            skipped += 1
            continue
        try:
            out = throughput(f, win)
            out.to_csv(dest, index=False)
            dur = out["Timestamp"].iloc[-1] + win if len(out) else 0
            log(f"[{f}] {len(out)} windows (~{dur:.1f} s) -> {dest.name}")
            ok += 1
        except Exception:
            failed += 1
            log(f"!! failed on {f}")
            traceback.print_exc()
    log(f"\nDone. {ok} written, {skipped} already existed, {failed} failed.")


if __name__ == "__main__":
    main()