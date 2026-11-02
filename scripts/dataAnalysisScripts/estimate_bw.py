#!/usr/bin/env python3
"""
Estimate PHY-layer throughput from QMDL metrics and compare with application throughput.

Pipeline (applied to every operator / location / date / run):
  MIMO            : UL = 1 (4G/5G); DL = "MIMO Layers"                 -> window MEAN
  Q_m             : 5G -> TS 38.214 Table 5.1.3.1-2 from MCS
                    4G -> from Modulation (QPSK 2, 16QAM 4, 64QAM 6, 256QAM 8)  -> window MEAN
  Target Code Rate: 5G -> TS 38.214 Table 5.1.3.1-2 from MCS (R x 1024)
                    4G UL -> floor(Coding Rate * 1024)
                    4G DL -> (TBS + 24) / (14 * 12 * RB * Q_m)      (see settings) -> window MEAN
  Resource Blocks : window SUM
  Efficiency      : new RB / total RB, new = RB where Retransmission == 0 (per window)
  Estimated_Throughput = MIMO * Q_m * Target Code Rate * Resource Blocks * Efficiency (per window)

Outputs:
  regression/<window_size>/<location>/<operator>/<date>/<date>_downlink_estimation.csv
  regression/<window_size>/<location>/<operator>/<date>/<date>_uplink_estimation.csv
  (with --use_speedtest true: regression/<window_size>/speedtest/<location>/<operator>/<date>/...)

Command line (all optional; defaults come from SETTINGS below):
  python3 estimate_throughput.py --location Loc1 Loc2 --dates 2026-10-01 --window_size 1 5 --use_speedtest true
"""

import argparse
import glob
import os
import re

import numpy as np
import pandas as pd

# =============================================================================
# SETTINGS — edit these
# =============================================================================
RESULTS_DIR = "results"
OUTPUT_ROOT = "regression"

# Window sizes in SECONDS (integers recommended, since app throughput is per 1 s).
# One output tree is produced per window size, e.g. regression/1000ms/..., regression/5000ms/...
WINDOW_SIZES_S = [1, 2, 5]

# Restrict processing (None = everything found on disk)
OPERATORS = None      # e.g. ["Jio", "Airtel"]
LOCATIONS = None      # e.g. ["LabA"]
DATES = None          # e.g. ["2026-10-01"]

# Speedtest mode (overridable with --use_speedtest true/false)
USE_SPEEDTEST = False

# QMDL file name suffixes — normal mode: results/qmdl_metrics/<op>/<loc>/<date><suffix>
QMDL_DL_SUFFIX = "_downlink.csv"
QMDL_UL_SUFFIX = "_uplink.csv"

# QMDL file name suffixes — speedtest mode: results/qmdl_metrics/speedtest/<op>/<loc>/<date><suffix>
# (uplink is processed only if that file exists)
SPEEDTEST_QMDL_DL_SUFFIX = "_downlink.csv"
SPEEDTEST_QMDL_UL_SUFFIX = "_uplink.csv"

# Application throughput file patterns, relative to results/Throughput/<op>/<loc>/<date>/
APP_PATTERN = os.path.join("capture_*", "throughput_1s_capture_*.csv")
SPEEDTEST_APP_PATTERN = os.path.join("capture_*", "speedtest_qmdl_*", "throughput_1s_speedtest*.csv")

# Column names in application throughput files (a missing column -> blank Application_Throughput)
APP_DL_COL = "Download (Mbps)"
APP_UL_COL = "Upload (Mbps)"

# A row is treated as 5G if radio_connection contains any of these (case-insensitive)
NR_KEYWORDS = ["NR", "5G"]

# 4G downlink target code rate numerator:
#   "tb_size"   -> (TB Size column + 24 CRC bits) / (14*12*RB*Q_m)
#   "tbs_index" -> (I_TBS from TS 36.213 Table 7.1.7.1-1 + 24) / (14*12*RB*Q_m)   [literal reading]
LTE_DL_TCR_NUMERATOR = "tb_size"
TB_SIZE_IN_BYTES = False          # set True if the "TB Size" column is in bytes (converted to bits)
LTE_DL_TCR_SCALE_1024 = True      # express 4G DL code rate as R x 1024, same scale as 5G table & 4G UL

