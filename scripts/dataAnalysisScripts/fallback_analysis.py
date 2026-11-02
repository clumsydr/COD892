#!/usr/bin/env python3
"""
Stacked-bar plots of how often each operator gave us 4G, 5G, or both.

Inputs
  results/qmdl_metrics/<op>/<loc>/<date>_downlink.csv
      date,run,timestamp,radio_connection,Resource blocks,MIMO Layers,MCS,...
  results/qmdl_metrics/<op>/<loc>/<date>_collisions.csv     (only if collisions)
      date,run,direction,timestamp,rb_4g,rb_5g,picked,rb

Definitions (per record = per timestamp)
  Both     : the timestamp appears in the collisions file (4G AND 5G logged)
  4G only  : not a collision, radio_connection = 4G
  5G only  : not a collision, radio_connection = 5G
  Picked   : for collisions only, which RAT had the higher RB (4G / 5G / tie)

Outputs (horizontal stacked bars, 0-100 %)
  OUTDIR/<loc>/<date>/<op>/<run>_<direction>.png
        one figure per run of one operator
        (a) % 4G only / Both / 5G only
        (b) % picked 4G / 5G / tie   (only if the run has any collisions)
  OUTDIR/<loc>/<date>/<date>_<direction>_consolidated.png
        same two panels, one bar per operator, all runs of that day pooled
  OUTDIR/<loc>/<date>/<date>_<direction>_fallback_summary.csv
        the numbers behind every bar

Usage: edit SETTINGS, then run
  python plot_fallback_bars.py
"""
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ============================ SETTINGS =====================================
OPERATORS = None              # e.g. ["jio", "airtel", "vi"]; None = all found
LOCATIONS = "indoor_AzadApt"              # e.g. ["loc1"];                None = all found
DATES     = ["20261013", "20261015"]              # e.g. ["20260929"];            None = all found
DIRECTIONS = ["downlink", "uplink"]     # add "uplink" if <date>_uplink.csv files exist

IN_DIR = Path("results/qmdl_metrics/speedtest")
OUTDIR = Path("graphs/speedtest/fallback_graphs")

RAT_COL = "radio_connection"
LABEL_MIN_PCT = 4             # don't write % labels on segments thinner than this
# ===========================================================================

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "font.size": 10, "legend.fontsize": 8, "legend.fancybox": True,
    "axes.linewidth": 0.5, "grid.linewidth": 0.25, "patch.linewidth": 0.5,
    "xtick.major.width": 0.25, "ytick.major.width": 0.25,
    "pdf.fonttype": 42, "ps.fonttype": 42,
})
CONN_CATS  = ["4G only", "Both", "5G only"]
CONN_COLOR = {"4G only": "#348ABD", "Both": "#7A68A6", "5G only": "#A60628"}
PICK_CATS  = ["4G", "tie", "5G"]
PICK_COLOR = {"4G": "#348ABD", "tie": "#999999", "5G": "#A60628"}


# ---------------------------------------------------------------- loading
def norm_rat(v):
    """Map the many spellings of a RAT to 4G / 5G / tie (else None)."""
    s = str(v).strip().lower()
    if s in ("tie", "both"):
        return "tie"
    if s in ("4g", "lte", "4") or "lte" in s or s.startswith("4g"):
        return "4G"
    if s in ("5g", "nr", "5") or s.startswith("5g") or "nr" == s[:2]:
        return "5G"
    return None


def norm_ts(s):
    """Timestamps as a common key: datetime if parseable, else the raw string."""
    num = pd.to_numeric(s, errors="coerce")
    if num.notna().mean() > 0.9:
        return num.round(6).astype(str)
    dt = pd.to_datetime(s, errors="coerce")
    return dt.astype(str).where(dt.notna(), s.astype(str))


def load_all(direction):
    """One table of records with columns op, loc, date, run, conn, picked."""
    frames, warnings = [], []
    for f in sorted(IN_DIR.glob(f"*/*/*_{direction}.csv")):
        op, loc = f.parent.parent.name, f.parent.name
        date = f.name[: -len(f"_{direction}.csv")]
        if OPERATORS and op not in OPERATORS: continue
        if LOCATIONS and loc not in LOCATIONS: continue
        if DATES and date not in DATES: continue

        d = pd.read_csv(f, usecols=["run", "timestamp", RAT_COL], dtype={"run": str})
        d["rat"] = d[RAT_COL].map(norm_rat)
        unk = d["rat"].isna().sum()
        if unk:
            warnings.append(f"{f}: {unk} rows with unrecognised {RAT_COL} "
                            f"(e.g. {d.loc[d.rat.isna(), RAT_COL].iloc[0]!r}) ignored")
            d = d.dropna(subset=["rat"])
        d["key"] = norm_ts(d["timestamp"])
        d["picked"] = np.nan

        cf = f.parent / f"{date}_collisions.csv"
        if cf.exists():
            c = pd.read_csv(cf, usecols=["run", "direction", "timestamp", "picked"],
                            dtype={"run": str})
            c = c[c["direction"].astype(str).str.lower() == direction]
            if len(c):
                c["key"] = norm_ts(c["timestamp"])
                c["picked"] = c["picked"].map(norm_rat)
                c = c.drop_duplicates(["run", "key"])
                d = d.drop(columns="picked").merge(c[["run", "key", "picked"]],
                                                   on=["run", "key"], how="left")
                matched = d["picked"].notna().sum()
                if matched != len(c):
                    warnings.append(f"{cf}: {len(c)} {direction} collisions but only "
                                    f"{matched} matched a row in {f.name} by timestamp")

        d["conn"] = np.where(d["picked"].notna() | (d["rat"] == "tie"), "Both",
                     np.where(d["rat"] == "4G", "4G only", "5G only"))
        # a 'tie' row with no collision entry still means both RATs were present
        d["picked"] = d["picked"].fillna(d["rat"].where(d["rat"] == "tie"))
        d["op"], d["loc"], d["date"] = op, loc, date
        frames.append(d[["op", "loc", "date", "run", "conn", "picked"]])
    for w in warnings:
        print("[!]", w, file=sys.stderr)
    return pd.concat(frames, ignore_index=True) if frames else None


