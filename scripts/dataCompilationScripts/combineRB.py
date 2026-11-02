"""
Combine 4G (LTE) and 5G (NR) resource-block records per run, per direction.

Input layout:
  qmdl_output/<op>/<loc>/<date>/capture_*/speedtest/
      lte/b139_pusch_tx.csv     (num_rb)        4G UL
      lte/b173_pdsch_stats.csv  (tb_rbs)        4G DL
      readable_b881.csv         (delta_num_prb) 5G UL
      readable_b887.csv         (num_rbs)       5G DL

Output (one folder per operator/location, so dates from different
operators don't overwrite each other):
  <out>/<op>/<loc>/<DATE>_rb_downlink.csv   date, run, timestamp, rat, rb
  <out>/<op>/<loc>/<DATE>_rb_uplink.csv     date, run, timestamp, rat, rb
  <out>/<op>/<loc>/<DATE>_rb_collisions.csv date, run, direction, timestamp,
                                            rb_4g, rb_5g, picked, rb
  <out>/run_summary.csv                     per-run counts and warnings

When 4G and 5G have a record at the same timestamp, the higher RB value is
kept (rat = 4G / 5G / tie) and the case is logged in *_rb_collisions.csv.

Usage: edit the SETTINGS block below, then run
  python combine_rb.py
"""
import glob, os, sys
import numpy as np
import pandas as pd

# ============================ SETTINGS =====================================
# What to process. Each is a list, so you can give one value or several.
OPERATORS = ["Airtel"]            # folder names under qmdl_output/
LOCATIONS = ["indoor_Bharti501"]           # folder names under qmdl_output/<op>/
DATES     = ["20261006"]     # folder names under qmdl_output/<op>/<loc>/

ROOT = "qmdl_output"           # input root folder
OUT="results/rb_combined"           # output root folder
USE_SPEEDTEST = False

TS_COL     = None   # timestamp column name; None = auto-detect
ROUND_MS   = 0      # 0 = exact timestamp match; e.g. 1 = match within a 1 ms bin
WITHIN_RAT = "max"  # several rows of ONE RAT at one timestamp: "max", "sum" or "first"
# ===========================================================================

