#!/usr/bin/env python3
"""
Time-windowed QMDL metrics + stacked bars of how much of the experiment
DURATION each operator spent on 4G, 5G, a 4G/5G tie, or with no data (Unknown).

Stage 1 - windowed CSV (RUN_WINDOWING)
  Reads   IN_DIR/<op>/<loc>/<date>_<direction>.csv
            date,run,timestamp,radio_connection,Resource blocks,MIMO Layers,MCS,
            Modulation,mod-order,Coding Rate,TB Size,Retransmission
  Writes  CSV_DIR/<op>/<loc>/<date>_<direction>_win<W>ms.csv   (one row per window)
  radio_connection of a window, from the share of its records:
    all records 4G (or all 5G)        -> 4G (or 5G)
    4G and 5G records 50-50           -> tie
    otherwise                         -> whichever RAT has the larger share
    no records in the window          -> Unknown
    (an input row already labelled "tie" counts once for 4G and once for 5G)
  Metrics are aggregated over the records of the winning RAT (all records for
  a tie), so 4G and 5G values are not mixed. n_4g, n_5g and share_5g keep the
  mix of every window.
  Aggregation:
    Resource blocks  mean      typical allocation size
    MIMO Layers      median    typical layer count (robust; integer-valued data)
    MCS              mean      over valid indices only - retransmission indices
                               (5G 28-31, 4G 29-31) carry no MCS level and are
                               excluded
    mod-order        low median  ordinal: the lower median is always a real
                               modulation order (a plain median of 4 and 6 = 5)
    Modulation       name of that mod-order (strings have no median)
    Coding Rate      mean
    TB Size          sum over NEW transmissions only (a retransmitted TB is the
                     same data sent again; summing it would double-count)
    Retransmission   mean = fraction of records that are retransmissions
                     (the median of a 0/1 flag is just a majority vote)
    n_records, n_retx   counts, for weighting / filtering later

Stage 2 - bar plots (RUN_PLOTS), from the windowed CSVs only
  % of experiment duration = (number of windows in the class x WINDOW_MS) /
  run duration, classes 4G / tie / 5G / Unknown.
  Outputs
    OUTDIR/<loc>/<date>/<op>/<run>_<direction>_win<W>ms.png           one bar per run
    OUTDIR/<loc>/<date>/<date>_<direction>_win<W>ms_consolidated.png  one bar per operator
  (the numbers behind the consolidated bars are printed to the console)

Paths
  USE_SPEEDTEST = True : IN_DIR  results/qmdl_metrics/speedtest
                         CSV_DIR results/fallback/speedtest
                         OUTDIR  graphs/speedtest/fallback_graphs
  USE_SPEEDTEST = False: IN_DIR  results/qmdl_metrics
                         CSV_DIR results/fallback
                         OUTDIR  graphs/dummyVC/fallback_graphs

Usage: LOCATIONS, DATES, WINDOW_MS and USE_SPEEDTEST are given on the command line
(all four are required):
  python plot_fallback_bars.py --locations indoor_AzadApt --dates 20261013 20261015 \
                               --window_ms 100 --use_speedtest True
"""
from pathlib import Path
import sys, argparse
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ============================ SETTINGS =====================================
# LOCATIONS, DATES, WINDOW_MS and USE_SPEEDTEST come from the command line
# (all four are required):
#   --locations indoor_AzadApt --dates 20261013 20261015 --window_ms 100 --use_speedtest True
OPERATORS = None                      # e.g. ["Airtel", "Jio"]; None = all found
DIRECTIONS = ["downlink", "uplink"]

PATHS = {   # USE_SPEEDTEST -> (IN_DIR, CSV_DIR, OUTDIR)
    True:  ("results/qmdl_metrics/speedtest", "results/granular_qmdl_metrics/speedtest",
            "graphs/speedtest/fallback_graphs"),
    False: ("results/qmdl_metrics", "results/granular_qmdl_metrics",
            "graphs/dummyVC/fallback_graphs"),
}

# Experiment duration per run:
#   None -> from the run's first to its last QMDL record
#   e.g. 40 -> a fixed 40 s from the run's first record; missing time at the
#              end then counts as Unknown
EXPERIMENT_DURATION_S = None

# Records whose timestamp is more than this many seconds from the middle of
# their run (e.g. a 1970 placeholder, a value in the wrong unit) are filtered
# out, and the file is reported. Keep it above your longest run.
MAX_RUN_DURATION_S = 3600

