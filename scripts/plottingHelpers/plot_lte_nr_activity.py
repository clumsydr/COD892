#!/usr/bin/env python3

import csv
import math
from pathlib import Path
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ============================================================
# CONFIGURATION
# ============================================================

DATA_ROOT = Path("/scratch/5GMeasurements/qmdl_output")
OUTPUT_ROOT = Path("/scratch/5GMeasurements/graphs/fallback_graphs")

OPERATORS = ["Airtel", "Vodafone", "Jio"]
BIN_WIDTH_MS = 10

# The selected numeric timestamp columns in these files are epoch seconds.
TIME_COL = None
NUMERIC_TIME_UNIT = "s"

NR_UL_FILE = "readable_b881.csv"
NR_DL_FILE = "readable_b887.csv"
LTE_UL_FILE = "b139_pusch_tx.csv"
LTE_DL_FILE = "b173_pdsch_stats.csv"

OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

# Prefer epoch columns so all four files use the same clock and units.
TIME_CANDIDATES = [
    "timestamp_epoch",
    "epoch_sec",
    "timestamp",
    "Timestamp",
    "time",
    "Time",
    "timestamp_ms",
    "Timestamp_ms",
    "time_ms",
    "Time_ms",
    "timestamp_us",
    "Timestamp_us",
]


# ============================================================
# CSV READING
# ============================================================

