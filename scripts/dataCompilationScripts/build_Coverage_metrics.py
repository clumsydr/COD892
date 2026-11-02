#!/usr/bin/env python3
"""
Extract coverage metrics (RSRP, RSRQ, SINR) from the phone's network logs and
split each capture into a speedtest part and a dummy-VC part.

Reads   data/<op>/<loc>/<date>/capture_*/session_*/network_logs_*.csv
          time,lat,lon,network,signal,operator,mcc,mnc,pci,tac,nci,rsrp,rsrq,
          sinr,neighborCount,dlKbps,ulKbps,screenOn
Writes  results/coverage_metrics/speedtest/<op>/<loc>/<date>_metrics.csv
            records in the first SPEEDTEST_WINDOW_S seconds of each capture
        results/coverage_metrics/<op>/<loc>/<date>_metrics.csv
            the rest of each capture (dummy VC)

Output columns
  date, run, session, <TS_COL>, time, operator, <METRICS>,
  RSRP Factor, RSRQ Factor, t_since_start_s
  - RSRP / RSRQ Factor = Strong / Average / Poor / Very poor from SIG_LEVELS
    (blank when the metric itself is blank)
  - <TS_COL> is the parsed time in UTC (ISO text), used for sorting/splitting
  - time is the original value from the log, unchanged
  - "N/A", empty or other non-numeric values in rsrp/rsrq/sinr are left blank
  - t_since_start_s = seconds since the first record of the capture

Usage: edit SETTINGS, then run
  python coverage_metrics.py
"""
from pathlib import Path
import sys, argparse
import numpy as np
import pandas as pd

# ============================ SETTINGS =====================================
OPERATORS = ["Airtel", "Jio", "Vodafone"]   # folder names under data/; None = all
ROOT = "data"                                        # input root folder
OUT_DummyVC   = "results/coverage_metrics/"          # dummy VC output root
OUT_speedtest = "results/coverage_metrics/speedtest" # speedtest output root
TS_COL = "timestamp_utc"                             # name of the parsed UTC time column in the output

INPUT_TIME_COL = "time"        # time column in network_logs_*.csv
NAIVE_TZ = "UTC"               # timezone of log times without an offset, e.g. "Asia/Kolkata"

SPEEDTEST_WINDOW_S = 40        # first N seconds of each capture = speedtest, rest = dummy VC
WINDOW_FROM = "capture"        # "capture": window starts at the capture's first record
                               # "session": window restarts at every session_* folder

METRICS = ["rsrp", "rsrq", "sinr", "dlKbps", "ulKbps"]
# Android reports unavailable values as Integer.MAX_VALUE; treat them as blank too
INVALID_VALUES = [2147483647, -2147483648]

# Signal levels -> factor label, best to worst:
#   Strong    : value >  strong   (>= strong if strong_inclusive=True)
#   Average   : average <= value < strong   (<= strong if strong_inclusive=False)
#   Poor      : poor    <= value < average
#   Very poor : value <  poor
#   blank     : metric is blank (N/A)
SIG_LEVELS = {
    "rsrp": dict(strong=-85, average=-105, poor=-120, strong_inclusive=False),
    "rsrq": dict(strong=-9, average=-14, poor=-19, strong_inclusive=True),
    "sinr": dict(strong=20, average=13, poor=0, strong_inclusive=False),
}
# metric -> name of the factor column added to the output
FACTOR_COLUMNS = {"rsrp": "RSRP Factor", "rsrq": "RSRQ Factor"}   # add "sinr": "SINR Factor" if needed
FACTOR_LABELS = ["Strong", "Average", "Poor", "Very poor"]
# ===========================================================================


def as_list(x):
    return None if x is None else ([x] if isinstance(x, str) else list(x))


def to_utc(s):
    """Times (epoch s/ms/us/ns or strings, with or without offset) -> UTC datetime."""
    n = pd.to_numeric(s, errors="coerce")
    if n.notna().mean() > 0.9:
        m = n.abs().median()
        unit = "ns" if m > 1e17 else "us" if m > 1e14 else "ms" if m > 1e11 else "s"
        return pd.to_datetime(n, unit=unit, utc=True, errors="coerce")
    txt = s.astype(str).str.strip()
    has_off = txt.str.contains(r"(?:[+-]\d{2}:?\d{2}|Z)$", regex=True)
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns, UTC]")
    if has_off.any():
        out[has_off] = pd.to_datetime(txt[has_off], errors="coerce", format="mixed", utc=True)
    if (~has_off).any():
        dt = pd.to_datetime(txt[~has_off], errors="coerce", format="mixed")
        out[~has_off] = dt.dt.tz_localize(NAIVE_TZ, ambiguous="NaT",
                                          nonexistent="NaT").dt.tz_convert("UTC")
    return out


def clean_metric(s):
    """'N/A', blanks, text and Android sentinels -> NaN (written as blank)."""
    v = pd.to_numeric(s.astype(str).str.strip().replace({"N/A": "", "NA": "", "n/a": ""}),
                      errors="coerce")
    return v.where(~v.isin(INVALID_VALUES))


def signal_factor(values, lv):
    """Map metric values to Strong / Average / Poor / Very poor using SIG_LEVELS."""
    s, a, p = lv["strong"], lv["average"], lv["poor"]
    strong = values >= s if lv.get("strong_inclusive", False) else values > s
    out = pd.Series("", index=values.index, dtype=object)   # blank metric -> blank factor
    out[values < p] = FACTOR_LABELS[3]
    out[(values >= p) & (values < a)] = FACTOR_LABELS[2]
    out[(values >= a) & ~strong] = FACTOR_LABELS[1]
    out[strong] = FACTOR_LABELS[0]
    return out