# Blank Retransmission values: True -> treated as new transmission (0)
RETX_BLANK_AS_NEW = True

# How to pair a QMDL "run" with a capture_* folder:
#   "number" -> match the number in the run value with the number in capture_<n>
#   "order"  -> i-th run (natural sort) <-> i-th capture folder (natural sort)
# "number" falls back to "order" if numbers don't line up.
CAPTURE_MATCH = "number"

# Float precision in output CSVs
FLOAT_FMT = "%.6f"

# =============================================================================
# 3GPP TABLES
# =============================================================================
# TS 38.214 Table 5.1.3.1-2 (MCS index table 2, up to 256QAM): MCS -> (Q_m, R x 1024)
# MCS 28-31 are reserved (Q_m defined, code rate not) -> code rate NaN
NR_MCS_TABLE = {
    0: (2, 120), 1: (2, 193), 2: (2, 308), 3: (2, 449), 4: (2, 602),
    5: (4, 378), 6: (4, 434), 7: (4, 490), 8: (4, 553), 9: (4, 616), 10: (4, 658),
    11: (6, 466), 12: (6, 517), 13: (6, 567), 14: (6, 616), 15: (6, 666),
    16: (6, 719), 17: (6, 772), 18: (6, 822), 19: (6, 873),
    20: (8, 682.5), 21: (8, 711), 22: (8, 754), 23: (8, 797), 24: (8, 841),
    25: (8, 885), 26: (8, 916.5), 27: (8, 948),
    28: (2, np.nan), 29: (4, np.nan), 30: (6, np.nan), 31: (8, np.nan),
}

# TS 36.213 Table 7.1.7.1-1: MCS -> I_TBS (29-31 reserved)
LTE_MCS_TO_ITBS = {
    **{m: m for m in range(0, 10)},          # QPSK, I_TBS 0-9
    **{m: m - 1 for m in range(10, 17)},     # 16QAM, I_TBS 9-15
    **{m: m - 2 for m in range(17, 29)},     # 64QAM, I_TBS 15-26
}

LTE_MOD_QM = {"QPSK": 2, "16QAM": 4, "64QAM": 6, "256QAM": 8}

OUT_COLUMNS = [
    "Operator", "Date", "Run", "Timestamp", "Direction", "MIMO", "Q_m",
    "Target Code Rate", "Resource Blocks", "Efficiency",
    "Application_Throughput", 
]


# =============================================================================
# HELPERS
# =============================================================================
def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]


def last_int(s):
    nums = re.findall(r"\d+", str(s))
    return int(nums[-1]) if nums else None


def to_epoch_seconds(series):
    """Convert a timestamp column (epoch s/ms/us/ns or datetime strings) to float seconds."""
    num = pd.to_numeric(series, errors="coerce")
    if num.notna().mean() > 0.9:
        med = num.median()
        if med > 1e17:
            return num / 1e9
        if med > 1e14:
            return num / 1e6
        if med > 1e11:
            return num / 1e3
        return num.astype(float)
    dt = pd.to_datetime(series, errors="coerce", utc=True)
    return (dt - pd.Timestamp("1970-01-01", tz="UTC")).dt.total_seconds()


def norm_mod(v):
    if pd.isna(v):
        return None
    return re.sub(r"[\s\-_]", "", str(v)).upper()


def parse_retx(series):
    s = series.astype(str).str.strip().str.upper()
    mapped = s.map({"TRUE": 1, "YES": 1, "FALSE": 0, "NO": 0})
    num = pd.to_numeric(series, errors="coerce").fillna(mapped)
    if RETX_BLANK_AS_NEW:
        num = num.fillna(0)
    return num


def nr_lookup(mcs, idx):
    def f(m):
        if pd.isna(m):
            return np.nan
        return NR_MCS_TABLE.get(int(m), (np.nan, np.nan))[idx]
    return mcs.map(f).astype(float)