def read_timestamps(filepath):
    """Read timestamps from one CSV using Python's built-in csv module."""

    with open(filepath, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        if not reader.fieldnames:
            print(f"[WARNING] Empty CSV: {filepath}", flush=True)
            return []

        columns = reader.fieldnames

        if TIME_COL is not None:
            if TIME_COL not in columns:
                raise ValueError(
                    f"Timestamp column '{TIME_COL}' not found in "
                    f"{filepath}. Columns: {columns}"
                )
            time_col = TIME_COL
        else:
            time_col = next(
                (col for col in TIME_CANDIDATES if col in columns),
                None,
            )

            if time_col is None:
                time_col = next(
                    (
                        col for col in columns
                        if "timestamp" in col.lower()
                        or col.lower() in ("time", "epoch_sec")
                    ),
                    None,
                )

            if time_col is None:
                raise ValueError(
                    f"Cannot identify timestamp column in {filepath}. "
                    f"Available columns: {columns}"
                )

        timestamps = []
        factors = {"s": 1.0, "ms": 1e-3, "us": 1e-6, "ns": 1e-9}

        if NUMERIC_TIME_UNIT not in factors:
            raise ValueError(f"Unsupported timestamp unit: {NUMERIC_TIME_UNIT}")

        for row in reader:
            value = row.get(time_col)
            if value is None or not value.strip():
                continue

            value = value.strip()
            try:
                timestamp = float(value) * factors[NUMERIC_TIME_UNIT]
            except ValueError:
                # Fallback for a human-readable datetime column.
                try:
                    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    timestamp = dt.timestamp()
                except ValueError:
                    continue

            if math.isfinite(timestamp):
                timestamps.append(timestamp)

        print(
            f"  Read {len(timestamps):,} timestamps from {filepath.name} "
            f"(column: {time_col})",
            flush=True,
        )
        return timestamps


# ============================================================
# LOAD ONE CAPTURE
# ============================================================

def load_capture(capture_dir):
    files = {
        "NR UL": capture_dir / NR_UL_FILE,
        "NR DL": capture_dir / NR_DL_FILE,
        "LTE UL": capture_dir / "lte" / LTE_UL_FILE,
        "LTE DL": capture_dir / "lte" / LTE_DL_FILE,
    }

    missing = [str(path) for path in files.values() if not path.is_file()]
    if missing:
        print(f"\n[SKIP] {capture_dir}")
        for path in missing:
            print(f"  Missing: {path}")
        return None

    try:
        print("Reading NR UL...", flush=True)
        nr_ul = read_timestamps(files["NR UL"])
        print("Reading NR DL...", flush=True)
        nr_dl = read_timestamps(files["NR DL"])
        print("Reading LTE UL...", flush=True)
        lte_ul = read_timestamps(files["LTE UL"])
        print("Reading LTE DL...", flush=True)
        lte_dl = read_timestamps(files["LTE DL"])
    except Exception as exc:
        print(f"[ERROR] {capture_dir}: {exc}", flush=True)
        return None

    nr_times = nr_ul + nr_dl
    lte_times = lte_ul + lte_dl

    if not nr_times and not lte_times:
        print(f"[SKIP] No valid timestamps: {capture_dir}")
        return None

    return {
        "nr_times": nr_times,
        "lte_times": lte_times,
        "nr_ul_count": len(nr_ul),
        "nr_dl_count": len(nr_dl),
        "lte_ul_count": len(lte_ul),
        "lte_dl_count": len(lte_dl),
    }


# ============================================================
# PLOT ONE CAPTURE: TWO SEPARATE ACTIVITY PANELS
# ============================================================

def plot_capture(capture_dir, result, output_dir):
    nr_times = result["nr_times"]
    lte_times = result["lte_times"]

    all_times = nr_times + lte_times
    t0 = min(all_times)

    bin_width = BIN_WIDTH_MS / 1000.0
    max_time = max(all_times) - t0
    n_bins = max(1, math.floor(max_time / bin_width) + 1)

    # Guard against invalid timestamps creating an enormous timeline.
    if n_bins > 10_000_000:
        raise ValueError(
            f"Refusing to allocate {n_bins:,} time bins. "
            f"Check timestamp columns/units; max elapsed time is {max_time:.3f}s."
        )

    # Each technology is active if either its UL or DL file has a record
    # in that bin.
    nr_bins = {int((t - t0) / bin_width) for t in nr_times}
    lte_bins = {int((t - t0) / bin_width) for t in lte_times}

    time_bins = [i * bin_width for i in range(n_bins)]
    nr_activity = [int(i in nr_bins) for i in range(n_bins)]
    lte_activity = [int(i in lte_bins) for i in range(n_bins)]

    # Four mutually exclusive states for each time bin:
    # 0 = neither, 1 = NR only, 2 = LTE only, 3 = both.
    states = []
    for i in range(n_bins):
        nr_on = nr_activity[i]
        lte_on = lte_activity[i]
        if nr_on and lte_on:
            states.append(3)
        elif nr_on:
            states.append(1)
        elif lte_on:
            states.append(2)
        else:
            states.append(0)

    state_labels = {
        0: "Neither observed",
        1: "NR only",
        2: "LTE only",
        3: "Both observed",
    }
    state_colors = {
        0: "lightgray",
        1: "red",
        2: "blue",
        3: "purple",
    }

    fig, (ax_nr, ax_lte, ax_state) = plt.subplots(
        nrows=3,
        ncols=1,
        figsize=(16, 8),
        sharex=True,
        gridspec_kw={"height_ratios": [1, 1, 0.8]},
    )

    ax_nr.step(
        time_bins, nr_activity, where="post",
        color="red", linewidth=0.8, label="5G NR",
    )
    ax_nr.set_ylabel("NR activity\n(0/1)")
    ax_nr.set_yticks([0, 1])
    ax_nr.set_ylim(-0.15, 1.15)
    ax_nr.set_title("5G NR PHY activity")
    ax_nr.grid(True, alpha=0.3)
    ax_nr.legend(loc="upper right")

    ax_lte.step(
        time_bins, lte_activity, where="post",
        color="blue", linewidth=0.8, label="LTE",
    )
    ax_lte.set_ylabel("LTE activity\n(0/1)")
    ax_lte.set_yticks([0, 1])
    ax_lte.set_ylim(-0.15, 1.15)
    ax_lte.set_title("LTE PHY activity")
    ax_lte.grid(True, alpha=0.3)
    ax_lte.legend(loc="upper right")

    # Categorical state timeline: color each bin according to the joint state.
    for state_value, color in state_colors.items():
        active = [1 if state == state_value else 0 for state in states]
        ax_state.fill_between(
            time_bins,
            0,
            active,
            step="post",
            color=color,
            linewidth=0,
            label=state_labels[state_value],
        )

    ax_state.set_ylim(0, 1.15)
    ax_state.set_yticks([])
    ax_state.set_ylabel("Joint\nstate")
    ax_state.set_xlabel("Elapsed time (seconds)")
    ax_state.set_title("Joint NR/LTE activity state")
    ax_state.grid(True, axis="x", alpha=0.3)
    ax_state.legend(loc="upper center", ncol=4, fontsize=9)

    fig.suptitle(
        f"{capture_dir.parent.parent.name} | "
        f"{capture_dir.parent.name} | {capture_dir.name}\n"
        f"LTE and 5G NR PHY Activity (bin width: {BIN_WIDTH_MS} ms)",
        y=0.995,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.95])

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "lte_nr_binary_activity.png"
    fig.savefig(output_file, dpi=200, bbox_inches="tight")
    plt.close(fig)

    # Summarize time spent in each joint state.
    state_counts = {state: states.count(state) for state in state_labels}
    duration = n_bins * bin_width

    # Find contiguous LTE-only runs (state 2) and write their start/end times.
    lte_only_intervals = []
    run_start = None
    for i, state in enumerate(states):
        if state == 2 and run_start is None:
            run_start = i
        elif state != 2 and run_start is not None:
            start_s = run_start * bin_width
            end_s = i * bin_width
            lte_only_intervals.append({
                "capture_dir": str(capture_dir),
                "start_seconds": round(start_s, 3),
                "end_seconds": round(end_s, 3),
                "duration_ms": round((end_s - start_s) * 1000, 3),
            })
            run_start = None

    if run_start is not None:
        start_s = run_start * bin_width
        end_s = n_bins * bin_width
        lte_only_intervals.append({
            "capture_dir": str(capture_dir),
            "start_seconds": round(start_s, 3),
            "end_seconds": round(end_s, 3),
            "duration_ms": round((end_s - start_s) * 1000, 3),
        })

    intervals_file = output_dir / "lte_only_intervals.csv"
    with open(intervals_file, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "capture_dir", "start_seconds", "end_seconds", "duration_ms"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(lte_only_intervals)

    print(f"[SAVED] {output_file}", flush=True)
    print(f"[SAVED] {intervals_file}", flush=True)
    print(
        "Joint-state bin counts: "
        + ", ".join(
            f"{state_labels[s]}={state_counts[s]:,}"
            for s in state_labels
        ),
        flush=True,
    )
    print(
        f"LTE-only candidate intervals: {len(lte_only_intervals)}",
        flush=True,
    )

    return {
        "capture_dir": str(capture_dir),
        "duration_seconds": round(duration, 3),
        "bin_width_ms": BIN_WIDTH_MS,
        "nr_ul_records": result["nr_ul_count"],
        "nr_dl_records": result["nr_dl_count"],
        "lte_ul_records": result["lte_ul_count"],
        "lte_dl_records": result["lte_dl_count"],
        "neither_observed_bins": state_counts[0],
        "nr_only_observed_bins": state_counts[1],
        "lte_only_observed_bins": state_counts[2],
        "both_active_bins": state_counts[3],
        "neither_observed_pct": round(100 * state_counts[0] / n_bins, 3),
        "nr_only_observed_pct": round(100 * state_counts[1] / n_bins, 3),
        "lte_only_observed_pct": round(100 * state_counts[2] / n_bins, 3),
        "both_active_pct": round(100 * state_counts[3] / n_bins, 3),
        "lte_only_interval_count": len(lte_only_intervals),
        "plot_file": str(output_file),
        "lte_only_intervals_file": str(intervals_file),
    }


# ============================================================
# WRITE SUMMARY CSV WITHOUT PANDAS
# ============================================================

def write_summary(rows, filepath):
    if not rows:
        print("\nNo successful captures to summarize.")
        return

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"[SAVED] Summary: {filepath}", flush=True)


