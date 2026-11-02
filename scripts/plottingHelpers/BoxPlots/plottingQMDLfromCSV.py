import os
import glob
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

# ==========================================
# CONFIGURATION: Directory Structure & Output
# ==========================================
# Input base path containing operator folders (e.g., results/dummyVC/Airtel/...)


# Specified Output Path
DATE="20260929"
NETWORKTYPE="5G_QMDL_Data"
INPUT_BASE_DIR = "results/dummyVC/" + NETWORKTYPE 
OUTPUT_FILE_PATH = "graphs/dummyVC/BoxPlots/" + DATE
UPLINK="readable_b881.csv"
DOWNLINK="readable_b887.csv"


def load_all_operator_data_5g(base_dir):
    records = []
    
    # Check if base path exists
    if not os.path.exists(base_dir):
        raise FileNotFoundError(f"Input base directory missing: '{base_dir}'")
        
    # Iterate through all subdirectories inside results/dummyVC/ (representing <Operator>)
    operator_dirs = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
    
    for operator in operator_dirs:
        op_path = os.path.join(base_dir, operator)
        
        
        uplink_files = glob.glob(os.path.join(op_path, "capture_*/", UPLINK))
        downlink_files = glob.glob(os.path.join(op_path, "capture_*/", DOWNLINK))
        
        # --- Process Downlink ---
        for filepath in downlink_files:
            try:
                df_dl = pd.read_csv(filepath)
                df_dl_clean = pd.DataFrame({
                    "Operator": operator,
                    "Direction": "DL",
                    "MCS": pd.to_numeric(df_dl.get("mcs"), errors="coerce"),
                    "TB Size (Bytes)": pd.to_numeric(df_dl.get("tb_size_bytes"), errors="coerce"),
                    "Resource Block Count": pd.to_numeric(df_dl.get("num_rbs"), errors="coerce")
                })
                records.append(df_dl_clean)
            except Exception as e:
                print(f"[!] Warning: Failed to parse {filepath}: {e}")

        # --- Process Uplink ---
        for filepath in uplink_files:
            try:
                df_ul = pd.read_csv(filepath)
                df_ul_clean = pd.DataFrame({
                    "Operator": operator,
                    "Direction": "UL",
                    "MCS": pd.to_numeric(df_ul.get("avg_mcs_this_interval"), errors="coerce"),
                    "TB Size (Bytes)": pd.to_numeric(df_ul.get("delta_new_tx_bytes"), errors="coerce"),
                    "Resource Block Count": pd.to_numeric(df_ul.get("delta_num_prb"), errors="coerce")
                })
                records.append(df_ul_clean)
            except Exception as e:
                print(f"[!] Warning: Failed to parse {filepath}: {e}")

    if not records:
        raise ValueError(f"No valid uplink or downlink files found under '{base_dir}'.")
        
    combined_df = pd.concat(records)
    return combined_df

def load_all_operator_data_4g(base_dir):
    records = []
    
    # Check if base path exists
    if not os.path.exists(base_dir):
        raise FileNotFoundError(f"Input base directory missing: '{base_dir}'")
        
    # Iterate through all subdirectories inside results/dummyVC/ (representing <Operator>)
    operator_dirs = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
    
    for operator in operator_dirs:
        op_path = os.path.join(base_dir, operator, DATE)
        print(op_path)
        
        uplink_files = glob.glob(os.path.join(op_path, "capture_*/", UPLINK))
        downlink_files = glob.glob(os.path.join(op_path, "capture_*/", DOWNLINK))
        print(uplink_files)
        
        # --- Process Downlink ---
        for filepath in downlink_files:
            try:
                df_dl = pd.read_csv(filepath)
                df_dl_clean = pd.DataFrame({
                    "Operator": operator,
                    "Direction": "DL",
                    "MCS": pd.to_numeric(df_dl.get("mcs"), errors="coerce"),
                    "TB Size (Bytes)": pd.to_numeric(df_dl.get("tb_size_bytes"), errors="coerce"),
                    "Resource Block Count": pd.to_numeric(df_dl.get("num_rbs_subframe"), errors="coerce")
                })
                records.append(df_dl_clean)
            except Exception as e:
                print(f"[!] Warning: Failed to parse {filepath}: {e}")

        # --- Process Uplink ---
        for filepath in uplink_files:
            try:
                df_ul = pd.read_csv(filepath)
                df_ul_clean = pd.DataFrame({
                    "Operator": operator,
                    "Direction": "UL",
                    # "MCS": pd.to_numeric(df_ul.get(""), errors="coerce"),
                    "TB Size (Bytes)": pd.to_numeric(df_ul.get("tb_size_bytes"), errors="coerce"),
                    "Resource Block Count": pd.to_numeric(df_ul.get("num_rb"), errors="coerce")
                })
                records.append(df_ul_clean)
            except Exception as e:
                print(f"[!] Warning: Failed to parse {filepath}: {e}")

    if not records:
        raise ValueError(f"No valid uplink or downlink files found under '{base_dir}'.")
        
    combined_df = pd.concat(records)
    return combined_df


def plot_dl_ul_boxplots(df, output_dir):

    os.makedirs(output_dir, exist_ok=True)
    sns.set_theme(style="whitegrid")

    # Column name, Title for the plot, and file tag for saving
    metrics = [
        ("MCS", "Modulation and Coding Scheme", "MCS"),
        ("TB Size (Bytes)", "Transport Block Size", "TB_Size"),
        ("Resource Block Count", "Resource Block Count", "RB_Count")
    ]
    
    colors = {"DL": "#4C72B0", "UL": "#DD8452"}
    
    for metric_col, title, file_tag in metrics:
        if metric_col not in df.columns:
            print(f"[!] Column '{metric_col}' not found in DataFrame. Skipping {file_tag} plot.")
            continue
            
        metric_df = df.dropna(subset=[metric_col])
        if metric_df.empty:
            print(f"[!] No valid data available for '{metric_col}'. Skipping {file_tag} plot.")
            continue
        
        metric_df = df.dropna(subset=[metric_col])
        fig, ax = plt.subplots(figsize=(6, 6))
        
        sns.boxplot(
            data=metric_df,
            x="Operator",
            y=metric_col,
            hue="Direction",
            order=["Airtel", "Jio", "Vodafone"],
            palette=colors,
            ax=ax,
            showfliers=False,
            showmeans=True,  # Display mean marker
            meanprops={
                "marker": "^",
                "markerfacecolor": "red",
                "markeredgecolor": "red",
                "markersize": "5"
            }
        )
        
        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.set_xlabel("Provider", fontsize=12, fontweight="bold")
        ax.set_ylabel(metric_col, fontsize=12, fontweight="bold")
        
        # Increase font size, bold, and darken tick labels
        ax.tick_params(axis="both", which="major", labelsize=12)
        for label in ax.get_xticklabels() + ax.get_yticklabels():
            label.set_fontweight("bold")
            label.set_color("#111111")
            
        ax.legend(title="Direction")

        plt.tight_layout()
        
        # Save each plot with its specific metric tag
        filename = os.path.join(output_dir, f"{NETWORKTYPE}_{file_tag}.png")
        plt.savefig(filename, dpi=300)
        plt.close()
        
        print(f"[✓] Box plot successfully saved to: {filename}")


if __name__ == "__main__":
    # combined_data = load_all_operator_data_5g(INPUT_BASE_DIR)
    combined_data = load_all_operator_data_4g(INPUT_BASE_DIR)
    plot_dl_ul_boxplots(combined_data, OUTPUT_FILE_PATH)