# =============================================================================
# PER-ROW PARAMETERS
# =============================================================================
def add_row_params(df, direction):
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]

    rc = df["radio_connection"].astype(str).str.upper()
    is_nr = rc.apply(lambda v: any(k.upper() in v for k in NR_KEYWORDS))

    mcs = pd.to_numeric(df["MCS"], errors="coerce")
    rb = pd.to_numeric(df["Resource blocks"], errors="coerce")

    # --- MIMO ---
    if direction == "UL":
        mimo = pd.Series(1.0, index=df.index)
    else:
        mimo = pd.to_numeric(df["MIMO Layers"], errors="coerce")

    # --- Q_m ---
    qm_nr = nr_lookup(mcs, 0)
    qm_lte = df["Modulation"].map(norm_mod).map(LTE_MOD_QM).astype(float)
    if "mod-order" in df.columns:  # fallback only when Modulation is unmappable
        mo = pd.to_numeric(df["mod-order"], errors="coerce")
        qm_lte = qm_lte.fillna(mo.where(mo.isin([2, 4, 6, 8])))
    qm = qm_nr.where(is_nr, qm_lte)

    # --- Target Code Rate ---
    tcr_nr = nr_lookup(mcs, 1)
    if direction == "UL":
        cr = pd.to_numeric(df["Coding Rate"], errors="coerce")
        tcr_lte = np.floor(cr * 1024)
    else:
        if LTE_DL_TCR_NUMERATOR == "tb_size":
            num = pd.to_numeric(df["TB Size"], errors="coerce")
            if TB_SIZE_IN_BYTES:
                num = num * 8
        else:
            num = mcs.map(lambda m: LTE_MCS_TO_ITBS.get(int(m), np.nan) if pd.notna(m) else np.nan)
        denom = 14 * 12 * rb * qm_lte
        tcr_lte = (num + 24) / denom.where(denom > 0)
        if LTE_DL_TCR_SCALE_1024:
            tcr_lte = tcr_lte * 1024
    tcr = tcr_nr.where(is_nr, tcr_lte)

    df["_mimo"] = mimo
    df["_qm"] = qm
    df["_tcr"] = tcr
    df["_rb"] = rb.fillna(0)
    df["_retx"] = parse_retx(df["Retransmission"])
    df["_t"] = to_epoch_seconds(df["timestamp"])
    return df


# =============================================================================
# APPLICATION THROUGHPUT
# =============================================================================
def load_app_throughput(op, loc, date):
    """Returns {key: DataFrame[dl, ul]} indexed by second 0..N-1.
    key = folder holding the file relative to the date folder,
    e.g. 'capture_3' or 'capture_3/speedtest_qmdl_2'."""
    date_dir = os.path.join(RESULTS_DIR, "Throughput", op, loc, date)
    pattern = os.path.join(date_dir, SPEEDTEST_APP_PATTERN if USE_SPEEDTEST else APP_PATTERN)
    out = {}
    for f in sorted(glob.glob(pattern), key=natural_key):
        key = os.path.relpath(os.path.dirname(f), date_dir)
        d = pd.read_csv(f)
        d.columns = [c.strip() for c in d.columns]
        col = lambda c: (pd.to_numeric(d[c], errors="coerce").values if c in d.columns
                         else np.full(len(d), np.nan))
        if APP_DL_COL not in d.columns or APP_UL_COL not in d.columns:
            print(f"    [warn] {f}: missing {APP_DL_COL} or {APP_UL_COL}")
        if key in out:
            print(f"    [warn] more than one throughput file in {key}; using the first")
            continue
        out[key] = pd.DataFrame({"dl": col(APP_DL_COL), "ul": col(APP_UL_COL)})
    return out