def find(df, name):
    lower = {c.lower().strip(): c for c in df.columns}
    return lower.get(name.lower().strip())


def load_capture(cap_dir):
    frames = []
    for f in sorted(cap_dir.glob("session_*/network_logs_*.csv")):
        df = pd.read_csv(f, dtype=str, keep_default_na=False)
        tc = find(df, INPUT_TIME_COL)
        if tc is None:
            print(f"[!] {f}: no '{INPUT_TIME_COL}' column, skipped", file=sys.stderr)
            continue
        oc = find(df, "operator")
        out = pd.DataFrame({
            "session": f.parent.name,
            "time": df[tc],
            "operator": df[oc] if oc else "",
        })
        for m in METRICS:
            c = find(df, m)
            out[m] = clean_metric(df[c]) if c else np.nan
            if c is None:
                print(f"[!] {f.name}: no '{m}' column", file=sys.stderr)
        out["_t"] = to_utc(df[tc])
        bad = out["_t"].isna().sum()
        if bad:
            print(f"[!] {f.name}: {bad} rows with unparsable time dropped", file=sys.stderr)
        frames.append(out.dropna(subset=["_t"]))
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True).sort_values(["_t", "session"], kind="mergesort")


def split_capture(d):
    ref = d.groupby("session")["_t"].transform("min") if WINDOW_FROM == "session" \
        else d["_t"].min()
    d = d.copy()
    d["t_since_start_s"] = ((d["_t"] - ref).dt.total_seconds()).round(3)
    is_st = d["t_since_start_s"] < SPEEDTEST_WINDOW_S
    return d[is_st], d[~is_st]


def finish(parts, date):
    if not parts:
        return None
    d = pd.concat(parts, ignore_index=True).sort_values("_t", kind="mergesort")
    d.insert(0, "date", date)
    d[TS_COL] = d["_t"].dt.strftime("%Y-%m-%d %H:%M:%S.%f").str[:-3] + "+00:00"
    factor_cols = []
    for metric, col in FACTOR_COLUMNS.items():
        if metric in d.columns and metric in SIG_LEVELS:
            d[col] = signal_factor(d[metric], SIG_LEVELS[metric])
            factor_cols.append(col)
    cols = (["date", "run", "session", TS_COL, "time", "operator"] + METRICS
            + factor_cols + ["t_since_start_s"])
    return d[cols]


def main():
    if WINDOW_FROM not in ("capture", "session"):
        sys.exit('WINDOW_FROM must be "capture" or "session"')
    root = Path(ROOT)
    ops_f, locs_f, dates_f = as_list(OPERATORS), as_list(LOCATIONS), as_list(DATES)
    combos = sorted({p.relative_to(root).parts[:3] for p in root.glob("*/*/*/capture_*") if p.is_dir()})
    combos = [c for c in combos if (not ops_f or c[0] in ops_f)
              and (not locs_f or c[1] in locs_f) and (not dates_f or c[2] in dates_f)]
    for want, have, name in ((ops_f, {c[0] for c in combos}, "operator"),
                             (locs_f, {c[1] for c in combos}, "location"),
                             (dates_f, {c[2] for c in combos}, "date")):
        for w in (want or []):
            if w not in have:
                print(f"[!] {name} '{w}': no capture_* folders found under {ROOT}/", file=sys.stderr)
    if not combos:
        sys.exit("Nothing to process.")

    summary = []
    for op, loc, date in combos:
        st_parts, vc_parts = [], []
        for cap in sorted((root / op / loc / date).glob("capture_*")):
            d = load_capture(cap)
            if d is None or d.empty:
                print(f"[!] {cap}: no network_logs_*.csv data", file=sys.stderr)
                continue
            d["run"] = cap.name
            st, vc = split_capture(d)
            st_parts.append(st)
            vc_parts.append(vc)
            summary.append({"operator": op, "location": loc, "date": date, "run": cap.name,
                            "sessions": d["session"].nunique(),
                            "duration_s": round((d["_t"].max() - d["_t"].min()).total_seconds(), 1),
                            "speedtest_rows": len(st), "dummyVC_rows": len(vc),
                            "sinr_blank_%": round(100 * d["sinr"].isna().mean(), 1)})

        for parts, out_root, label in ((st_parts, OUT_speedtest, "speedtest"),
                                       (vc_parts, OUT_DummyVC, "dummyVC")):
            res = finish(parts, date)
            if res is None or res.empty:
                print(f"[!] {op}/{loc}/{date}: no {label} rows", file=sys.stderr)
                continue
            dst = Path(out_root) / op / loc / f"{date}_metrics.csv"
            dst.parent.mkdir(parents=True, exist_ok=True)
            res.to_csv(dst, index=False)
            print(f"[✓] {op}/{loc}/{date} {label:9s}: {len(res):,} rows -> {dst}")

    if summary:
        print(f"\nPer capture (speedtest = first {SPEEDTEST_WINDOW_S} s from {WINDOW_FROM} start):")
        print(pd.DataFrame(summary).to_string(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--locations",
        nargs="+",
        default=["indoor_Shubham_JiaSarai"],
        help="List of measurement locations (space-separated)",
    )
    parser.add_argument(
        "--dates",
        nargs="+",                    
        default=["20261018"],
        help="List of dates in YYYYMMDD format (space-separated)",
    )
    args = parser.parse_args()
    LOCATIONS = args.locations
    DATES = args.dates
    main()