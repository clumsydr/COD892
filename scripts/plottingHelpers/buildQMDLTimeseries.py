#!/usr/bin/env python3
"""
Per-second, multi-metric time-series builder + plotter.

For every run, combines:
  - Throughput (Download / Upload, Mbps, already ~1 Hz)
        results/Throughput/<operator>/<loc>/20260826/capture_000_*/capture_000_*.csv
        columns: Timestamp, Download (Mbps), Upload (Mbps)

  - Downlink QMDL  (tb_size_bytes, mcs, num_rbs — per-ms snapshots)
        results/dummyVC/QMDL_Data/<operator>/capture_000_*/readable_b887.csv
        columns: timestamp_epoch, timestamp_utc, tb_size_bytes, mcs, num_rbs

  - Uplink QMDL    (delta_new_tx_bytes, delta_retx_bytes, delta_num_prb, avg_mcs_this_interval — per-ms deltas)
        results/dummyVC/QMDL_Data/<operator>/capture_000_*/readable_b881.csv
        columns: timestamp_epoch, timestamp_utc, delta_new_tx_bytes, delta_retx_bytes, delta_num_prb, avg_mcs_this_interval

into one row-per-second CSV for downlink and one for uplink, then draws a
4-subplot figure for each direction with:
  1. Download/Upload Throughput (Mbps)
  2. MCS
  3. Resource Block Count
  4. Sample Count per second (# of QMDL samples)

AGGREGATION RULES:
  - Download / Upload (Mbps)      -> already per-second -> MEAN within the bucket (defensive)
  - tb_size_bytes, mcs, num_rbs   -> per-interval snapshots -> MEAN per second
  - delta_new_tx_bytes,
    delta_retx_bytes,
    delta_num_prb                 -> per-interval deltas   -> SUM per second (true per-second total)
  - avg_mcs_this_interval         -> already an interval average -> MEAN per second
  - Sample_Count                  -> COUNT of raw QMDL samples per second

TIME ALIGNMENT:
  Each of the three input files is treated as its own independently-clocked
  recording of the same ~duration-second test. "Second 0" for a given file
  is defined as THAT file's own first timestamp.

MISSING SECONDS:
  Seconds with NO underlying samples at all are left as NaN in both CSV and
  plot. No forward-fill, no invented values. The plot will show a gap where
  NaN values exist — this is handled automatically by matplotlib.

NORMALIZATION:
  None. Each metric is stored and plotted in its own raw units/scale.

RUN MATCHING:
  A run = a capture_* directory name. Provider + Location are taken from the
  Throughput path; the matching QMDL files are located by re-using that same
  capture directory name under results/dummyVC/QMDL_Data/<operator>/<capture_dir>/.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ------------------------------------------------------------------
# Plotting convention (as specified) — kept identical to existing scripts
# ------------------------------------------------------------------
plt.rcParams["font.family"] = "serif"
plt.rcParams["font.serif"] = ["Times New Roman", "Times", "DejaVu Serif"]
plt.rcParams.update({
    "text.usetex": False,
    "font.family": "serif",
    "font.serif": ["Times"],
    "font.size": 10,
    "figure.figsize": (3.125, 1.56),
    "legend.fontsize": 8,
    "legend.fancybox": True,
    "axes.linewidth": 0.5,
    "axes.prop_cycle": plt.cycler(color=[
        "#348ABD",  # blue
        "#A60628",  # red
        "#7A68A6",  # purple
        "#467821",  # green
        "#CF4457",  # pink
        "#188487",  # turquoise
        "#E24A33"   # orange
    ]),
    "patch.linewidth": 0.5,
    "lines.linewidth": 0.75,
    "grid.linewidth": 0.25,
    "xtick.major.width": 0.25,
    "xtick.minor.width": 0.25,
    "ytick.major.width": 0.25,
    "ytick.minor.width": 0.25,
    "ps.usedistiller": "xpdf",
    "pdf.fonttype": 42,
    "ps.fonttype": 42
})

DATE="20260929"
THROUGHPUT_GLOB = "*/*/" + DATE +  "/capture_*/*.csv"
DEFAULT_DURATION = 300  # seconds
SCRIPT_VERSION = "2024-per-source-t0-v6-sample-count"
RESULT_DIR="results/dummyVC/5G_QMDL_Data/"


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def parse_timestamps(series: pd.Series) -> pd.Series:
    """Return epoch seconds (float) regardless of whether input is numeric
    epoch (s or ms) or a datetime string."""
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().mean() > 0.9:
        vals = numeric.astype(float)
        if vals.median() > 1e12:
            vals = vals / 1000.0
        return vals
    parsed = pd.to_datetime(series, errors="coerce")
    return parsed.astype("int64") / 1e9


def bucket_to_seconds(df: pd.DataFrame, ts_col: str, duration: int,
                       agg_map: dict, label: str = ""):
    """Assign each row to an integer second bucket relative to THIS source's
    own first timestamp, aggregate per agg_map, reindex to a full 0..duration-1
    range, and LEFT AS NaN for entirely-missing seconds (no forward-fill).

    Returns (bucketed_df):
      - bucketed_df: the aggregated table with NaN for missing seconds.
        Both CSV and plot use this directly — no filling, no invented values.
    """
    df = df.copy()
    if len(df) == 0:
        full_idx = pd.RangeIndex(0, duration, name="Second")
        return pd.DataFrame(index=full_idx)
    
    local_t0 = df[ts_col].min()
    observed_span = df[ts_col].max() - local_t0
    df["Second"] = np.floor(df[ts_col].astype(float) - local_t0).astype("Int64")
    df = df[(df["Second"] >= 0) & (df["Second"] < duration)]
    df["Second"] = df["Second"].astype(int)

    grouped = df.groupby("Second").agg(agg_map)
    full_idx = pd.RangeIndex(0, duration, name="Second")
    bucketed = grouped.reindex(full_idx)
    # NO ffill() — missing seconds stay as NaN

    if bucketed.isna().all().all():
        print(f"[!] WARNING: {label or 'a source'} produced zero usable rows "
              f"after bucketing (raw file spans ~{observed_span:.1f}s vs a "
              f"{duration}s window) — check its timestamp units/column.", file=sys.stderr)
    return bucketed


def count_samples_per_second(df: pd.DataFrame, ts_col: str, duration: int) -> pd.Series:
    """Count # of raw samples per second (before aggregation).
    Returns a Series indexed by Second with counts, NaN for missing seconds."""
    df = df.copy()
    if len(df) == 0:
        return pd.Series(np.nan, index=pd.RangeIndex(0, duration, name="Second"))
    
    local_t0 = df[ts_col].min()
    df["Second"] = np.floor(df[ts_col].astype(float) - local_t0).astype("Int64")
    df = df[(df["Second"] >= 0) & (df["Second"] < duration)]
    df["Second"] = df["Second"].astype(int)

    counts = df.groupby("Second").size()
    full_idx = pd.RangeIndex(0, duration, name="Second")
    return counts.reindex(full_idx)  # NaN for missing seconds, counts for present ones


def find_runs(throughput_root: Path):
    """Yield (operator, loc, capture_dir_name, throughput_csv_path) for every run."""
    for csv_path in sorted(throughput_root.glob(THROUGHPUT_GLOB)):
        rel = csv_path.relative_to(throughput_root)
        parts = rel.parts
        if len(parts) < 5:
            continue
        operator, loc, _date, capture_dir = parts[0], parts[1], parts[2], parts[3]
        yield operator, loc, capture_dir, csv_path


def load_throughput(csv_path: Path):
    df = pd.read_csv(csv_path)
    required = {"Timestamp", "Download (Mbps)", "Upload (Mbps)"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Throughput CSV missing columns: {sorted(missing)}")
    df["__ts"] = parse_timestamps(df["Timestamp"])
    df = df.dropna(subset=["__ts"])
    return df


def load_b887(csv_path: Path):
    df = pd.read_csv(csv_path)
    required = {"timestamp_epoch", "tb_size_bytes", "mcs", "num_rbs"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"readable_b887.csv missing columns: {sorted(missing)}")
    df["__ts"] = parse_timestamps(df["timestamp_epoch"])
    df = df.dropna(subset=["__ts"])
    for c in ("tb_size_bytes", "mcs", "num_rbs"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def load_b881(csv_path: Path):
    df = pd.read_csv(csv_path)
    required = {"timestamp_epoch", "delta_new_tx_bytes", "delta_retx_bytes", "delta_num_prb", "avg_mcs_this_interval"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"readable_b881.csv missing columns: {sorted(missing)}")
    df["__ts"] = parse_timestamps(df["timestamp_epoch"])
    df = df.dropna(subset=["__ts"])
    for c in ("delta_new_tx_bytes", "delta_retx_bytes", "delta_num_prb", "avg_mcs_this_interval"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

def load_b173(csv_path: Path):
    df = pd.read_csv(csv_path)
    required = {"timestamp_epoch", "tb_size_bytes", "mcs", "num_rbs_subframe", "rv"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"b173_pdsch_stats.csv missing columns: {sorted(missing)}")
    df["__ts"] = parse_timestamps(df["timestamp_epoch"])
    df = df.dropna(subset=["__ts"])
    for c in ("tb_size_bytes", "mcs", "num_rbs_subframe", "rv"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

def load_b139(csv_path: Path):
    df = pd.read_csv(csv_path)
    required = {"timestamp_epoch", "tb_size_bytes", "num_rb", "rv"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"b139_pusch_tx.csv missing columns: {sorted(missing)}")
    df["__ts"] = parse_timestamps(df["timestamp_epoch"])
    df = df.dropna(subset=["__ts"])
    for c in ("tb_size_bytes", "num_rb", "rv"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

# ------------------------------------------------------------------
# Per-run processing
# ------------------------------------------------------------------
def process_run_5g(operator, date, capture_dir, throughput_csv, qmdl_root: Path, duration: int):
    b887_path = qmdl_root / operator / date / capture_dir / "readable_b887.csv"
    b881_path = qmdl_root / operator / date / capture_dir / "readable_b881.csv"
    if not b887_path.exists() or not b881_path.exists():
        raise FileNotFoundError(
            f"missing QMDL files for {operator}/{capture_dir} "
            f"(b887 exists={b887_path.exists()}, b881 exists={b881_path.exists()})"
        )

    thr = load_throughput(throughput_csv)
    dl_raw = load_b887(b887_path)
    ul_raw = load_b881(b881_path)

    run_label = f"{operator}/{capture_dir}"
    thr_bucketed = bucket_to_seconds(
        thr, "__ts", duration,
        {"Download (Mbps)": "mean", "Upload (Mbps)": "mean"},
        label=f"{run_label} throughput",
    )
    dl_bucketed = bucket_to_seconds(
        dl_raw, "__ts", duration,
        {"tb_size_bytes": "mean", "mcs": "mean", "num_rbs": "mean"},
        label=f"{run_label} readable_b887",
    )
    ul_bucketed = bucket_to_seconds(
        ul_raw, "__ts", duration,
        {"delta_new_tx_bytes": "sum", "delta_retx_bytes": "sum", "delta_num_prb": "sum", "avg_mcs_this_interval": "mean"},
        label=f"{run_label} readable_b881",
    )

    # Count samples per second (raw QMDL samples)
    dl_sample_counts = count_samples_per_second(dl_raw, "__ts", duration)
    ul_sample_counts = count_samples_per_second(ul_raw, "__ts", duration)

    # ---- Downlink table (raw values, NaN preserved) ----
    downlink = pd.concat(
        [thr_bucketed[["Download (Mbps)"]], dl_bucketed], axis=1
    ).rename(columns={
        "Download (Mbps)": "Download_Mbps",
        "tb_size_bytes": "TB_Size_Bytes",
        "mcs": "MCS",
        "num_rbs": "RB_Count",
    })
    downlink["Sample_Count"] = dl_sample_counts.values
    downlink = downlink.reset_index()

    # ---- Uplink table (raw values, NaN preserved) ----
    uplink = pd.concat(
        [ul_bucketed, thr_bucketed[["Upload (Mbps)"]]], axis=1
    ).rename(columns={
        "Upload (Mbps)": "Upload_Mbps",
        "delta_new_tx_bytes": "TB_Bytes_Sum",
        "delta_retx_bytes": "Retransmission_Bytes",
        "delta_num_prb": "RB_Count",
        "avg_mcs_this_interval": "MCS",
    })
    uplink = uplink[["Upload_Mbps", "MCS", "RB_Count", "TB_Bytes_Sum", "Retransmission_Bytes"]]
    uplink["Sample_Count"] = ul_sample_counts.values
    uplink = uplink.reset_index()

    return downlink, uplink

def process_run_4g(operator, loc, capture_dir, throughput_csv, qmdl_root: Path, duration: int):
    b173_path = qmdl_root / operator / capture_dir / "b173_pdsch_stats.csv"
    b139_path = qmdl_root / operator / capture_dir / "b139_pusch_tx.csv"
    if not b139_path.exists() or not b173_path.exists():
        raise FileNotFoundError(
            f"missing QMDL files for {operator}/{capture_dir} "
            f"(b173 exists={b173_path.exists()}, b139 exists={b139_path.exists()})"
        )

    thr = load_throughput(throughput_csv)
    dl_raw = load_b887(b173_path)
    ul_raw = load_b881(b139_path)

    run_label = f"{operator}/{capture_dir}"
    thr_bucketed = bucket_to_seconds(
        thr, "__ts", duration,
        {"Download (Mbps)": "mean", "Upload (Mbps)": "mean"},
        label=f"{run_label} throughput",
    )
    dl_bucketed = bucket_to_seconds(
        dl_raw, "__ts", duration,
        {"tb_size_bytes": "mean", "mcs": "mean", "num_rbs_subframe": "mean", "rv": "mean"},
        label=f"{run_label} b173_pdsch_stats",
    )
    ul_bucketed = bucket_to_seconds(
        ul_raw, "__ts", duration,
        {"tb_size_bytes": "sum", "delta_retx_bytes": "sum", "num_rb": "sum", "rv": "mean"},
        label=f"{run_label} b139_pusch_tx",
    )

    # Count samples per second (raw QMDL samples)
    dl_sample_counts = count_samples_per_second(dl_raw, "__ts", duration)
    ul_sample_counts = count_samples_per_second(ul_raw, "__ts", duration)

    # ---- Downlink table (raw values, NaN preserved) ----
    downlink = pd.concat(
        [thr_bucketed[["Download (Mbps)"]], dl_bucketed], axis=1
    ).rename(columns={
        "Download (Mbps)": "Download_Mbps",
        "tb_size_bytes": "TB_Size_Bytes",
        "mcs": "MCS",
        "num_rbs": "RB_Count",
    })
    downlink["Sample_Count"] = dl_sample_counts.values
    downlink = downlink.reset_index()

    # ---- Uplink table (raw values, NaN preserved) ----
    uplink = pd.concat(
        [ul_bucketed, thr_bucketed[["Upload (Mbps)"]]], axis=1
    ).rename(columns={
        "Upload (Mbps)": "Upload_Mbps",
        "tb_size_bytes": "TB_Bytes_Sum",
        "delta_retx_bytes": "Retransmission_Bytes",
        "avg_mcs_this_interval": "RB_Count",
    })
    uplink = uplink[["Upload_Mbps", "RB_Count", "TB_Bytes_Sum", "Retransmission_Bytes"]]
    uplink["Sample_Count"] = ul_sample_counts.values
    uplink = uplink.reset_index()

    return downlink, uplink


# ------------------------------------------------------------------
# Plotting — 4 stacked subplots, one metric per subplot, raw units
# ------------------------------------------------------------------
def plot_timeseries_subplots(df: pd.DataFrame, cols, labels, ylabels, title: str,
                              out_path: Path):
    """One subplot per metric (4 rows x 1 col, shared x-axis), each in its
    own raw units/scale — no normalization.
    
    NaN values are left as-is, which matplotlib automatically renders as gaps
    in the line (no lines drawn across NaN points).
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n = len(cols)
    print(n)
    fig, axes = plt.subplots(n, 1, figsize=(9.5, 2.2 * n), sharex=True)
    if n == 1:
        axes = [axes]

    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    for i, (col, label, ylabel) in enumerate(zip(cols, labels, ylabels)):
        ax = axes[i]
        ax.plot(df["Second"], df[col], color=colors[i % len(colors)], label=label, linewidth=0.8)
        ax.set_ylabel(ylabel, fontweight="bold", fontsize=8)
        ax.grid(True, linestyle="--", alpha=0.5)
        for lbl in ax.get_xticklabels() + ax.get_yticklabels():
            lbl.set_fontweight("bold")
        ax.text(0.01, 0.90, label, transform=ax.transAxes, fontsize=8,
                 fontweight="bold", va="top", ha="left")

    axes[-1].set_xlabel("Time (s)", fontweight="bold")
    fig.suptitle(title, fontweight="bold", fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(out_path, dpi=300)
    plt.close(fig)


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Build per-second combined-metric CSVs and 4-subplot raw time-series figures")
    parser.add_argument("--throughput-root", default="results/Throughput", type=Path)
    parser.add_argument("--qmdl-root", type=Path)
    parser.add_argument("--csv-out", default="results/dummyVC/allMetrics", type=Path)
    parser.add_argument("--plot-out", default="graphs/dummyVC/timeSeriesPlots", type=Path)
    parser.add_argument("--duration", default=DEFAULT_DURATION, type=int)
    args = parser.parse_args()
    print(f"[i] build_timeseries.py version: {SCRIPT_VERSION}, duration={args.duration}s")
    print(f"[i] throughput_root={args.throughput_root}")

    if not args.throughput_root.exists():
        print(f"[!] Throughput root missing: {args.throughput_root}", file=sys.stderr)
        sys.exit(1)

    n_ok, n_fail = 0, 0
    for operator, loc, capture_dir, throughput_csv in find_runs(args.throughput_root):
        try:
            downlink, uplink = process_run_5g(
                operator, DATE, capture_dir, throughput_csv, Path(RESULT_DIR), args.duration
            )
            # downlink, uplink = process_run_4g(
            #     operator, loc, capture_dir, throughput_csv, args.qmdl_root, args.duration
            # )
        except (FileNotFoundError, ValueError) as e:
            print(f"[!] Skipping {operator}/{loc}/{capture_dir}: {e}", file=sys.stderr)
            n_fail += 1
            continue

        # ---- CSVs: results/dummyVC/allMetrics/<loc>/<operator>/<capture_dir>_{dl,ul}.csv
        csv_dir = args.csv_out / loc / operator
        csv_dir.mkdir(parents=True, exist_ok=True)
        dl_csv_path = csv_dir / f"{capture_dir}_downlink.csv"
        ul_csv_path = csv_dir / f"{capture_dir}_uplink.csv"
        downlink.to_csv(dl_csv_path, index=False)
        uplink.to_csv(ul_csv_path, index=False)

        # ---- Plots: graphs/dummyVC/timeSeriesPlots/<loc>/<operator>/<capture_dir>_{dl,ul}.png
        plot_dir = args.plot_out / loc / operator
        # plot_timeseries_subplots(
        #     downlink,
        #     cols=["Download_Mbps", "MCS", "RB_Count", "Sample_Count"],
        #     labels=["Download", "MCS", "RB Count", "Sample Count"],
        #     ylabels=["Mbps", "MCS index", "RBs", "# Samples/s"],
        #     title=f"Downlink — {operator} / {loc} / {capture_dir}",
        #     out_path=plot_dir / f"{capture_dir}_downlink.png",
        # )
        # plot_timeseries_subplots(
        #     uplink,
        #     cols=["Upload_Mbps", "MCS", "RB_Count", "Retransmission_Bytes", "Sample_Count"],
        #     labels=["Upload", "MCS", "RB Count", "Retx Bytes","Sample Count"],
        #     ylabels=["Mbps", "MCS index", "RBs", "Retx Bytes", "# Samples/s"],
        #     title=f"Uplink — {operator} / {loc} / {capture_dir}",
        #     out_path=plot_dir / f"{capture_dir}_uplink.png",
        # )
        plot_timeseries_subplots(
            downlink,
            cols=["Download_Mbps", "MCS", "RB_Count", "Retransmission_Bytes", "Sample_Count"],
            labels=["Download", "MCS", "RB Count", "Retx Bytes" "Sample Count"],
            ylabels=["Mbps", "MCS index", "RBs", "Retx Bytes", "# Samples/s"],
            title=f"Downlink — {operator} / {loc} / {capture_dir}",
            out_path=plot_dir / f"{capture_dir}_downlink.png",
        )
        plot_timeseries_subplots(
            uplink,
            cols=["Upload_Mbps", "RB_Count", "Retransmission_Bytes", "Sample_Count"],
            labels=["Upload", "RB Count", "Retx Bytes","Sample Count"],
            ylabels=["Mbps", "MCS index", "RBs", "Retx Bytes", "# Samples/s"],
            title=f"Uplink — {operator} / {loc} / {capture_dir}",
            out_path=plot_dir / f"{capture_dir}_uplink.png",
        )

        print(f"[✓] {operator}/{loc}/{capture_dir} -> {dl_csv_path.name}, {ul_csv_path.name}")
        n_ok += 1

    print(f"\nDone. {n_ok} run(s) processed, {n_fail} skipped.")


if __name__ == "__main__":
    main()