def map_runs_to_captures(runs, captures):
    runs_sorted = sorted(runs, key=natural_key)
    caps_sorted = sorted(captures, key=natural_key)
    if CAPTURE_MATCH == "number":
        # number of the innermost folder: capture_<n>, or speedtest_qmdl_<n> in speedtest mode
        nums = [last_int(c) for c in caps_sorted]
        if len(set(nums)) == len(nums):
            cap_by_num = dict(zip(nums, caps_sorted))
            mapping = {r: cap_by_num.get(last_int(r)) for r in runs_sorted}
            if all(v is not None for v in mapping.values()):
                return mapping
        print("    [warn] run numbers don't match folder numbers uniquely; falling back to sorted order")
    return {r: (caps_sorted[i] if i < len(caps_sorted) else None)
            for i, r in enumerate(runs_sorted)}


# =============================================================================
# WINDOW AGGREGATION
# =============================================================================
def aggregate_run(df_run, t0, win_s, app, app_col, meta):
    if df_run.empty:
        return []
    df_run = df_run.copy()
    df_run["_win"] = np.floor((df_run["_t"] - t0) / win_s).astype("Int64")
    df_run = df_run.dropna(subset=["_win"])

    app_win = None
    if app is not None:
        sec = np.arange(len(app))
        app_win = pd.Series(app[app_col].values).groupby(np.floor(sec / win_s).astype(int)).mean()

    rows = []
    for k, g in df_run.groupby("_win", sort=True):
        k = int(k)
        mimo = g["_mimo"].mean()
        qm = g["_qm"].mean()
        tcr = g["_tcr"].mean()
        rb_total = g["_rb"].sum()
        rb_new = g.loc[g["_retx"] == 0, "_rb"].sum()
        eff = rb_new / rb_total if rb_total > 0 else np.nan
        app_tp = app_win.get(k, np.nan) if app_win is not None else np.nan
        rows.append({
            "Operator": meta["op"], "Date": meta["date"], "Run": meta["run"],
            "Timestamp": g["timestamp"].iloc[0], "Direction": meta["dir"],
            "MIMO": mimo, "Q_m": qm, "Target Code Rate": tcr,
            "Resource Blocks": rb_total, "Efficiency": eff,
            "Application_Throughput": app_tp, 
        })
    return rows


# =============================================================================
# MAIN
# =============================================================================
def process_date(op, loc, date, dl_file, ul_file):
    print(f"  {op} | {loc} | {date}")
    dl = add_row_params(pd.read_csv(dl_file), "DL") if dl_file and os.path.exists(dl_file) else None
    ul = add_row_params(pd.read_csv(ul_file), "UL") if ul_file and os.path.exists(ul_file) else None

    app = load_app_throughput(op, loc, date)
    if not app:
        print("    [warn] no application throughput files found; Application_Throughput will be blank")

    runs = set()
    for d in (dl, ul):
        if d is not None:
            runs.update(d["run"].dropna().unique())
    run_to_cap = map_runs_to_captures(runs, list(app.keys())) if app else {r: None for r in runs}

    for win_s in WINDOW_SIZES_S:
        win_dir = f"{int(round(win_s * 1000))}ms"
        if USE_SPEEDTEST:
            out_dir = os.path.join(OUTPUT_ROOT, win_dir, "speedtest", loc, op, date)
        else:
            out_dir = os.path.join(OUTPUT_ROOT, win_dir, loc, op, date)
        os.makedirs(out_dir, exist_ok=True)
        dl_rows, ul_rows = [], []

        for run in sorted(runs, key=natural_key):
            parts = [d.loc[d["run"] == run, "_t"] for d in (dl, ul) if d is not None]
            t0 = pd.concat(parts).min()   # common start so DL and UL windows align
            if pd.isna(t0):
                continue
            cap = run_to_cap.get(run)
            app_df = app.get(cap) if cap else None

            if dl is not None:
                dl_rows += aggregate_run(dl[dl["run"] == run], t0, win_s, app_df, "dl",
                                         {"op": op, "date": date, "run": run, "dir": "Downlink"})
            if ul is not None:
                ul_rows += aggregate_run(ul[ul["run"] == run], t0, win_s, app_df, "ul",
                                         {"op": op, "date": date, "run": run, "dir": "Uplink"})

        for rows, name, src in ((dl_rows, "downlink", dl), (ul_rows, "uplink", ul)):
            if src is None:   # no QMDL file for this direction (e.g. speedtest uplink)
                continue
            path = os.path.join(out_dir, f"{date}_{name}.csv")
            pd.DataFrame(rows, columns=OUT_COLUMNS).to_csv(path, index=False, float_format=FLOAT_FMT)
        print(f"    window {win_s}s -> {out_dir}  (DL {len(dl_rows)} rows, UL {len(ul_rows)} rows)")