# ============================================================
# MAIN: PROCESS ONLY ONE CAPTURE FOR THIS TEST
# ============================================================

def main():
    if not DATA_ROOT.is_dir():
        raise FileNotFoundError(f"Data directory not found: {DATA_ROOT}")

    operator_dir = DATA_ROOT / "Vodafone"

    if not operator_dir.is_dir():
        raise FileNotFoundError(
            f"Vodafone directory not found: {operator_dir}"
        )

    required_files = [
        NR_UL_FILE,
        NR_DL_FILE,
        f"lte/{LTE_UL_FILE}",
        f"lte/{LTE_DL_FILE}",
    ]

    captures = sorted(
        p for p in operator_dir.rglob("capture_*")
        if p.is_dir()
    )

    capture_dir = None

    for candidate in captures:
        missing = [
            filename
            for filename in required_files
            if not (candidate / filename).is_file()
        ]

        if not missing:
            capture_dir = candidate
            break

        print(f"[SKIP] {candidate}: missing {', '.join(missing)}")

    if capture_dir is None:
        print("No Vodafone captures contain all four required CSV files.")
        return

    print(f"\nProcessing Vodafone capture:\n{capture_dir}", flush=True)
    result = load_capture(capture_dir)
    if result is None:
        print("Could not process this capture.")
        return

    relative_path = capture_dir.relative_to(DATA_ROOT)
    output_dir = OUTPUT_ROOT / relative_path

    stats = plot_capture(capture_dir, result, output_dir)
    stats["operator"] = "Vodafone"

    write_summary([stats], OUTPUT_ROOT / "activity_summary.csv")
    print("\nOne-capture test completed. Exiting.", flush=True)


if __name__ == "__main__":
    main()
