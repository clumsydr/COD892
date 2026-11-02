#!/usr/bin/env python3
"""
Combine per-operator estimation CSVs into larger files.

Input  : regression/<window>/<loc>/<op>/<date>/<date>_downlink*.csv  and  <date>_uplink*.csv
Outputs:
  regression/<window>/<loc>/<date>_combined.csv   all operators, DL + UL, one location, one date
  regression/<window>/<loc>_combined.csv          all operators, DL + UL, all dates, one location
  regression/<window>/all_data.csv                everything for that window size

A "Location" column is added (the input files don't have one) so rows stay identifiable
once locations are merged.
"""

import glob
import os
import re

import pandas as pd

# =============================================================================
# SETTINGS — edit these
# =============================================================================
REGRESSION_ROOT = "regression"

# Window folders to process, e.g. ["1000ms"]; None = every folder under REGRESSION_ROOT
WINDOW_DIRS = ["1000ms"]

# Restrict processing (None = everything found)
LOCATIONS = None
OPERATORS = None
DATES = None

# Folder names directly under the window folder that are NOT locations
# (the speedtest outputs live in regression/<window>/speedtest/...)
SKIP_LOCATION_DIRS = ["speedtest"]

# Also combine the speedtest tree, writing the same three kinds of file under
# regression/<window>/speedtest/
INCLUDE_SPEEDTEST = True

# Matches <date>_downlink.csv and <date>_downlink_estimation.csv (same for uplink)
DL_GLOB = "*_downlink.csv"
UL_GLOB = "*_uplink.csv"

# Row order in the combined files
SORT_COLUMNS = ["Location", "Operator", "Date", "Direction", "Run", "Timestamp"]


# =============================================================================
def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]


def subdirs(path):
    return sorted((d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))),
                  key=natural_key)


def read_estimation(path, loc, op, date):
    df = pd.read_csv(path)
    if df.empty:
        return None
    df.insert(0, "Location", loc)
    if "Operator" not in df.columns:
        df.insert(1, "Operator", op)
    if "Date" not in df.columns:
        df.insert(2, "Date", date)
    return df


def sort_rows(df):
    cols = [c for c in SORT_COLUMNS if c in df.columns]
    return df.sort_values(cols, kind="stable",
                          key=lambda s: s.map(natural_key) if s.dtype == object else s
                          ).reset_index(drop=True)


def combine_tree(base_dir):
    """base_dir = regression/<window> (or regression/<window>/speedtest)."""
    all_frames = []
    for loc in subdirs(base_dir):
        if loc in SKIP_LOCATION_DIRS or (LOCATIONS and loc not in LOCATIONS):
            continue
        loc_dir = os.path.join(base_dir, loc)

        # group files by date across operators
        by_date = {}
        for op in subdirs(loc_dir):
            if OPERATORS and op not in OPERATORS:
                continue
            for date in subdirs(os.path.join(loc_dir, op)):
                if DATES and date not in DATES:
                    continue
                date_dir = os.path.join(loc_dir, op, date)
                files = glob.glob(os.path.join(date_dir, DL_GLOB)) + \
                        glob.glob(os.path.join(date_dir, UL_GLOB))
                for f in files:
                    by_date.setdefault(date, []).append((op, f))

        loc_frames = []
        for date in sorted(by_date, key=natural_key):
            frames = [read_estimation(f, loc, op, date) for op, f in by_date[date]]
            frames = [f for f in frames if f is not None]
            if not frames:
                continue
            date_df = sort_rows(pd.concat(frames, ignore_index=True))
            out = os.path.join(loc_dir, f"{date}_combined.csv")
            date_df.to_csv(out, index=False)
            ops = sorted(date_df["Operator"].unique(), key=natural_key)
            print(f"  {out}  ({len(date_df)} rows, operators: {', '.join(map(str, ops))})")
            loc_frames.append(date_df)

        if loc_frames:
            loc_df = sort_rows(pd.concat(loc_frames, ignore_index=True))
            out = os.path.join(base_dir, f"{loc}_combined.csv")
            loc_df.to_csv(out, index=False)
            print(f"  {out}  ({len(loc_df)} rows)")
            all_frames.append(loc_df)

    if all_frames:
        all_df = sort_rows(pd.concat(all_frames, ignore_index=True))
        out = os.path.join(base_dir, "all_data.csv")
        all_df.to_csv(out, index=False)
        print(f"  {out}  ({len(all_df)} rows)")
    else:
        print(f"  [warn] nothing found under {base_dir}")


def main():
    windows = WINDOW_DIRS or subdirs(REGRESSION_ROOT)
    for w in windows:
        base = os.path.join(REGRESSION_ROOT, w)
        if not os.path.isdir(base):
            print(f"[warn] {base} not found")
            continue
        print(f"Window {w}:")
        combine_tree(base)
        if INCLUDE_SPEEDTEST and os.path.isdir(os.path.join(base, "speedtest")):
            print(f"Window {w} (speedtest):")
            combine_tree(os.path.join(base, "speedtest"))
    print("Done.")


if __name__ == "__main__":
    main()