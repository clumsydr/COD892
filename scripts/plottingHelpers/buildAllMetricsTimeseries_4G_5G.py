#!/usr/bin/env python3
"""
Per-run time-series plots for 4G vs 5G based on unified QMDL metrics and throughput.
X-axis is normalized to 0-300 seconds.

Inputs:
  - Throughput: results/Throughput/<op>/<loc>/<date>/capture_*/throughput_1s_capture_*.csv
  - QMDL Metrics: results/qmdl_metrics/<op>/<loc>/<date>_downlink.csv / _uplink.csv

Output:
  - Graphs: graphs/dummyVC/timeSeries_4Gvs5G/<op>/<loc>/<date>/<run>_<dir>.png
"""
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ============================ SETTINGS =====================================
OPERATORS = ["Jio", "Vodafone"]                  # e.g. ["Airtel"]; None = all found
LOCATIONS = "indoor_Bharti501"          # e.g. ["indoor_Bharti501"]; None = all found
DATES     = "20261006"                  # e.g. ["20261006"]; None = all found

ROOT_THROUGHPUT = Path("results/Throughput")
ROOT_QMDL       = Path("results/qmdl_metrics")
PLOT_OUT        = Path("graphs/dummyVC/timeSeries_4Gvs5G")

DIRECTIONS = ["downlink", "uplink"]

PANELS = [  # (metric key, y-label, display name)
    ("throughput",    "Mbps",               "Throughput"),
    ("MCS",           "MCS index",          "MCS"),
    ("Resource blocks","RBs",               "Resource Blocks"),
    ("MIMO Layers",   "Layers",             "MIMO Layers"),
    ("TB Size",       "Bytes",              "TB Size"),
    ("Retransmission","Value / RV",         "Retransmission"),
]
COLOR = {"4G": "#348ABD", "5G": "#A60628", "Dummy VC": "#467821"}
# ===========================================================================

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "font.size": 10, "legend.fontsize": 8, "legend.fancybox": True,
    "axes.linewidth": 0.5, "lines.linewidth": 0.75, "grid.linewidth": 0.25,
    "xtick.major.width": 0.25, "ytick.major.width": 0.25,
    "pdf.fonttype": 42, "ps.fonttype": 42,
})


def load_throughput(path, direction):
    if not path.exists():
        return None
    df = pd.read_csv(path)
    # Automatically find timestamp or second column, normalize to 0-300 index
    ts_col = next((c for c in df.columns if "time" in c.lower() or "sec" in c.lower() or "index" in c.lower()), df.columns[0])
    df = df.set_index(ts_col).sort_index()
    
    # Identify download/upload throughput column
    col = next((c for c in df.columns if direction.lower() in c.lower() and ("mbps" in c.lower() or "speed" in c.lower() or "throughput" in c.lower())), None)
    if not col and len(df.columns) > 0:
        col = df.columns[0] # Fallback to first metric column if name doesn't match precisely
    
    if col:
        s = pd.to_numeric(df[col], errors="coerce")
        # Reset or reindex to fit 0-300 constraints if timestamps are absolute
        if len(s) > 0:
            s.index = range(len(s))
        return s
    return None


def load_qmdl_run(path, run_name, direction, metric):
    """Extracts per-second series for 4G or 5G from the unified operator-date QMDL file."""
    if not path.exists():
        return None, None
    df = pd.read_csv(path)
    
    # Filter by specific run and direction if columns exist
    if "run" in df.columns:
        df = df[df["run"] == run_name]
    if df.empty or "radio_connection" not in df.columns or metric not in df.columns:
        return None, None
    
    # Clean and map to sequential 0-300 index window per run
    df = df.reset_index(drop=True)
    df.index.name = "second_index"
    
    # Split by radio connection type
    df_4g = df[df["radio_connection"].astype(str).str.upper() == "4G"]
    df_5g = df[df["radio_connection"].astype(str).str.upper() == "5G"]
    
    s4 = pd.to_numeric(df_4g[metric], errors="coerce") if not df_4g.empty else None
    s5 = pd.to_numeric(df_5g[metric], errors="coerce") if not df_5g.empty else None
    
    # Reindex series back to match timeline frames if needed, or map via sequential index
    if not df_4g.empty:
        s4.index = df_4g.index
    if not df_5g.empty:
        s5.index = df_5g.index
        
    return s4, s5

# def load_qmdl_run(path, run_name, direction, metric):
#     """Extracts per-second series for 4G or 5G, mapping to a 0-300 timeline with NaN gaps."""
#     if not path.exists():
#         return None, None
#     df = pd.read_csv(path)
    
#     if "run" in df.columns:
#         df = df[df["run"] == run_name]
#     if df.empty or "radio_connection" not in df.columns or metric not in df.columns:
#         return None, None
    
