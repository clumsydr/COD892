#!/usr/bin/env python3

"""
Create separate box plots for Download and Upload throughput by operator.

Reads speedtest CSVs for each operator and creates two separate figures:
  - Download Speed (Mbit/s) across operators
  - Upload Speed (Mbit/s) across operators

Here, we're taking the entire distribution of speeds for each operator and plotting them as box plots. 

Each figure shows box plots with median, quartiles, min-max range, and means.
"""

from pathlib import Path
import os, glob, matplotlib
import pandas as pd
import matplotlib.pyplot as plt
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

# Configuration
OPERATORS = ["Airtel", "Jio", "Vodafone"]
RESULT_DIR = "results/Throughput"
GRAPHS_DIR = "graphs/dummyVC/BoxPlots"
LOCATION = "Amul"
DATE_5G = "20260826"
DATE_4G = "20260917_only4G"

# Setting Graph Specifications
plt.rcParams["font.family"] = "serif"
plt.rcParams["font.serif"] = ["Times New Roman", "Times", "DejaVu Serif"]
plt.rcParams.update({
    "text.usetex": False,
    "font.family": "serif",
    "font.serif": ["Times"],
    "font.size": 10,
    "figure.figsize": (3.125, 1.56),  # Squashed height
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
    "lines.linewidth": 1.0,
    "grid.linewidth": 0.25,
    "xtick.major.width": 0.25,
    "xtick.minor.width": 0.25,
    "ytick.major.width": 0.25,
    "ytick.minor.width": 0.25,
    "ps.usedistiller": "xpdf",
    "pdf.fonttype": 42,
    "ps.fonttype": 42
})

# 1. Read and combine data from all operators

def readcsv(DATE):
    combined_data = []
    for op in OPERATORS:
        csv_dir = os.path.join(RESULT_DIR, op, LOCATION, DATE)
        csv_pattern = os.path.join(csv_dir, "capture_*", "capture_*.csv")
        csv_files = sorted(glob.glob(csv_pattern))
        
        if csv_files:
            for csv_path in csv_files:
                try:
                    df = pd.read_csv(csv_path)
                    df["Operator"] = op
                    if "4G" in DATE:
                        df["Network Type"] = "4G"
                    else:
                        df["Network Type"] = "5G"
                    combined_data.append(df)
                    # print(f"[✓] Loaded {csv_path}: {len(df)} records")
                except Exception as e:
                    print(f"[!] Error loading {csv_path}: {e}")
        else:
            print(f"[!] No files found matching: {csv_pattern}")
    if combined_data:
        return pd.concat(combined_data, ignore_index=True)
    else:
        print("[!] No data loaded across any operators.")
        return pd.DataFrame()

def make_combined_boxplot(summary: pd.DataFrame, title: str, out_path: Path, direction: str):
    providers = sorted(summary["Operator"].unique())
    data_5g = [summary.loc[(summary["Operator"] == p) & (summary["Type"] == direction) & (summary["Network Type"] == "5G"), "Speed (Mbit/s)"].dropna().values for p in providers]
    data_4g = [summary.loc[(summary["Operator"] == p) & (summary["Type"] == direction) & (summary["Network Type"] == "4G"), "Speed (Mbit/s)"].dropna().values for p in providers]
    
    n = len(providers)
    centers = list(range(1, n + 1))
    pos_dl = [c - 0.2 for c in centers]
    pos_ul = [c + 0.2 for c in centers]
    width = 0.32

    dl_color = "#4C72B0"
    ul_color = "#DD8452"

    fig, ax = plt.subplots(figsize=(max(7, n * 2.2), 5.5))

    ax.boxplot(
        data_5g,
        positions=pos_dl,
        widths=width,
        patch_artist=True,
        showmeans=True,
        showfliers=False,
        boxprops=dict(facecolor=dl_color, alpha=0.8),
        medianprops=dict(color="black"),
        meanprops=dict(marker="^", markerfacecolor="green", markeredgecolor="green"),
    )
    ax.boxplot(
        data_4g,
        positions=pos_ul,
        widths=width,
        patch_artist=True,
        showmeans=True,
        showfliers=False,
        boxprops=dict(facecolor=ul_color, alpha=0.8),
        medianprops=dict(color="black"),
        meanprops=dict(marker="^", markerfacecolor="green", markeredgecolor="green"),
    )

    ax.set_xticks(centers)
    ax.set_xticklabels(providers)
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontweight("bold")
    ax.set_xlim(0.5, n + 0.5)
    # ax.set_ylim(bottom=0)
    ax.set_title(title, fontweight="bold")
    ax.set_xlabel("Operator")
    ax.set_ylabel("Throughput (Mbps)")
    ax.grid(axis="y", linestyle="--", alpha=0.5)

    legend_handles = [
        Patch(facecolor=dl_color, alpha=0.8, label="5G"),
        Patch(facecolor=ul_color, alpha=0.8, label="4G"),
    ]
    ax.legend(handles=legend_handles, loc="upper right", title="Network Type")

    # fig.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)

if __name__ == "__main__":

    data_4g = readcsv(DATE_5G)
    data_5g = readcsv(DATE_4G)
    full_df = pd.concat([data_4g, data_5g], ignore_index=True)
    print(f"\n[i] Total records: {len(full_df)}")

    # Prepare data for both download and upload
    df_download = full_df[["Operator", "Download (Mbps)", "Network Type"]].copy()
    df_download.columns = ["Operator", "Speed (Mbit/s)", "Network Type"]
    df_download["Type"] = "Download"
    df_download = df_download[df_download["Speed (Mbit/s)"] > 0]
    
    df_upload = full_df[["Operator", "Upload (Mbps)", "Network Type"]].copy()
    df_upload.columns = ["Operator", "Speed (Mbit/s)", "Network Type"]
    df_upload["Type"] = "Upload"
    df_upload = df_upload[df_upload["Speed (Mbit/s)"] > 0]
    
    # Combine both datasets
    df_combined = pd.concat([df_download, df_upload], ignore_index=True)
    print(df_combined.head(5))
    
    # Create figure with 2 subplots side by side
    down_plot_path = f"{GRAPHS_DIR}/Comparative/{LOCATION}_{DATE_5G}vs{DATE_4G}_download_throughput.png"
    up_plot_path = f"{GRAPHS_DIR}/Comparative/{LOCATION}_{DATE_5G}vs{DATE_4G}_upload_throughput.png"
    title = f"Throughput by Provider (4G vs 5G) - ({LOCATION})"
    make_combined_boxplot(df_combined, title=title, out_path=down_plot_path, direction="Download")
    make_combined_boxplot(df_combined, title=title, out_path=up_plot_path, direction="Upload")
    print(f"[✓] Combined throughput box plot saved to: {down_plot_path} and {up_plot_path}")

else:
    print("[!] No data files found.")