def str2bool(v):
    if isinstance(v, bool):
        return v
    if str(v).strip().lower() in ("true", "t", "yes", "y", "1"):
        return True
    if str(v).strip().lower() in ("false", "f", "no", "n", "0"):
        return False
    raise argparse.ArgumentTypeError(f"expected true/false, got {v!r}")


def parse_args():
    p = argparse.ArgumentParser(description="Estimate throughput from QMDL metrics.")
    p.add_argument("--location", "--locations", nargs="+", default=None,
                   help="one or more locations (default: all / LOCATIONS setting)")
    p.add_argument("--dates", "--date", nargs="+", default=None,
                   help="one or more dates (default: all / DATES setting)")
    p.add_argument("--use_speedtest", "--use-speedtest", type=str2bool, nargs="?", const=True,
                   default=None, help="true/false (bare flag = true; default: USE_SPEEDTEST setting)")
    p.add_argument("--window_size", "--window-size", type=float, nargs="+", default=None,
                   help="window size(s) in seconds (default: WINDOW_SIZES_S setting)")
    return p.parse_args()


def main():
    global LOCATIONS, DATES, USE_SPEEDTEST, WINDOW_SIZES_S
    args = parse_args()
    if args.location is not None:
        LOCATIONS = args.location
    if args.dates is not None:
        DATES = args.dates
    if args.use_speedtest is not None:
        USE_SPEEDTEST = args.use_speedtest
    if args.window_size is not None:
        WINDOW_SIZES_S = [int(w) if float(w).is_integer() else w for w in args.window_size]

    if USE_SPEEDTEST:
        qmdl_root = os.path.join(RESULTS_DIR, "qmdl_metrics", "speedtest")
        dl_suffix, ul_suffix = SPEEDTEST_QMDL_DL_SUFFIX, SPEEDTEST_QMDL_UL_SUFFIX
    else:
        qmdl_root = os.path.join(RESULTS_DIR, "qmdl_metrics")
        dl_suffix, ul_suffix = QMDL_DL_SUFFIX, QMDL_UL_SUFFIX

    print(f"Mode: {'speedtest' if USE_SPEEDTEST else 'normal'} | windows: {WINDOW_SIZES_S} s | "
          f"locations: {LOCATIONS or 'all'} | dates: {DATES or 'all'}")

    for op_dir in sorted(glob.glob(os.path.join(qmdl_root, "*")), key=natural_key):
        op = os.path.basename(op_dir)
        if not os.path.isdir(op_dir) or (OPERATORS and op not in OPERATORS):
            continue
        if not USE_SPEEDTEST and op == "speedtest":   # speedtest tree lives under qmdl_metrics/
            continue
        
        for loc_dir in sorted(glob.glob(os.path.join(op_dir, "*")), key=natural_key):
            loc = os.path.basename(loc_dir)
            if not os.path.isdir(loc_dir) or (LOCATIONS and loc not in LOCATIONS):
                continue
            dates = set()
            for suffix in (dl_suffix, ul_suffix):
                for f in glob.glob(os.path.join(loc_dir, f"*{suffix}")):
                    dates.add(os.path.basename(f)[: -len(suffix)])
            print(dates)
            for date in sorted(dates, key=natural_key):
                if DATES and date not in DATES:
                    continue
                process_date(op, loc, date,
                             os.path.join(loc_dir, f"{date}{dl_suffix}"),
                             os.path.join(loc_dir, f"{date}{ul_suffix}"))
    print("Done.")


if __name__ == "__main__":
    main()