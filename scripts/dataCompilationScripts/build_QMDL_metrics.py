"""
Combine 4G (LTE) and 5G (NR) resource-block records per run, per direction.
Also captures expanded metrics like MIMO Layers, MCS, Modulation, TB Size, etc.
Handles missing or empty RAT files gracefully and appends to run_summary.csv.

Input layout:
  qmdl_output/<op>/<loc>/<date>/capture_*/speedtest/ (or run root)
      lte/b139_pusch_tx.csv     4G UL
      lte/b173_pdsch_stats.csv  4G DL
      readable_b881.csv         5G UL
      readable_b887.csv         5G DL

Output:
  <out>/<op>/<loc>/<DATE>_rb_downlink.csv   
  <out>/<op>/<loc>/<DATE>_rb_uplink.csv     
  <out>/<op>/<loc>/<DATE>_rb_collisions.csv 
  <out>/run_summary.csv                     accumulated per-run counts and warnings
"""
import glob, os, sys, argparse
import numpy as np
import pandas as pd

# ============================ SETTINGS =====================================
OPERATORS = ["Airtel", "Jio", "Vodafone"]            # folder names under qmdl_output/
ROOT = "qmdl_output"              # input root folder

TS_COL     = "timestamp_utc"      # timestamp column name; None = auto-detect
ROUND_MS   = 0                    # 0 = exact timestamp match; e.g. 1 = match within 1 ms bin
WITHIN_RAT = "max"                # rows of ONE RAT at one timestamp: "max", "sum" or "first"
# ===========================================================================

# Sources definition with metrics configuration:
SOURCES = {
    "uplink": {
        "4G": ("payloads_b139.csv", "num_rb", {
            "MIMO Layers": None, "MCS": None, "Modulation": "modulation", 
            "mod-order": "mod_order", "Coding Rate": "coding_rate", 
            "TB Size": "tb_size_bytes", "Retransmission": "rv"
        }),
        "5G": ("payloads_b881.csv", "avg_prb_this_interval", {
            "MIMO Layers": None, "MCS": "avg_mcs_this_interval", "Modulation": None, 
            "mod-order": None, "Coding Rate": None, 
            "TB Size": "delta_new_tx_bytes", "Retransmission": "delta_retx_bytes"
        })
    },
    "downlink": {
        "4G": ("payloads_b173.csv", "tb_rbs", {
            "MIMO Layers": "num_layers", "MCS": "mcs", "Modulation": "modulation", 
            "mod-order": None, "Coding Rate": None, 
            "TB Size": "tb_size_bytes", "Retransmission": "rv"
        }),
        "5G": ("payloads_b887.csv", "num_rbs", {
            "MIMO Layers": "num_layers", "MCS": "mcs", "Modulation": None, 
            "mod-order": None, "Coding Rate": None, 
            "TB Size": "tb_size_bytes", "Retransmission": "rv"
        })
    },
}

TS_CANDIDATES = ["timestamp", "time_stamp", "time", "ts", "log_time", "datetime"]

def find_ts_col(cols, override=None):
    if override:
        return override if override in cols else None
    lower = {c.lower().strip(): c for c in cols}
    for c in TS_CANDIDATES:
        if c in lower:
            return lower[c]
    for c in cols:
        if "time" in c.lower():
            return c
    return None

def parse_ts(s):
    num = pd.to_numeric(s, errors="coerce")
    if num.notna().mean() > 0.9:
        m = num.abs().median()
        unit = "ns" if m > 1e17 else "us" if m > 1e14 else "ms" if m > 1e11 else "s"
        return pd.to_datetime(num, unit=unit, errors="coerce")
    return pd.to_datetime(s, errors="coerce")

def read_rat(path, rb_col, metric_map, ts_override, notes):
    """Return DataFrame with timestamp, rb, and extra mapped columns, or None if missing/empty."""
    if not os.path.exists(path):
        notes.append(f"missing {os.path.relpath(path)}")
        return None
    try:
        df = pd.read_csv(path, low_memory=False)
    except Exception as e:
        notes.append(f"error reading {os.path.basename(path)}: {e}")
        return None

    if df.empty:
        notes.append(f"empty {os.path.basename(path)}")
        return None
    if rb_col not in df.columns:
        notes.append(f"no column '{rb_col}' in {os.path.basename(path)}")
        return None
    ts_col = find_ts_col(df.columns, ts_override)
    if ts_col is None:
        notes.append(f"no timestamp column in {os.path.basename(path)}")
        return None
    
    # Build core dataframe dictionary
    data_dict = {
        "ts": parse_ts(df[ts_col]),
        "Resource blocks": pd.to_numeric(df[rb_col], errors="coerce")
    }
    
    # Map additional user metrics if column exists in CSV
    for target_col, src_col in metric_map.items():
        if src_col and src_col in df.columns:
            converted = pd.to_numeric(df[src_col], errors="coerce")
            data_dict[target_col] = converted if converted.notna().any() else df[src_col]
        else:
            data_dict[target_col] = np.nan

    out = pd.DataFrame(data_dict)
    bad = out["Resource blocks"].isna().sum()
    if bad:
        notes.append(f"dropped {bad} unparsable rows in {os.path.basename(path)}")
    
    cleaned = out.dropna(subset=["ts", "Resource blocks"])
    if cleaned.empty:
        notes.append(f"all rows dropped after cleaning {os.path.basename(path)}")
        return None
    return cleaned