RUN_WINDOWING = True            # stage 1: (re)build the windowed CSVs
RUN_PLOTS = True                # stage 2: plots from the windowed CSVs

NAIVE_TZ = "UTC"                # timezone for timestamps without an offset
RAT_COL = "radio_connection"
LABEL_MIN_PCT = 4               # don't write % labels on segments thinner than this
# ===========================================================================

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "font.size": 10, "legend.fontsize": 8, "legend.fancybox": True,
    "axes.linewidth": 0.5, "grid.linewidth": 0.25, "patch.linewidth": 0.5,
    "xtick.major.width": 0.25, "ytick.major.width": 0.25,
    "pdf.fonttype": 42, "ps.fonttype": 42,
})
DUR_CATS  = ["4G", "tie", "5G", "Unknown"]
DUR_COLOR = {"4G": "#348ABD", "tie": "#7A68A6", "5G": "#A60628", "Unknown": "#BBBBBB"}
DUR_LABEL = {"4G": "4G", "tie": "Tie (50-50)", "5G": "5G", "Unknown": "Unknown"}
QM_NAME = {1: "BPSK", 2: "QPSK", 4: "16QAM", 6: "64QAM", 8: "256QAM", 10: "1024QAM",
           16: "16QAM", 64: "64QAM", 256: "256QAM", 1024: "1024QAM"}   # Qm or M
METRIC_COLS = ["Resource blocks", "MIMO Layers", "MCS", "Modulation", "mod-order",
               "Coding Rate", "TB Size", "Retransmission"]


def as_list(x):
    return None if x is None else ([x] if isinstance(x, str) else list(x))


def wanted(op, loc, date):
    # read the settings at call time, so command-line overrides take effect
    ops, locs, dates = as_list(OPERATORS), as_list(LOCATIONS), as_list(DATES)
    return ((not ops or op in ops) and (not locs or loc in locs)
            and (not dates or date in dates))


def set_paths():
    global IN_DIR, CSV_DIR, OUTDIR
    IN_DIR, CSV_DIR, OUTDIR = (Path(p) for p in PATHS[bool(USE_SPEEDTEST)])


# ---------------------------------------------------------------- helpers
def norm_rat(v):
    s = str(v).strip().lower()
    if s in ("tie", "both"):
        return "tie"
    if "lte" in s or s.startswith("4"):
        return "4G"
    if s.startswith("5") or s.startswith("nr"):
        return "5G"
    return None


