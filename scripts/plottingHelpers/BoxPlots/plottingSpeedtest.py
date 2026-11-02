#!/usr/bin/env python3
"""
Create separate box plots for Download and Upload throughput by operator.

Reads speedtest CSVs for each operator and creates two separate figures:
  - Download Speed (Mbit/s) across operators
  - Upload Speed (Mbit/s) across operators

Each figure shows box plots with median, quartiles, min-max range, and means.
"""

from pathlib import Path
import os, re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

# Configuration
DATA_DIR = "/scratch/5GMeasurements/data"
OPERATORS = ["Airtel", "Jio", "Vodafone"]
DATES = ["20261011", "20261012"] 
LOCATION="outdoor_Ground"
RESULT_DIR = "results/speedtest/"
GRAPHS_DIR= "graphs/speedtest/Throughput_BoxPlots"

# Plotting convention
plt.rcParams["font.family"] = "serif"
plt.rcParams["font.serif"] = ["Times"]
plt.rcParams.update({
    "text.usetex": False,
    "font.family": "serif",
    "font.serif": ["Times"],
    "font.size": 10,
    "figure.figsize": (10, 6),
    "legend.fontsize": 10,
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
    "ytick.major.width": 0.25,
    "ps.usedistiller": "xpdf",
    "pdf.fonttype": 42,
    "ps.fonttype": 42
})

def get_custom_stats(data_list, labels):
    stats = []
    for data, label in zip(data_list, labels):
        d = np.array(data)
        if len(d) == 0:
            d = np.array([0]) # Fallback for empty data
        
        # Calculate standard quartiles and the 10th/90th percentiles
        p10, q1, med, q3, p90 = np.percentile(d, [10, 25, 50, 75, 90])
        
        stat = {
            "label": label,
            "mean": np.mean(d),
            "med": med,
            "q1": q1,            # Box bottom = 25th percentile (Standard Q1)
            "q3": q3,            # Box top = 75th percentile (Standard Q3)
            "whislo": p10,       # Lower whisker = 10th percentile
            "whishi": p90,       # Upper whisker = 90th percentile
            "fliers": []
        }
        stats.append(stat)
    return stats

# 1. Parse text files and generate CSV for each operator
def parse_csv(date):
    for op in OPERATORS:
        op_dir = os.path.join(DATA_DIR, op, LOCATION, date)
        if not os.path.exists(op_dir):
            print("Path Issue")
            continue

        records = []
        
        # Traverse through operator and date subdirectories
        for root, _, files in os.walk(op_dir):
            for file in files:
                if file.startswith("ndt7_speedtest") and file.endswith(".txt"):
                    file_path = os.path.join(root, file)
                    
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    # Extract Timestamp, Download, and Upload
                    ts_match = re.search(r"^Timestamp\s*:\s*(.+)$", content, re.MULTILINE)
                    dl_match = re.search(r"^Download\s*:\s*(.+)$", content, re.MULTILINE)
                    ul_match = re.search(r"^Upload\s*:\s*(.+)$", content, re.MULTILINE)

                    if ts_match and dl_match and ul_match:
                        timestamp = ts_match.group(1).strip()
                        
                        # Extract numeric floating values for plotting
                        dl_speed = float(re.search(r"([\d.]+)", dl_match.group(1).strip()).group(1))
                        ul_speed = float(re.search(r"([\d.]+)", ul_match.group(1).strip()).group(1))

                        records.append({
                            "Timestamp": timestamp,
                            "Download Speed (Mbit/s)": dl_speed,
                            "Upload Speed (Mbit/s)": ul_speed
                        })

        # Save to CSV per operator
        df_op = pd.DataFrame(records)
        csv_filename = f"{date}_speedtest.csv"
        csv_path = os.path.join(RESULT_DIR, op, LOCATION, csv_filename)
        csv_dir = os.path.dirname(csv_path)
        # Create the directory if it doesn't already exist
        os.makedirs(csv_dir, exist_ok=True)
        df_op.to_csv(csv_path, index=False)
        print(f"Saved {len(df_op)} records to {csv_path}")

# 2. Read and combine data from all operators for a given date
def load_data(date):
    data = []
    for op in OPERATORS:
        csv_filename = f"{date}_speedtest.csv"
        csv_path = os.path.join(RESULT_DIR, op, LOCATION, csv_filename)
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            df["Operator"] = op
            df["Date"] = date
            data.append(df)
            print(f"[✓] Loaded {op} ({date}): {len(df)} records")
        else:
            print(f"[!] File not found: {csv_path}")
    return data

def make_combined_boxplot(summary: pd.DataFrame, title: str, out_path: Path):
    providers = sorted(summary["Operator"].unique())
    dl_data = [summary.loc[(summary["Operator"] == p) & (summary["Type"] == "Download"), "Speed (Mbit/s)"].dropna().values for p in providers]
    ul_data = [summary.loc[(summary["Operator"] == p) & (summary["Type"] == "Upload"), "Speed (Mbit/s)"].dropna().values for p in providers]
    
    
    n = len(providers)
    centers = list(range(1, n + 1))
    pos_dl = [c - 0.2 for c in centers]
    pos_ul = [c + 0.2 for c in centers]
    width = 0.32

    dl_color = "#4C72B0"
    ul_color = "#DD8452"

    fig, ax = plt.subplots(figsize=(max(7, n * 2.2), 5.5))

    ax.boxplot(
        dl_data,
        positions=pos_dl,
        widths=width,
        patch_artist=True,
        showmeans=True,
        boxprops=dict(facecolor=dl_color, alpha=0.8),
        medianprops=dict(color="black"),
        meanprops=dict(marker="^", markerfacecolor="green", markeredgecolor="green"),
    )
    ax.boxplot(
        ul_data,
        positions=pos_ul,
        widths=width,
        patch_artist=True,
        showmeans=True,
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
        Patch(facecolor=dl_color, alpha=0.8, label="Download"),
        Patch(facecolor=ul_color, alpha=0.8, label="Upload"),
    ]
    ax.legend(handles=legend_handles, loc="upper right", title="Direction")

    # fig.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)

