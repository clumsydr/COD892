import os
import glob
import re
import pandas as pd
import matplotlib.pyplot as plt

# ==========================================
# CONFIGURATION & RC PARAMS
# ==========================================
OPERATORS = ["Airtel", "Jio", "Vodafone"]
DATE_TAG_M1 = "20260826"
DATE_TAG_M2 = "26Aug2026"
LOCATION = "Amul"

BASE_DIR_M1 = "results/Throughput"
BASE_DIR_M2 = "results/dummyVC"
OUTPUT_GRAPH_DIR = "graphs/dummyVC/CombinedRun/20260826"

# Matplotlib global parameters
plt.rcParams.update({
    "text.usetex": False,
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "font.size": 10,
    "figure.figsize": (8.5, 5),
    "legend.fontsize": 8,
    "legend.fancybox": True,
    "axes.linewidth": 0.5,
    "patch.linewidth": 0.5,
    "lines.linewidth": 1.2,
    "grid.linewidth": 0.25,
    "xtick.major.width": 0.25,
    "xtick.minor.width": 0.25,
    "ytick.major.width": 0.25,
    "ytick.minor.width": 0.25,
    "pdf.fonttype": 42,
    "ps.fonttype": 42
})

# Color scheme for Methods
METHOD_COLORS = {
    "Method 1": "#348ABD",  # Blue
    "Method 2": "#A60628"   # Red
}

# Line styles for Operators
OPERATOR_LINESTYLES = {
    "Airtel": "-",       # Solid
    "Jio": "--",         # Dashed
    "Vodafone": ":"      # Dotted
}


def extract_run_key(folder_name: str):
    """Extracts key matching '20260826_10X' from folder strings."""
    match = re.search(r"(20260826_10\d)", folder_name)
    return match.group(1) if match else None


def find_capture_dir_by_key(parent_dir: str, run_key: str):
    """Finds a subfolder inside parent_dir matching the extracted run_key."""
    if not os.path.exists(parent_dir):
        return None
    for entry in os.listdir(parent_dir):
        if os.path.isdir(os.path.join(parent_dir, entry)) and run_key in entry:
            return os.path.join(parent_dir, entry)
    return None


def plot_combined_runs():
    os.makedirs(OUTPUT_GRAPH_DIR, exist_ok=True)

    # 1. Discover all unique run keys across all operators in Method 1
    discovered_keys = set()
    for op in OPERATORS:
        m1_op_dir = os.path.join(BASE_DIR_M1, op, LOCATION, DATE_TAG_M1)
        if os.path.exists(m1_op_dir):
            for folder in os.listdir(m1_op_dir):
                key = extract_run_key(folder)
                if key:
                    discovered_keys.add(key)

    sorted_run_keys = sorted(discovered_keys)
    if not sorted_run_keys:
        print("[!] No matching folders found with pattern '20260826_10x'.")
        return

    # 2. Generate 1 graph per unique run key
    for run_key in sorted_run_keys:
        fig, ax = plt.subplots(figsize=(8.5, 3.5))
        lines_count = 0

        for op in OPERATORS:
            linestyle = OPERATOR_LINESTYLES.get(op, "-")
            
            m1_parent = os.path.join(BASE_DIR_M1, op, LOCATION, DATE_TAG_M1)
            m2_parent = os.path.join(BASE_DIR_M2, op, DATE_TAG_M2)

            m1_cap_dir = find_capture_dir_by_key(m1_parent, run_key)
            m2_cap_dir = find_capture_dir_by_key(m2_parent, run_key)

            # --- Method 1 Extraction (1..300 seconds) ---
            if m1_cap_dir:
                m1_files = glob.glob(os.path.join(m1_cap_dir, "*.csv"))
                if m1_files:
                    try:
                        df_m1 = pd.read_csv(m1_files[0])
                        ul_col = [c for c in df_m1.columns if "upload" in c.lower() or "ul" in c.lower()]
                        time_col = [c for c in df_m1.columns if "time" in c.lower() or "sec" in c.lower()]

                        if ul_col:
                            # Use explicit time column if present, else default to 1-indexed range (1..N)
                            if time_col:
                                x_m1 = df_m1[time_col[0]].values
                            else:
                                x_m1 = range(1, len(df_m1) + 1)

                            ax.plot(
                                x_m1,
                                df_m1[ul_col[0]].values,
                                label=f"Method 1 - {op}",
                                color=METHOD_COLORS["Method 1"],
                                linestyle=linestyle,
                                alpha=0.85
                            )
                            lines_count += 1
                    except Exception as e:
                        print(f"[!] Error loading Method 1 ({op}, {run_key}): {e}")

            # --- Method 2 Extraction (Epoch -> Relative Seconds) ---
            if m2_cap_dir:
                m2_file_path = os.path.join(m2_cap_dir, "readable_b881.csv")
                if os.path.exists(m2_file_path):
                    try:
                        df_m2 = pd.read_csv(m2_file_path)
                        ts_col = [c for c in df_m2.columns if "timestamp" in c.lower() or "time" in c.lower()]

                        if "throughput_mbps_interval" in df_m2.columns:
                            # Convert epoch float to relative elapsed seconds starting at 0
                            if ts_col:
                                raw_ts = pd.to_numeric(df_m2[ts_col[0]], errors="coerce")
                                x_m2 = raw_ts - raw_ts.iloc[0]
                            else:
                                x_m2 = range(0, len(df_m2))

                            ax.plot(
                                x_m2,
                                df_m2["throughput_mbps_interval"].values,
                                label=f"Method 2 - {op}",
                                color=METHOD_COLORS["Method 2"],
                                linestyle=linestyle,
                                alpha=0.85
                            )
                            lines_count += 1
                    except Exception as e:
                        print(f"[!] Error loading Method 2 ({op}, {run_key}): {e}")

        if lines_count == 0:
            plt.close(fig)
            continue

        # Axis Titles & Formatting
        ax.set_title(f"Uplink Throughput Comparison ({run_key})", fontsize=11, fontweight="bold")
        ax.set_xlabel("Time (seconds)", fontsize=10, fontweight="bold")
        ax.set_ylabel("Throughput (Mbps)", fontsize=10, fontweight="bold")

        # Tick Formatting
        ax.tick_params(axis="both", which="major", labelsize=10)
        for label in ax.get_xticklabels() + ax.get_yticklabels():
            label.set_fontweight("bold")
            label.set_color("#111111")

        # Grid & Legend
        ax.grid(True, linestyle="--", alpha=0.5)
        ax.legend(loc="upper right", frameon=True, fancybox=True, ncol=2)

        plt.tight_layout()

        # Save Plot
        out_filename = os.path.join(OUTPUT_GRAPH_DIR, f"UL_Throughput_Comparison_{run_key}.png")
        plt.savefig(out_filename, dpi=300)
        plt.close(fig)

        print(f"[✓] Saved run plot ({lines_count} lines): {out_filename}")


if __name__ == "__main__":
    plot_combined_runs()