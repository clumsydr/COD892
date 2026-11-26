#!/usr/bin/env python3
"""
Throughput with vs without retransmissions, per operator.

For every location and direction, makes one figure per day and one for all days pooled:
  left subplot : seconds with Retransmission == 0
  right subplot: seconds with Retransmission  > 0
Each subplot has one bar per operator: bar = mean throughput, error bar = std,
mean written on top, sample count (n) under the operator name. Both subplots share
the y-axis so they can be compared directly.

Inputs
  PHY  : <GRAN_ROOT>/<operator>/<location>/<GRAN_FILE>     (one file per date and direction)
         columns used: run, window_start_ms, Retransmission
  Tput : <TPUT_ROOT>/<operator>/<location>/<date>/capture_*/throughput_1s_capture_*.csv
         columns used: Timestamp, Download (Mbps) / Upload (Mbps)
Runs are matched by the capture id in their names (e.g. 20261006_162251), and seconds
are matched as window_start_ms / 1000 == Timestamp.

Output
  <GRAPHS_DIR>/<location>/<date>_<direction>_retx.png
  <GRAPHS_DIR>/<location>/all_dates_<direction>_retx.png

Usage: edit the CONFIG block below, then run  python retx_throughput_plots.py
"""
import re
from datetime import date, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ───────────────────────────── CONFIG ──────────────────────────────
USE_SPEEDTEST = True            # True: speedtest captures; False: dummyVC captures

if USE_SPEEDTEST:
    GRAPHS_DIR = Path("graphs/speedtest/Retx_extra_plots")
    GRAN_ROOT = Path("results/granular_qmdl_metrics/speedtest")
    TPUT_GLOB = "capture_*/speedtest_qmdl_*/throughput_1s_speedtest_*.csv"   # inside <op>/<loc>/<date>/
else:
    GRAPHS_DIR = Path("graphs/dummyVC/Retx_extra_plots")
    GRAN_ROOT = Path("results/granular_qmdl_metrics")
    TPUT_GLOB = "capture_*/throughput_1s_capture_*.csv"                      # inside <op>/<loc>/<date>/
TPUT_ROOT = Path("results/Throughput")
GRAN_FILE = "{date}_{direction}_win1000ms.csv"      # file name inside <operator>/<location>/

OPERATORS = ["Airtel", "Jio", "Vodafone"]
LOCATIONS = ["indoor_Bharti501", "indoor_BlueTokai"]

START_DATE, END_DATE = date(2026, 10, 6), date(2026, 10, 13)   # both inclusive
DATES = [(START_DATE + timedelta(days=i)).strftime("%Y%m%d")
         for i in range((END_DATE - START_DATE).days + 1)]

# direction in the PHY file name -> throughput column to use
DIRECTIONS = {"downlink": "Download (Mbps)", "uplink": "Upload (Mbps)"}

RUN_COL = "run"
RETX_COL = "Retransmission"
GRAN_TIME_COL = "window_start_ms"
GRAN_TIME_SCALE = 1000          # window_start_ms / 1000 -> seconds
ALIGN_OFFSET_S = 0              # shift PHY seconds vs throughput seconds if the two start apart
TPUT_TIME_COL = "Timestamp"

DROP_ZERO_TPUT = True           # ignore seconds with 0 Mbps (idle seconds pull the mean down)
MAX_TPUT = None                 # e.g. 500 to drop values above it; None = no upper limit
# ───────────────────────────────────────────────────────────────────

# Setting Graph Specifications
plt.rcParams["font.family"] = "serif"
plt.rcParams["font.serif"] = ["Times New Roman", "Times", "DejaVu Serif"]
plt.rcParams.update({
    "text.usetex": False,
    "font.size": 10,
    "legend.fontsize": 8,
    "axes.linewidth": 0.5,
    "patch.linewidth": 0.5,
    "lines.linewidth": 1.0,
    "grid.linewidth": 0.25,
    "xtick.major.width": 0.25,
    "ytick.major.width": 0.25,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})
OP_COLORS = ["#348ABD", "#A60628", "#7A68A6", "#467821", "#CF4457", "#188487", "#E24A33"]

KEY_RE = re.compile(r"(\d{8}_\d{6})")


def log(msg):
    print(msg, flush=True)


def capture_key(name):
    """'capture_000_20261006_162251' / 'throughput_1s_capture_20261006_162251.csv' -> '20261006_162251'."""
    m = KEY_RE.findall(str(name))
    return m[-1] if m else str(name)