# SOURCES = {
#     "uplink":   {"4G": ("lte/b139_pusch_tx.csv", "num_rb"),
#                  "5G": ("readable_b881.csv", "delta_num_prb")},
#     "downlink": {"4G": ("lte/b173_pdsch_stats.csv", "tb_rbs"),
#                  "5G": ("readable_b887.csv", "num_rbs")},
# }
SOURCES = {
    "uplink":   {"4G": ("payloads_b139.csv", "num_rb"),
                 "5G": ("payloads_b881.csv", "avg_prb_this_interval")},
    "downlink": {"4G": ("payloads_b173.csv", "tb_rbs"),
                 "5G": ("payloads_b887.csv", "num_rbs")},
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
    """Return datetime64. Handles epoch numbers (s/ms/us/ns) or date strings."""
    num = pd.to_numeric(s, errors="coerce")
    if num.notna().mean() > 0.9:
        m = num.abs().median()
        unit = "ns" if m > 1e17 else "us" if m > 1e14 else "ms" if m > 1e11 else "s"
        return pd.to_datetime(num, unit=unit, errors="coerce")
    return pd.to_datetime(s, errors="coerce")


def read_rat(path, rb_col, ts_override, notes):
    """Return DataFrame[ts, rb] for one CSV, or None if missing/unusable."""
    if not os.path.exists(path):
        notes.append(f"missing {os.path.relpath(path)}")
        return None
    df = pd.read_csv(path, low_memory=False)
    if df.empty:
        notes.append(f"empty {os.path.basename(path)}")
        return None
    if rb_col not in df.columns:
        notes.append(f"no column '{rb_col}' in {os.path.basename(path)}")
        return None
    ts_col = find_ts_col(df.columns, ts_override)
    if ts_col is None:
        notes.append(f"no timestamp column in {os.path.basename(path)} "
                     f"(columns: {list(df.columns)[:8]}...)")
        return None
    out = pd.DataFrame({"ts": parse_ts(df[ts_col]),
                        "rb": pd.to_numeric(df[rb_col], errors="coerce")})
    bad = out.isna().any(axis=1).sum()
    if bad:
        notes.append(f"dropped {bad} unparsable rows in {os.path.basename(path)}")
    return out.dropna()


def collapse_within_rat(df, how, rat, notes):
    """Several rows of the SAME RAT at one timestamp (carriers, TBs, ...)."""
    dup = df["ts"].duplicated(keep=False).sum()
    if dup:
        notes.append(f"{rat}: {dup} rows share a timestamp within {rat} -> {how}")
    return df.groupby("ts", as_index=False)["rb"].agg(how)


def combine_run(run_dir, direction):
    notes = []
    parts = {}
    
    for rat, (rel, col) in SOURCES[direction].items():
        d = read_rat(os.path.join(run_dir, rel), col, TS_COL, notes)
        if d is None or d.empty:
            continue
        if ROUND_MS:
            d["ts"] = d["ts"].dt.round(f"{ROUND_MS}ms")
        parts[rat] = collapse_within_rat(d, WITHIN_RAT, rat, notes)

    # if not parts:
    #     return None, None, notes, {}
    if not parts:
        empty_stats = {"rows_4g": 0, "rows_5g": 0, "collisions": 0, "rows_out": 0}
        return None, None, notes, empty_stats

    empty = pd.DataFrame({"ts": pd.Series(dtype="datetime64[ns]"),
                          "rb": pd.Series(dtype=float)})
    g4 = parts.get("4G", empty).rename(columns={"rb": "rb_4g"})
    g5 = parts.get("5G", empty).rename(columns={"rb": "rb_5g"})
    m = pd.merge(g4, g5, on="ts", how="outer")
    m[["rb_4g", "rb_5g"]] = m[["rb_4g", "rb_5g"]].astype(float)

    has4, has5 = m["rb_4g"].notna(), m["rb_5g"].notna()
    both = has4 & has5
    m["rb"] = m[["rb_4g", "rb_5g"]].max(axis=1)
    r4, r5 = m["rb_4g"].fillna(-1), m["rb_5g"].fillna(-1)
    m["rat"] = np.select([~has5, ~has4, r4 > r5, r5 > r4],
                         ["4G", "5G", "4G", "5G"], default="tie")

    coll = m.loc[both, ["ts", "rb_4g", "rb_5g", "rat", "rb"]].rename(
        columns={"rat": "picked"})
    comb = m[["ts", "rat", "rb"]]
    stats = {"rows_4g": len(g4), "rows_5g": len(g5),
             "collisions": int(both.sum()), "rows_out": len(comb)}
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
        runs = sorted(glob.glob(os.path.join(ddir, "capture_000_20261006_162251")))
        if not runs:
            print(f"No capture_* folders in {ddir}")
            continue
        
        out_dir = os.path.join(OUT, op, loc)
        coll_all = []
        for direction in ("downlink", "uplink"):
            frames = []
            for rdir in runs:
                run = os.path.basename(rdir)
                if USE_SPEEDTEST :
                    comb, coll, notes, st = combine_run(os.path.join(rdir, "speedtest"),
                                                    direction)
                else:
                    comb, coll, notes, st = combine_run(os.path.join(rdir),
                                                    direction)
                summary.append({"op": op, "loc": loc, "date": date, "run": run,
                                "direction": direction, **st,
                                "notes": "; ".join(notes)})
                if comb is None:
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
            out.to_csv(os.path.join(out_dir, f"{date}_rb_{direction}.csv"), index=False)

        if coll_all:
            os.makedirs(out_dir, exist_ok=True)
            c = (pd.concat(coll_all, ignore_index=True)
                   .sort_values(["ts", "run", "direction"], kind="mergesort")
                   .rename(columns={"ts": "timestamp"}))
            c.to_csv(os.path.join(out_dir, f"{date}_rb_collisions.csv"), index=False)

    if not summary:
        sys.exit("Nothing processed.")
    s = pd.DataFrame(summary)
    os.makedirs(OUT, exist_ok=True)
    s.to_csv(os.path.join(OUT, "run_summary.csv"), index=False)
    print(s.groupby(["op", "date", "direction"])[["rows_4g", "rows_5g", "collisions", "rows_out"]]
            .sum().to_string())
    flagged = s[s["notes"].astype(bool)]
    if len(flagged):
        print(f"\n{len(flagged)} run/direction entries have warnings -> see run_summary.csv")
    print(f"\nWritten to {OUT}/")


if __name__ == "__main__":
    main()