def collapse_within_rat(df, how, rat, notes):
    """Several rows of the SAME RAT at one timestamp."""
    dup = df["ts"].duplicated(keep=False).sum()
    if dup:
        notes.append(f"{rat}: {dup} rows share a timestamp within {rat} -> {how}")
    
    agg_dict = {col: how if pd.api.types.is_numeric_dtype(df[col]) else 'first' for col in df.columns if col != "ts"}
    return df.groupby("ts", as_index=False).agg(agg_dict)

def combine_run(run_dir, direction):
    notes = []
    parts = {}
    
    for rat, (rel, rb_col, metric_map) in SOURCES[direction].items():
        d = read_rat(os.path.join(run_dir, rel), rb_col, metric_map, TS_COL, notes)
        if d is not None and not d.empty:
            if ROUND_MS:
                d["ts"] = d["ts"].dt.round(f"{ROUND_MS}ms")
            parts[rat] = collapse_within_rat(d, WITHIN_RAT, rat, notes)

    if not parts:
        empty_stats = {"rows_4g": 0, "rows_5g": 0, "collisions": 0, "rows_out": 0}
        return None, None, notes, empty_stats

    # Safely extract and format g4 and g5 if available
    g4 = parts.get("4G")
    if g4 is not None and not g4.empty:
        g4 = g4.rename(columns={c: f"{c}_4g" for c in g4.columns if c != "ts"})
    else:
        g4 = pd.DataFrame(columns=["ts"])

    g5 = parts.get("5G")
    if g5 is not None and not g5.empty:
        g5 = g5.rename(columns={c: f"{c}_5g" for c in g5.columns if c != "ts"})
    else:
        g5 = pd.DataFrame(columns=["ts"])

    m = pd.merge(g4, g5, on="ts", how="outer")

    has4 = m["Resource blocks_4g"].notna() if "Resource blocks_4g" in m.columns else pd.Series(False, index=m.index)
    has5 = m["Resource blocks_5g"].notna() if "Resource blocks_5g" in m.columns else pd.Series(False, index=m.index)
    both = has4 & has5

    # Determine winning RAT based on Resource blocks comparison
    r4 = m["Resource blocks_4g"].fillna(-1) if "Resource blocks_4g" in m.columns else pd.Series(-1, index=m.index)
    r5 = m["Resource blocks_5g"].fillna(-1) if "Resource blocks_5g" in m.columns else pd.Series(-1, index=m.index)
    
    m["radio_connection"] = np.select([~has5, ~has4, r4 > r5, r5 > r4],
                                       ["4G", "5G", "4G", "5G"], default="tie")

    # Select winning attributes dynamically for each column field
    target_fields = ["Resource blocks", "MIMO Layers", "MCS", "Modulation", "mod-order", "Coding Rate", "TB Size", "Retransmission"]
    for field in target_fields:
        col_4g = f"{field}_4g"
        col_5g = f"{field}_5g"
        
        has_4g_col = col_4g in m.columns
        has_5g_col = col_5g in m.columns
        
        if has_4g_col and has_5g_col:
            m[field] = np.select(
                [m["radio_connection"] == "4G", m["radio_connection"] == "5G"],
                [m[col_4g], m[col_5g]],
                default=m[[col_4g, col_4g]].max(axis=1)
            )
        elif has_4g_col:
            m[field] = m[col_4g]
        elif has_5g_col:
            m[field] = m[col_5g]
        else:
            m[field] = np.nan

    # Build collision log columns safely using .any()
    if both.any():
        coll = m.loc[both, ["ts"]].copy()
        coll["rb_4g"] = m.loc[both, "Resource blocks_4g"] if "Resource blocks_4g" in m.columns else np.nan
        coll["rb_5g"] = m.loc[both, "Resource blocks_5g"] if "Resource blocks_5g" in m.columns else np.nan
        coll["picked"] = m.loc[both, "radio_connection"]
        coll["rb"] = m.loc[both, "Resource blocks"]
    else:
        coll = pd.DataFrame(columns=["ts", "rb_4g", "rb_5g", "picked", "rb"])

    # Final combined schema order
    output_cols = ["ts", "radio_connection", "Resource blocks", "MIMO Layers", "MCS", "Modulation", "mod-order", "Coding Rate", "TB Size", "Retransmission"]
    comb = m[[c for c in output_cols if c in m.columns]]

    stats = {
        "rows_4g": len(parts.get("4G")) if "4G" in parts and parts["4G"] is not None else 0, 
        "rows_5g": len(parts.get("5G")) if "5G" in parts and parts["5G"] is not None else 0,
        "collisions": int(both.sum()) if isinstance(both, pd.Series) else 0, 
        "rows_out": len(comb)
    }
    return comb, coll, notes, stats