# ───────────────────────────── loading ─────────────────────────────
def load_day(op, loc, d, direction, tcol):
    """PHY seconds of one operator/location/date joined with that second's throughput."""
    gran_path = GRAN_ROOT / op / loc / GRAN_FILE.format(date=d, direction=direction)
    if not gran_path.exists():
        return None

    g = pd.read_csv(gran_path)
    missing = [c for c in (RUN_COL, RETX_COL, GRAN_TIME_COL) if c not in g.columns]
    if missing:
        log(f"  ! {gran_path}: missing columns {missing}")
        return None

    g["_sec"] = np.floor(pd.to_numeric(g[GRAN_TIME_COL], errors="coerce") / GRAN_TIME_SCALE)
    g[RETX_COL] = pd.to_numeric(g[RETX_COL], errors="coerce")
    g = g.dropna(subset=["_sec", RETX_COL])
    g["_key"] = g[RUN_COL].map(capture_key)
    # PHY time is UTC; throughput Timestamp is 0..N s. Make PHY relative per run:
    # first PHY second of each run = second 0 (+ ALIGN_OFFSET_S).
    g["_sec"] = (g["_sec"] - g.groupby("_key")["_sec"].transform("min")
                 + ALIGN_OFFSET_S).astype(np.int64)

    tput_files = {capture_key(p.name): p
                  for p in sorted((TPUT_ROOT / op / loc / d).glob(TPUT_GLOB))
                  if not p.name.startswith("._")}

    frames = []
    for key, run_rows in g.groupby("_key"):
        tp_path = tput_files.get(key)
        if tp_path is None:
            log(f"  ! {op}/{loc}/{d}: no throughput file for run {key}")
            continue
        t = pd.read_csv(tp_path, usecols=[TPUT_TIME_COL, tcol])
        t["_sec"] = np.floor(pd.to_numeric(t[TPUT_TIME_COL], errors="coerce"))
        t[tcol] = pd.to_numeric(t[tcol], errors="coerce")
        t = t.dropna(subset=["_sec", tcol])
        t["_sec"] = t["_sec"].astype(np.int64)
        t = t.groupby("_sec")[tcol].mean()

        m = run_rows.merge(t, left_on="_sec", right_index=True, how="inner")
        if m.empty:
            log(f"  ! {op}/{loc}/{d}/{key}: no overlapping seconds between PHY and throughput")
            continue
        frames.append(pd.DataFrame({
            "Operator": op, "Run": key, "Retx": m[RETX_COL].to_numpy(),
            "Throughput": m[tcol].to_numpy(),
        }))

    if not frames:
        return None
    df = pd.concat(frames, ignore_index=True)
    if DROP_ZERO_TPUT:
        df = df[df["Throughput"] > 0]
    if MAX_TPUT is not None:
        df = df[df["Throughput"] <= MAX_TPUT]
    log(f"  [✓] {op}/{loc}/{d}/{direction}: {df['Run'].nunique()} runs, {len(df)} seconds")
    return df


# ───────────────────────────── plotting ────────────────────────────
def stats(df):
    """Per operator: (mean, std, n) for each operator in OPERATORS order."""
    out = []
    for op in OPERATORS:
        v = df.loc[df["Operator"] == op, "Throughput"]
        n = len(v)
        out.append((v.mean() if n else 0.0, v.std(ddof=0) if n > 1 else 0.0, n))
    return out


def plot_retx(df, title, ylabel, out_path):
    groups = [("Retransmission = 0", df[df["Retx"] == 0]),
              ("Retransmission > 0", df[df["Retx"] > 0])]
    all_stats = [stats(sub) for _, sub in groups]

    top = max((m + s) for st in all_stats for m, s, n in st if n) if len(df) else 1.0
    top = top if top > 0 else 1.0
    pad = 0.02 * top

    x = np.arange(len(OPERATORS))
    colors = [OP_COLORS[i % len(OP_COLORS)] for i in range(len(OPERATORS))]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5), sharey=True)

    for ax, (name, _), st in zip(axes, groups, all_stats):
        means = [m for m, s, n in st]
        stds = [s for m, s, n in st]
        ax.bar(x, means, yerr=stds, capsize=4, width=0.6, color=colors,
               edgecolor="black", linewidth=0.5, alpha=0.85,
               error_kw=dict(elinewidth=0.75, ecolor="black"))
        for xi, (m, s, n) in zip(x, st):
            if n:
                ax.text(xi, m + s + pad, f"{m:.1f}", ha="center", va="bottom",
                        fontweight="bold", fontsize=9)
            else:
                ax.text(xi, pad, "no data", ha="center", va="bottom", fontsize=8, color="grey")
        ax.set_xticks(x)
        ax.set_xticklabels([f"{op}\n(n={n})" for op, (_, _, n) in zip(OPERATORS, st)])
        for label in ax.get_xticklabels() + ax.get_yticklabels():
            label.set_fontweight("bold")
        ax.set_title(name, fontweight="bold")
        ax.set_xlabel("Operator")
        ax.grid(axis="y", linestyle="--", alpha=0.5)
        ax.set_axisbelow(True)

    axes[0].set_ylabel(ylabel)
    axes[0].set_ylim(0, top * 1.15)
    fig.suptitle(title, fontweight="bold", fontsize=13)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    log(f"  -> {out_path}")


# ───────────────────────────── main ────────────────────────────────
def main():
    for loc in LOCATIONS:
        for direction, tcol in DIRECTIONS.items():
            label = "Downlink" if direction == "downlink" else "Uplink"
            ylabel = f"{label} Throughput (Mbps)"
            log(f"\n===== {loc} / {direction} =====")

            all_days = []
            for d in DATES:
                day = [df for op in OPERATORS
                       if (df := load_day(op, loc, d, direction, tcol)) is not None]
                if not day:
                    continue
                day_df = pd.concat(day, ignore_index=True)
                plot_retx(day_df, f"{loc} - {d} - {label}", ylabel,
                          GRAPHS_DIR / loc / f"{d}_{direction}_retx.png")
                all_days.append(day_df)

            if all_days:
                plot_retx(pd.concat(all_days, ignore_index=True),
                          f"{loc} - All dates - {label}", ylabel,
                          GRAPHS_DIR / loc / f"all_dates_{direction}_retx.png")
            else:
                log("  ! no data for any date")


if __name__ == "__main__":
    main()