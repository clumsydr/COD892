#!/usr/bin/env python3
"""
Plot mean variability vs window size (timescale), one line per operator.

  in : <ROOT>/variability_mean_<direction>.csv          (from capture_variability.py)
  out: <ROOT>/plots/<direction>/<param>.png / .pdf      one figure per parameter
       <ROOT>/plots/<direction>/all_parameters.png / .pdf
            one panel per parameter on a shared x-axis, throughput first, so each
            parameter's curve can be compared directly with throughput's

Scales
  x : window sizes 1,2,5,10,20,50 s grow roughly geometrically, so the x-axis is log by
      default (evenly spaced ticks, labelled with the actual window sizes). On a linear
      axis 1, 2 and 5 s would crowd together on the left. Set X_SCALE = "linear" to change it.
  y : every parameter gets its own axis, labelled with its unit, and its range is fitted
      to the data with a small margin rather than forced to start at 0, so the trend with
      timescale stays visible (MIMO and MCS variabilities are small numbers). To start a
      parameter at 0, add it to Y_FROM_ZERO.

Usage: edit the CONFIG block, then run  python plot_variability.py
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, NullLocator
import numpy as np
import pandas as pd

# ───────────────────────────── CONFIG ──────────────────────────────
ROOT = Path("results/dummyVC/oldData")
DIRECTIONS = ["downlink", "uplink"]
IN_NAME = "variability_mean_{direction}.csv"
PLOT_DIR = Path("graphs/dummyVC/VariabilityPlots/oldData")

# column in the mean CSV -> y-axis label
PARAMS = {
    "Throughput Variability":          "Tput variability (Mbps)",
    # "PHY Throughput Variability":      "PHY tput variability (Mbps)",
    "Resource Block Variability":      "RB variability (RBs)",
    "MIMO Variability":                "MIMO variability (layers)",
    "Retransmission Rate Variability": "Retx rate variability (%)",
    "MCS Variability":                 "MCS variability (index)",
}

X_SCALE = "log"                     # "log" or "linear"
Y_FROM_ZERO = set()                 # e.g. {"MIMO Variability"} to start that y-axis at 0
Y_MARGIN = 0.08                     # fraction of the data range added above and below

# Fixed colour + marker per operator, so an operator looks the same on every plot.
# Colours: validated colour-blind-safe categorical palette; markers add a second cue.
STYLE_ORDER = [("#2a78d6", "^"), ("#eb6834", "D"), ("#1baf7a", "X"),
               ("#4a3aa7", "o"), ("#e87ba4", "s")]
OPERATOR_ORDER = ["Jio", "Airtel", "Vi"]   # these get the first styles, others follow

FORMATS = ["png", "pdf"]
DPI = 300
# ───────────────────────────────────────────────────────────────────

plt.rcParams.update({
    "font.size": 15, "axes.labelsize": 16, "xtick.labelsize": 14, "ytick.labelsize": 14,
    "legend.fontsize": 13, "axes.linewidth": 1.2, "lines.linewidth": 1.8,
    "lines.markersize": 9, "savefig.bbox": "tight", "pdf.fonttype": 42,
})

plt.rcParams["font.family"] = "serif"
plt.rcParams["font.serif"] = ["Times New Roman", "Times", "DejaVu Serif"]
plt.rcParams.update({
    "text.usetex": False,
    "font.family": "serif",
    "font.serif": ["Times"],
})

def log(msg):
    print(msg, flush=True)


def operator_styles(operators):
    known = [o for o in OPERATOR_ORDER if o in operators]
    rest = sorted(o for o in operators if o not in OPERATOR_ORDER)
    return {op: STYLE_ORDER[i % len(STYLE_ORDER)] for i, op in enumerate(known + rest)}


def style_axis(ax, windows, col, values):
    if X_SCALE == "log":
        ax.set_xscale("log")
        ax.set_xlim(min(windows) / 1.3, max(windows) * 1.3)
    else:
        pad = (max(windows) - min(windows)) * 0.04
        ax.set_xlim(min(windows) - pad, max(windows) + pad)
    ax.xaxis.set_major_locator(FixedLocator(windows))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_xticklabels([f"{w:g}" for w in windows])

    lo, hi = np.nanmin(values), np.nanmax(values)
    span = (hi - lo) or (abs(hi) or 1.0)
    bottom = 0 if col in Y_FROM_ZERO else max(0, lo - Y_MARGIN * span)
    ax.set_ylim(bottom, hi + Y_MARGIN * span)

    ax.grid(True, color="#b0b0b0", linewidth=1.0)
    ax.set_axisbelow(True)


def draw(ax, data, col, styles, windows):
    for op, (color, marker) in styles.items():
        d = data[data["Operator"] == op].sort_values("Window Size")
        if d[col].notna().any():
            ax.plot(d["Window Size"], d[col], color=color, marker=marker, label=op,
                    markeredgecolor="white", markeredgewidth=0.8)
    style_axis(ax, windows, col, data[col].to_numpy(dtype=float))


def save(fig, base):
    for ext in FORMATS:
        fig.savefig(base.with_suffix(f".{ext}"), dpi=DPI)
    plt.close(fig)
    log(f"    -> {base}.{{{','.join(FORMATS)}}}")


def plot_direction(direction):
    src = ROOT / IN_NAME.format(direction=direction)
    if not src.exists():
        log(f"[{direction}] {src} not found, skipping")
        return
    data = pd.read_csv(src)
    data.columns = [c.strip() for c in data.columns]
    windows = sorted(int(w) for w in data["Window Size"].unique())
    styles = operator_styles(set(data["Operator"]))
    params = [c for c in PARAMS if c in data.columns and data[c].notna().any()]
    skipped = [c for c in PARAMS if c not in params]
    if skipped:
        log(f"[{direction}] no data for {skipped}, not plotted")

    out_dir =  PLOT_DIR / direction
    out_dir.mkdir(parents=True, exist_ok=True)
    log(f"[{direction}] {len(styles)} operators, window sizes {windows}")

    # one figure per parameter
    for col in params:
        fig, ax = plt.subplots(figsize=(7, 3.8))
        draw(ax, data, col, styles, windows)
        ax.set_xlabel("timescale / window size (in s)")
        ax.set_ylabel(PARAMS[col])
        ax.legend(frameon=True, framealpha=0.9, ncol=len(styles), loc="best")
        save(fig, out_dir / col.lower().replace(" ", "_"))

    # all parameters side by side, shared x-axis, throughput first
    n = len(params)
    ncols = 3 if n > 4 else 2 if n > 1 else 1
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(5.2 * ncols, 3.6 * nrows), squeeze=False)
    for ax, col in zip(axes.flat, params):
        draw(ax, data, col, styles, windows)
        ax.set_ylabel(PARAMS[col])
    for ax in axes.flat[n:]:
        ax.set_visible(False)
    for ax in axes[-1]:
        ax.set_xlabel("window size (in s)")
    for r in range(nrows - 1):          # x label on the lowest visible panel of each column
        for c in range(ncols):
            if not axes[r + 1, c].get_visible():
                axes[r, c].set_xlabel("window size (in s)")
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=len(labels), frameon=False,
               bbox_to_anchor=(0.5, 1.02))
    fig.suptitle(f"{direction.capitalize()}: mean variability vs timescale", y=1.07)
    fig.tight_layout()
    save(fig, out_dir / "all_parameters")


def main():
    if not ROOT.is_dir():
        sys.exit(f"{ROOT} not found")
    for direction in DIRECTIONS:
        plot_direction(direction)


if __name__ == "__main__":
    main()