def main():
    if WITHIN_RAT not in ("max", "sum", "first"):
        sys.exit(f'WITHIN_RAT must be "max", "sum" or "first", not {WITHIN_RAT!r}')

    date_dirs, missing = [], []
    for op in OPERATORS:
        for loc in LOCATIONS:
            for date in DATES:
                d = os.path.join(ROOT, op, loc, date)
                (date_dirs if os.path.isdir(d) else missing).append(d)
    for d in missing:
        print(f"Skipping (folder not found): {d}")
    if not date_dirs:
        sys.exit("None of the requested operator/location/date folders exist.")

    summary = []
    for ddir in date_dirs:
        op, loc, date = os.path.normpath(ddir).split(os.sep)[-3:]
        runs = sorted(glob.glob(os.path.join(ddir, "capture_*")))
        if not runs:
            print(f"No capture_* folders in {ddir}")
            continue
        
        out_dir = os.path.join(OUT, op, loc)
        coll_all = []
        for direction in ("downlink", "uplink"):
            frames = []
            for rdir in runs:
                run = os.path.basename(rdir)
                print(rdir)
                if USE_SPEEDTEST:
                    sub_matches = glob.glob(os.path.join(rdir, "speedtest_qmdl_*"))
                    target_dir = sub_matches[0] if sub_matches else rdir
                else:
                    target_dir = rdir
                comb, coll, notes, st = combine_run(target_dir, direction)
                
                summary.append({"op": op, "loc": loc, "date": date, "run": run,
                                "direction": direction, **st,
                                "notes": "; ".join(notes)})
                if comb is None or comb.empty:
                    continue
                comb.insert(0, "run", run)
                comb.insert(0, "date", date)
                frames.append(comb)
                if len(coll):
                    coll.insert(0, "direction", direction)
                    coll.insert(0, "run", run)
                    coll.insert(0, "date", date)
                    coll_all.append(coll)
            if not frames:
                continue
            os.makedirs(out_dir, exist_ok=True)
            out = (pd.concat(frames, ignore_index=True)
                     .sort_values(["ts", "run"], kind="mergesort")
                     .rename(columns={"ts": "timestamp"}))
            out.to_csv(os.path.join(out_dir, f"{date}_{direction}.csv"), index=False)

        if coll_all:
            os.makedirs(out_dir, exist_ok=True)
            c = (pd.concat(coll_all, ignore_index=True)
                   .sort_values(["ts", "run", "direction"], kind="mergesort")
                   .rename(columns={"ts": "timestamp"}))
            c.to_csv(os.path.join(out_dir, f"{date}_collisions.csv"), index=False)

    if not summary:
        sys.exit("Nothing processed.")
    
    s_new = pd.DataFrame(summary)
    os.makedirs(OUT, exist_ok=True)
    summary_path = os.path.join(OUT, "run_summary.csv")
    
    # Append/Update summary instead of overwriting completely
    if os.path.exists(summary_path):
        try:
            s_old = pd.read_csv(summary_path)
            s = pd.concat([s_old, s_new], ignore_index=True)
            # Remove duplicates if re-running the same runs
            s = s.drop_duplicates(subset=["op", "loc", "date", "run", "direction"], keep="last")
        except Exception:
            s = s_new
    else:
        s = s_new
        
    s.to_csv(summary_path, index=False)
    print(s.groupby(["op", "date", "direction"])[["rows_4g", "rows_5g", "collisions", "rows_out"]]
            .sum().to_string())
    flagged = s[s["notes"].astype(bool)]
    if len(flagged):
        print(f"\n{len(flagged)} run/direction entries have warnings -> see run_summary.csv")
    print(f"\nWritten to {OUT}/")

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
    parser.add_argument(
        "--use_speedtest",
        action="store_true",
        help="Enable speedtest processing",
    )
    args = parser.parse_args()
    LOCATIONS = args.locations
    DATES = args.dates
    USE_SPEEDTEST = args.use_speedtest
    if USE_SPEEDTEST:
        OUT  = "results/qmdl_metrics/speedtest"
    else :
        OUT  = "results/qmdl_metrics"
    main()