#     if "timestamp" in df.columns:
#         df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
#         df = df.sort_values("timestamp")
    
#     df = df.reset_index(drop=True)
#     df["second_index"] = range(len(df))
    
#     max_sec = min(300, len(df) - 1)
#     full_timeline = range(0, max_sec + 1)
    
#     df_4g = df[df["radio_connection"].astype(str).str.upper() == "4G"]
#     df_5g = df[df["radio_connection"].astype(str).str.upper() == "5G"]
    
#     s4, s5 = None, None
    
#     if not df_4g.empty:
#         s4 = pd.Series(
#             pd.to_numeric(df_4g[metric], errors="coerce").values,
#             index=df_4g["second_index"]
#         ).reindex(full_timeline)  # Missing seconds are filled with NaN, creating visual gaps
        
#     if not df_5g.empty:
#         s5 = pd.Series(
#             pd.to_numeric(df_5g[metric], errors="coerce").values,
#             index=df_5g["second_index"]
#         ).reindex(full_timeline)  # Missing seconds are filled with NaN, creating visual gaps
        
#     return s4, s5

def find_runs():
    """Yield (op, loc, date, run, direction, throughput_path, qmdl_path)."""
    seen = set()
    # Find throughput files
    for p in sorted(ROOT_THROUGHPUT.glob("*/*/*/capture_*/throughput_1s_capture_*.csv")):
        op, loc, date = p.relative_to(ROOT_THROUGHPUT).parts[:3]
        run = p.parent.name # capture folder name
        
        if OPERATORS and op not in OPERATORS: continue
        if LOCATIONS and loc not in LOCATIONS: continue
        if DATES and date not in DATES: continue
        
        for d in DIRECTIONS:
            key = (op, loc, date, run, d)
            if key in seen: continue
            seen.add(key)
            
            qmdl_path = ROOT_QMDL / op / loc / f"{date}_{d}.csv"
            yield op, loc, date, run, d, p, qmdl_path


def plot_run(tp_series, qmdl_path, run, direction, title, out_path):
    fig, axes = plt.subplots(len(PANELS), 1, figsize=(9.5, 1.9 * len(PANELS)), sharex=True)
    missing = []
    
    for ax, (key, ylabel, title_name) in zip(axes, PANELS):
        if key == "throughput":
            if tp_series is not None and not tp_series.empty:
                ax.plot(tp_series.index, tp_series.values, marker=".", ms=1.5, color=COLOR["Dummy VC"], label="Dummy VC")
            else:
                ax.text(0.5, 0.5, "not in file", transform=ax.transAxes, ha="center", va="center", fontsize=8, color="gray")
                missing.append(key)
        else:
            s4, s5 = load_qmdl_run(qmdl_path, run, direction, key)
            if s4 is not None and not s4.empty:
                ax.plot(s4.index, s4.values, marker=".", ms=1.5, color=COLOR["4G"], label="4G")
            if s5 is not None and not s5.empty:
                ax.plot(s5.index, s5.values, marker=".", ms=1.5, color=COLOR["5G"], label="5G")
                
            if (s4 is None or s4.empty) and (s5 is None or s5.empty):
                ax.text(0.5, 0.5, "not in file", transform=ax.transAxes, ha="center", va="center", fontsize=8, color="gray")
                missing.append(key)
                
        if ax.get_lines():
            ax.legend(loc="upper right", ncol=3, frameon=True)
            
        ax.set_ylabel(ylabel, fontweight="bold", fontsize=8)
        ax.grid(True, linestyle="--", alpha=0.5)
        ax.set_xlim(0, 300) # Enforce 0-300 X-axis scale
        ax.text(0.01, 0.92, title_name, transform=ax.transAxes, fontsize=8, fontweight="bold", va="top")
        
    axes[-1].set_xlabel("Time (0-300 s)", fontweight="bold")
    fig.suptitle(title, fontweight="bold", fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    return missing


def main():
    n = 0
    for op, loc, date, run, d, tp_path, qmdl_path in find_runs():
        tp_series = load_throughput(tp_path, d)
        title = f"{d.capitalize()} — {op} / {loc} / {date} / {run}"
        out = PLOT_OUT / op / loc / date / f"{run}_{d}.png"
        
        missing = plot_run(tp_series, qmdl_path, run, d, title, out)
        n += 1
        
        note = f"  (not in file: {', '.join(missing)})" if missing else ""
        print(f"[✓] {op}/{loc}/{date}/{run} {d}{note}")

    if n == 0:
        sys.exit("No matching runs or files found. Check ROOT_THROUGHPUT / ROOT_QMDL paths and filters.")
    print(f"\nSuccessfully generated {n} figure(s) -> {PLOT_OUT}/")


if __name__ == "__main__":
    main()