def to_utc_ms(s):
    """Timestamps (epoch numbers or strings, with or without offset) -> ms UTC."""
    n = pd.to_numeric(s, errors="coerce")
    if n.notna().mean() > 0.9:
        m = n.abs().median()
        return n * (1e-6 if m > 1e17 else 1e-3 if m > 1e14 else 1.0 if m > 1e11 else 1e3)
    txt = s.astype(str).str.strip()
    has_off = txt.str.contains(r"(?:[+-]\d{2}:?\d{2}|Z)$", regex=True)
    out = pd.Series(np.nan, index=s.index)
    epoch = pd.Timestamp("1970-01-01", tz="UTC")
    if has_off.any():
        dt = pd.to_datetime(txt[has_off], errors="coerce", format="mixed", utc=True)
        out[has_off] = (dt - epoch) / pd.Timedelta(milliseconds=1)
    if (~has_off).any():
        dt = pd.to_datetime(txt[~has_off], errors="coerce", format="mixed")
        dt = dt.dt.tz_localize(NAIVE_TZ, ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
        out[~has_off] = (dt - epoch) / pd.Timedelta(milliseconds=1)
    return out


def find(df, name):
    return {c.lower().strip(): c for c in df.columns}.get(name.lower().strip())


def low_median(s):
    s = s.dropna().sort_values()
    return s.iloc[(len(s) - 1) // 2] if len(s) else np.nan


# ======================================================================
# Stage 1: windowed CSV
# ======================================================================
def window_file(f, direction):
    df = pd.read_csv(f, low_memory=False, dtype={"run": str})
    rc = find(df, RAT_COL)
    if rc is None or "run" not in df.columns or "timestamp" not in df.columns:
        print(f"[!] {f}: needs run, timestamp and {RAT_COL} columns - skipped", file=sys.stderr)
        return None
    col = {k: find(df, k) for k in METRIC_COLS}
    num = lambda k: pd.to_numeric(df[col[k]], errors="coerce") if col[k] else np.nan

    df = df.reset_index(drop=True)              # rec shares this index (for error examples)
    rec = pd.DataFrame({
        "date": df["date"] if "date" in df.columns else f.name.split("_")[0],
        "run": df["run"], "rat": df[rc].map(norm_rat),
        "t": to_utc_ms(df["timestamp"]),
        "prb": num("Resource blocks"), "layers": num("MIMO Layers"), "mcs": num("MCS"),
        "mod_order": num("mod-order"), "code_rate": num("Coding Rate"),
        "tbs": num("TB Size"), "retx": (num("Retransmission") > 0).astype(float),
    })
    if col["Retransmission"] is None:
        rec["retx"] = np.nan
    # mod-order missing but Modulation given -> derive it
    if col["Modulation"]:
        name2qm = {"BPSK": 1, "PI/2BPSK": 1, "QPSK": 2, "16QAM": 4, "64QAM": 6,
                   "256QAM": 8, "1024QAM": 10}
        qm = (df[col["Modulation"]].astype(str).str.upper()
                .str.replace(r"[\s_\-]", "", regex=True).map(name2qm))
        rec["mod_order"] = rec["mod_order"].fillna(qm)

    dropped = rec["rat"].isna().sum() + rec["t"].isna().sum()
    if dropped:
        print(f"[!] {f.name}: {dropped} rows with unknown RAT or unparsable time dropped",
              file=sys.stderr)
    rec = rec.dropna(subset=["rat", "t"])

    # MCS indices that only signal a retransmission carry no MCS level
    reserved = ((rec["rat"].isin(["5G", "tie"]) & (rec["mcs"] >= 28))
                | ((rec["rat"] == "4G") & (rec["mcs"] >= 29)))
    rec.loc[reserved, "mcs"] = np.nan
    rec.loc[rec["retx"] == 1, "tbs"] = np.nan          # count each TB once

    out = []
    for run, r in rec.groupby("run", sort=True):
        # filter out records whose timestamp is far from the rest of the run
        far = (r["t"] - r["t"].median()).abs() > MAX_RUN_DURATION_S * 1000
        if far.any():
            ex = df.loc[r.index[far], "timestamp"].astype(str).unique()[:3]
            print(f"[!] anomalous timestamps in {f} (run {run}): {far.sum()} record(s) "
                  f"filtered out, e.g. {', '.join(ex)}", file=sys.stderr)
            r = r[~far]

        t0 = np.floor(r["t"].min())
        span_ms = (EXPERIMENT_DURATION_S * 1000 if EXPERIMENT_DURATION_S
                   else r["t"].max() - t0 + 1)
        n_win = int(np.ceil(span_ms / WINDOW_MS))
        r = r.assign(win=np.floor((r["t"] - t0) / WINDOW_MS).astype(int))
        outside = (r["win"] >= n_win).sum()
        if outside:
            print(f"[!] {f.name} {run}: {outside} records after EXPERIMENT_DURATION_S ignored",
                  file=sys.stderr)
        r = r[r["win"] < n_win]

        # share of 4G / 5G records per window ("tie" rows count for both)
        is_tie = r["rat"] == "tie"
        cnt = pd.DataFrame({
            "n_4g": ((r["rat"] == "4G") | is_tie).astype(int),
            "n_5g": ((r["rat"] == "5G") | is_tie).astype(int),
            "win": r["win"],
        }).groupby("win").sum()
        label = pd.Series(np.select([cnt.n_4g > cnt.n_5g, cnt.n_5g > cnt.n_4g],
                                    ["4G", "5G"], default="tie"), index=cnt.index)

        # aggregate over the winning RAT's records (all records for a tie)
        r = r.assign(label=r["win"].map(label))
        keep = (r["label"] == "tie") | (r["rat"] == r["label"]) | is_tie
        g = r[keep].groupby("win")
        agg = pd.DataFrame({
            "n_records": g.size(),
            "n_retx": g["retx"].sum(min_count=1),
            "Resource blocks": g["prb"].mean(),
            "MIMO Layers": g["layers"].median(),
            "MCS": g["mcs"].mean(),
            "mod-order": g["mod_order"].agg(low_median),
            "Coding Rate": g["code_rate"].mean(),
            "TB Size": g["tbs"].sum(min_count=1),
            "Retransmission": g["retx"].mean(),
        })
        agg = agg.join(cnt).join(label.rename("radio_connection"))
        agg["Modulation"] = agg["mod-order"].map(QM_NAME)

        # every window of the run; windows with no records -> Unknown
        agg = agg.reindex(pd.RangeIndex(n_win, name="win")).reset_index()
        agg["radio_connection"] = agg["radio_connection"].fillna("Unknown")
        for c in ("n_records", "n_4g", "n_5g"):
            agg[c] = agg[c].fillna(0).astype(int)
        both = agg["n_4g"] + agg["n_5g"]
        agg["share_5g"] = (agg["n_5g"] / both.where(both > 0)).round(4)
        agg["window_ms"] = np.minimum(WINDOW_MS, span_ms - agg["win"] * WINDOW_MS).round(3)
        agg["window_start_ms"] = (t0 + agg["win"] * WINDOW_MS).astype(np.int64)
        agg["run"] = run
        agg["date"] = r["date"].iloc[0] if len(r) else ""
        out.append(agg)

    if not out:
        return None
    res = pd.concat(out, ignore_index=True)
    res["timestamp"] = (pd.to_datetime(res["window_start_ms"], unit="ms", utc=True)
                               .dt.strftime("%Y-%m-%d %H:%M:%S.%f").str[:-3] + "+00:00")
    cols = ["date", "run", "timestamp", "window_start_ms", "window_ms",
            "radio_connection", "n_4g", "n_5g", "share_5g", "n_records", "n_retx"] + METRIC_COLS
    return res[cols]


def stage_windowing():
    n = 0
    for direction in DIRECTIONS:
        for f in sorted(IN_DIR.glob(f"*/*/*_{direction}.csv")):
            op, loc = f.parent.parent.name, f.parent.name
            date = f.name[: -len(f"_{direction}.csv")]
            if not wanted(op, loc, date):
                continue
            res = window_file(f, direction)
            if res is None:
                continue
            dst = CSV_DIR / op / loc / f"{date}_{direction}_win{WINDOW_MS}ms.csv"
            dst.parent.mkdir(parents=True, exist_ok=True)
            res.round(4).to_csv(dst, index=False)
            n += 1
            share = res.groupby("radio_connection")["window_ms"].sum() / res["window_ms"].sum() * 100
            print(f"[✓] {op}/{loc}/{date} {direction}: {res['run'].nunique()} runs, "
                  f"{len(res):,} windows of {WINDOW_MS} ms -> {dst} | "
                  + ", ".join(f"{k} {share.get(k, 0):.1f}%" for k in DUR_CATS))
    print(f"Stage 1: {n} windowed file(s) written under {CSV_DIR}/\n")


# ======================================================================
# Stage 2: duration plots from the windowed CSVs
# ======================================================================
def load_windows(direction):
    frames = []
    suffix = f"_{direction}_win{WINDOW_MS}ms.csv"
    for f in sorted(CSV_DIR.glob(f"*/*/*{suffix}")):
        op, loc = f.parent.parent.name, f.parent.name
        date = f.name[: -len(suffix)]
        if not wanted(op, loc, date):
            continue
        d = pd.read_csv(f, dtype={"run": str},
                        usecols=["run", "window_start_ms", "window_ms", "radio_connection"])
        d = d.drop_duplicates(["run", "window_start_ms"])     # one row per window
        d["op"], d["loc"], d["date"] = op, loc, date
        frames.append(d)
    return pd.concat(frames, ignore_index=True) if frames else None


def summarise(df, key):
    """% of duration per class, one row per value of `key`."""
    rows = []
    for k, g in df.groupby(key, sort=False):
        total = g["window_ms"].sum()
        dur = g.groupby("radio_connection")["window_ms"].sum()
        r = {key: k, "duration_s": total / 1000, "runs": g["run"].nunique()}
        for c in DUR_CATS:
            r[f"{c} %"] = 100 * dur.get(c, 0) / total if total else np.nan
            r[f"{c} s"] = dur.get(c, 0) / 1000
        rows.append(r)
    return pd.DataFrame(rows).set_index(key)


def stacked(ax, s, title):
    labels = list(s.index)
    y = np.arange(len(labels))[::-1]
    left = np.zeros(len(labels))
    for c in DUR_CATS:
        v = s[f"{c} %"].fillna(0).to_numpy()
        ax.barh(y, v, left=left, height=0.6, color=DUR_COLOR[c], label=DUR_LABEL[c],
                edgecolor="white", linewidth=0.5)
        for yi, l, w in zip(y, left, v):
            if w >= LABEL_MIN_PCT:
                ax.text(l + w / 2, yi, f"{w:.0f}%", ha="center", va="center", fontsize=7,
                        color="black" if c == "Unknown" else "white", fontweight="bold")
        left += v
    for yi, lab in zip(y, labels):
        ax.text(101.5, yi, f"{s.loc[lab, 'duration_s']:.0f} s", ha="left", va="center", fontsize=7)
    ax.set_yticks(y, labels)
    ax.set_ylim(-0.6, len(labels) - 0.4)
    ax.set_xlim(0, 115)
    ax.set_xticks(range(0, 101, 20))
    ax.set_xlabel("% of experiment duration", fontweight="bold", fontsize=8)
    ax.set_title(title, fontsize=9, fontweight="bold", loc="left")
    ax.grid(axis="x", linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", bbox_to_anchor=(1.0, 1.0), frameon=False)


def plot(s, title, subtitle, out_path):
    h = 0.9 + 0.45 * len(s)
    fig, ax = plt.subplots(figsize=(6.5, h + 0.5))
    stacked(ax, s, subtitle)
    fig.suptitle(title, fontsize=10, fontweight="bold")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def stage_plots():
    n_figs = 0
    sub = f"Radio connection per {WINDOW_MS} ms window"
    for direction in DIRECTIONS:
        df = load_windows(direction)
        if df is None:
            print(f"[!] no *_{direction}_win{WINDOW_MS}ms.csv under {CSV_DIR} "
                  f"(run with RUN_WINDOWING = True)", file=sys.stderr)
            continue
        for (loc, date), day in df.groupby(["loc", "date"]):
            out_dir = OUTDIR / loc / date
            tables = []
            for (op, run), g in day.groupby(["op", "run"]):
                s = summarise(g.assign(label=op), "label")
                plot(s, f"{direction.capitalize()} — {loc} / {date} / {op} / {run}", sub,
                     out_dir / op / f"{run}_{direction}_win{WINDOW_MS}ms.png")
                tables.append(s.reset_index().rename(columns={"label": "operator"}).assign(run=run))
                n_figs += 1
            s = summarise(day, "op")
            plot(s, f"{direction.capitalize()} — {loc} / {date} (all runs)", sub,
                 out_dir / f"{date}_{direction}_win{WINDOW_MS}ms_consolidated.png")
            tables.append(s.reset_index().rename(columns={"op": "operator"}).assign(run="ALL"))
            n_figs += 1

            t = pd.concat(tables, ignore_index=True)
            cols = (["run", "operator", "runs", "duration_s"] + [f"{c} %" for c in DUR_CATS]
                    + [f"{c} s" for c in DUR_CATS])
            t = t[cols].round(2)
            print(f"== {direction} | {loc} | {date} | window {WINDOW_MS} ms")
            print(t[t.run == "ALL"][["operator", "runs", "duration_s"]
                                    + [f"{c} %" for c in DUR_CATS]].to_string(index=False))
            print()
    print(f"Stage 2: {n_figs} figure(s) written under {OUTDIR}/")


def main():
    mode = "speedtest" if USE_SPEEDTEST else "dummy VC"
    print(f"Mode: {mode} | window {WINDOW_MS} ms | locations {LOCATIONS} | dates {DATES}\n"
          f"  IN_DIR  {IN_DIR}\n  CSV_DIR {CSV_DIR}\n  OUTDIR  {OUTDIR}\n")
    if not IN_DIR.exists():
        print(f"[!] input folder {IN_DIR} does not exist", file=sys.stderr)
    if RUN_WINDOWING:
        stage_windowing()
    if RUN_PLOTS:
        stage_plots()


if __name__ == "__main__":
    # All four options are required: they are the only source of these values.
    parser = argparse.ArgumentParser()
    parser.add_argument("--locations", nargs="+", required=True,
                        help="Measurement locations (space-separated)")
    parser.add_argument("--dates", nargs="+", required=True,
                        help="Dates in YYYYMMDD format (space-separated)")
    def str2bool(v):
        s = str(v).strip().lower()
        if s in ("true", "t", "yes", "y", "1"):
            return True
        if s in ("false", "f", "no", "n", "0"):
            return False
        raise argparse.ArgumentTypeError(f"expected True or False, got {v!r}")

    parser.add_argument("--use_speedtest", type=str2bool, required=True,
                        help="True = speedtest folders, False = dummy VC folders")
    parser.add_argument("--window_ms", type=int, required=True,
                        help="Window size in ms, e.g. 100")
    args = parser.parse_args()
    LOCATIONS = args.locations
    DATES = args.dates
    USE_SPEEDTEST = args.use_speedtest
    WINDOW_MS = args.window_ms
    set_paths()          # IN_DIR, CSV_DIR, OUTDIR from USE_SPEEDTEST
    main()