def create_separate_plots(summary: pd.DataFrame, title: str, out_path: Path):
    providers = sorted(summary["Operator"].unique())
    dl_data = [summary.loc[(summary["Operator"] == p) & (summary["Type"] == "Download"), "Speed (Mbit/s)"].dropna().values for p in providers]
    ul_data = [summary.loc[(summary["Operator"] == p) & (summary["Type"] == "Upload"), "Speed (Mbit/s)"].dropna().values for p in providers]
    
    dl_stats = get_custom_stats(dl_data, providers)
    ul_stats = get_custom_stats(ul_data, providers)

    n = len(providers)
    centers = list(range(1, n + 1))
    width = 0.5  

    dl_color = "#4C72B0"
    ul_color = "#DD8452"

    # Removed sharey=True so each plot scales independently
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(max(10, n * 3.5), 5.5))

    # --- Download Subplot ---
    ax1.bxp(
        dl_stats,
        positions=centers,
        widths=width,
        patch_artist=True,
        showmeans=True,
        showfliers=False,
        boxprops=dict(facecolor=dl_color, alpha=0.8),
        medianprops=dict(color="black"),
        meanprops=dict(marker="^", markerfacecolor="green", markeredgecolor="green"),
    )
    ax1.set_xticks(centers)
    ax1.set_xticklabels(providers)
    ax1.set_title("Download Speed", fontweight="bold")
    ax1.set_xlabel("Operator")
    ax1.set_ylabel("Throughput (Mbps)")
    ax1.grid(axis="y", linestyle="--", alpha=0.5)

    # --- Upload Subplot ---
    ax2.bxp(
        ul_stats,
        positions=centers,
        widths=width,
        patch_artist=True,
        showmeans=True,
        showfliers=False,
        boxprops=dict(facecolor=ul_color, alpha=0.8),
        medianprops=dict(color="black"),
        meanprops=dict(marker="^", markerfacecolor="green", markeredgecolor="green"),
    )
    ax2.set_xticks(centers)
    ax2.set_xticklabels(providers)
    ax2.set_title("Upload Speed", fontweight="bold")
    ax2.set_xlabel("Operator")
    ax2.set_ylabel("Throughput (Mbps)") # Added Y-label here since scales differ
    ax2.grid(axis="y", linestyle="--", alpha=0.5)

    # Apply bold formatting to tick labels for both axes
    for ax in [ax1, ax2]:
        for label in ax.get_xticklabels() + ax.get_yticklabels():
            label.set_fontweight("bold")
        ax.set_xlim(0.5, n + 0.5)

    # Overall figure title
    fig.suptitle(title, fontweight="bold", fontsize=14)

    fig.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)

def plot_throughput(combined_data, label):
    if not combined_data:
        print(f"[!] No data files found for {label}.")
        return

    full_df = pd.concat(combined_data, ignore_index=True)
    print(f"\n[i] Total records ({label}): {len(full_df)}")

    # Prepare data for both download and upload
    df_download = full_df[["Operator", "Download Speed (Mbit/s)"]].copy()
    df_download.columns = ["Operator", "Speed (Mbit/s)"]
    df_download["Type"] = "Download"
    df_download = df_download[df_download["Speed (Mbit/s)"] > 0]

    df_upload = full_df[["Operator", "Upload Speed (Mbit/s)"]].copy()
    df_upload.columns = ["Operator", "Speed (Mbit/s)"]
    df_upload["Type"] = "Upload"
    df_upload = df_upload[df_upload["Speed (Mbit/s)"] > 0]

    # Combine both datasets
    df_combined = pd.concat([df_download, df_upload], ignore_index=True)

    # Create figure with 2 subplots side by side
    plot_dir = f"{GRAPHS_DIR}/{LOCATION}/"
    os.makedirs(plot_dir, exist_ok=True)
    if label == "all_dates":
        plot_path = f"{plot_dir}/throughput_combined.png"
    else:
        plot_path = f"{plot_dir}/{label}_throughput.png"
    title = f"Throughput by Provider"
    # make_combined_boxplot(df_combined, title=title, out_path=plot_path)
    create_separate_plots(df_combined, title=title, out_path=plot_path)
    print(f"[✓] Combined throughput box plot saved to: {plot_path}")


# Per-day graphs, then one graph pooling all dates
all_dates_data = []
for date in DATES:
    print(f"\n===== {date} =====")
    parse_csv(date)
    day_data = load_data(date)
    plot_throughput(day_data, label=date)
    all_dates_data.extend(day_data)

print("\n===== All dates =====")
plot_throughput(all_dates_data, label="all_dates")