# ---------------------------------------------------------------- summary
def summarise(df):
    """Per operator: record counts and % for each connection / picked category."""
    rows = []
    for op, g in df.groupby("op"):
        n = len(g)
        conn = g["conn"].value_counts()
        pk = g["picked"].dropna().value_counts()
        nc = int(pk.sum())
        r = {"operator": op, "records": n, "collisions": nc}
        for c in CONN_CATS:
            r[f"{c} %"] = 100 * conn.get(c, 0) / n if n else np.nan
        for c in PICK_CATS:
            r[f"picked {c} %"] = 100 * pk.get(c, 0) / nc if nc else np.nan
        rows.append(r)
    return pd.DataFrame(rows).set_index("operator")


# ---------------------------------------------------------------- plotting
def stacked(ax, s, cats, colors, prefix, count_col, title):
    """Horizontal stacked bars: one row per operator, segments add up to 100 %."""
    ops = list(s.index)
    y = np.arange(len(ops))[::-1]          # first operator on top
    left = np.zeros(len(ops))
    for c in cats:
        v = s[f"{prefix}{c} %"].fillna(0).to_numpy()
        ax.barh(y, v, left=left, height=0.6, color=colors[c], label=c,
                edgecolor="white", linewidth=0.5)
        for yi, (l, w) in zip(y, zip(left, v)):
            if w >= LABEL_MIN_PCT:
                ax.text(l + w / 2, yi, f"{w:.0f}%", ha="center", va="center",
                        fontsize=7, color="white", fontweight="bold")
        left += v
    for yi, op in zip(y, ops):
        n = s.loc[op, count_col]
        ax.text(101.5, yi, f"n={int(n):,}" if n else "none", ha="left",
                va="center", fontsize=7, color="black" if n else "gray")
    ax.set_yticks(y, ops)
    ax.set_ylim(-0.6, len(ops) - 0.4)
    ax.set_xlim(0, 115)
    ax.set_xticks(range(0, 101, 20))
    ax.set_xlabel("% of records" if count_col == "records" else "% of collisions",
                  fontweight="bold", fontsize=8)
    ax.set_title(title, fontsize=9, fontweight="bold", loc="left")
    ax.grid(axis="x", linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", bbox_to_anchor=(1.0, 1.0), frameon=False)


def plot(s, title, out_path):
    has_coll = s["collisions"].sum() > 0
    nrows = 2 if has_coll else 1
    h = 0.9 + 0.45 * len(s)                 # panel height grows with #operators
    fig, axes = plt.subplots(nrows, 1, figsize=(6.5, h * nrows + 0.5), squeeze=False)
    stacked(axes[0, 0], s, CONN_CATS, CONN_COLOR, "", "records",
            "(a) Radio connection")
    if has_coll:
        stacked(axes[1, 0], s, PICK_CATS, PICK_COLOR, "picked ", "collisions",
                "(b) Selected RAT when both present")
    fig.suptitle(title, fontsize=10, fontweight="bold")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------- main
def main():
    n_figs = 0
    for direction in DIRECTIONS:
        df = load_all(direction)
        if df is None:
            print(f"[!] no *_{direction}.csv files matched under {IN_DIR}", file=sys.stderr)
            continue
        for (loc, date), day in df.groupby(["loc", "date"]):
            out_dir = OUTDIR / loc / date
            tables = []
            # ---- per run, saved in that operator's folder
            for (op, run), g in day.groupby(["op", "run"]):
                s = summarise(g)
                plot(s, f"{direction.capitalize()} — {loc} / {date} / {op} / {run}",
                     out_dir / op / f"{run}_{direction}.png")
                tables.append(s.reset_index().assign(run=run))
                n_figs += 1
            # ---- consolidated day: all runs pooled per operator
            s = summarise(day)
            plot(s, f"{direction.capitalize()} — {loc} / {date} (all runs)",
                 out_dir / f"{date}_{direction}_consolidated.png")
            tables.append(s.reset_index().assign(run="ALL"))
            n_figs += 1

            t = pd.concat(tables, ignore_index=True)
            cols = ["run", "operator", "records", "collisions"] + \
                   [f"{c} %" for c in CONN_CATS] + [f"picked {c} %" for c in PICK_CATS]
            t = t[cols].round(2)
            t.to_csv(out_dir / f"{date}_{direction}_fallback_summary.csv", index=False)
            print(f"\n== {direction} | {loc} | {date}")
            print(t.to_string(index=False))
    print(f"\n{n_figs} figure(s) written under {OUTDIR}/")


if __name__ == "__main__":
    main()