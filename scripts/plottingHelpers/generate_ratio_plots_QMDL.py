import os
import glob
import sys, argparse
import pandas as pd
import matplotlib.pyplot as plt

# ============================ SETTINGS =====================================
OPERATORS = ['Airtel', 'Jio', 'Vodafone']
PARAMETERS = {
    'Modulation': ['QPSK', '16QAM', '64QAM', '256QAM'],
    'MIMO Layers': ['1', '2', '3', '4']
}
traffic_types = {
    'DL': 'downlink_win1000ms.csv',
    'UL': 'uplink_win1000ms.csv'
}
# ===========================================================================

# Distinct color palettes mapped by radio filter type
COLOR_PALETTES = {
    'Both': ['#a8d5e5', '#7fb3d5', '#5499c7', '#2980b9'], 
    '4G':   ['#ff9999', '#ffcc99', '#ffff99', '#ccff99'], 
    '5G':   ['#89CFEF', '#ffee8c', '#BAED91', '#8172b2'] 
}

# Setting Graph Specifications
plt.rcParams["font.family"] = "serif"
plt.rcParams["font.serif"] = ["Times New Roman", "Times", "DejaVu Serif"]
plt.rcParams.update({
    "text.usetex": False,
    "font.family": "serif",
    "font.size": 10,
    "figure.figsize": (3.125, 1.56),
    "legend.fontsize": 8,
    "legend.fancybox": True,
    "axes.linewidth": 0.5,
    "axes.prop_cycle": plt.cycler(color=[
        "#348ABD", "#A60628", "#7A68A6", "#467821", "#CF4457", "#188487", "#E24A33"
    ]),
    "patch.linewidth": 0.5,
    "lines.linewidth": 1.0,
    "grid.linewidth": 0.25,
    "xtick.major.width": 0.25,
    "xtick.minor.width": 0.25,
    "ytick.major.width": 0.25,
    "ytick.minor.width": 0.25,
    "pdf.fonttype": 42,
    "ps.fonttype": 42
})

def map_mcs_to_modulation(mcs_val):
    """Maps 3GPP MCS index to modulation scheme."""
    try:
        val = int(float(mcs_val))
    except (ValueError, TypeError):
        return None
        
    if 0 <= val <= 4:
        return 'QPSK'
    elif 5 <= val <= 10:
        return '16QAM'
    elif 11 <= val <= 19:
        return '64QAM'
    elif 20 <= val <= 27:
        return '256QAM'
    else:
        return None

def main():
    for loc in LOCATIONS:
        GRAPH_DIR = os.path.join(GRAPH_ROOT, loc)
        os.makedirs(GRAPH_DIR, exist_ok=True)

        # Loop through each date individually so each gets its own plot
        for date in DATES:
            for direction, file_suffix in traffic_types.items():
                for param, categories in PARAMETERS.items():
                    plot_data = []

                    for op in OPERATORS:
                        row_counts = {cat: 0 for cat in categories}

                        csv_filename = f"{date}_{file_suffix}"
                        csv_path = os.path.join(BASE_DIR, op, loc, csv_filename)

                        if os.path.exists(csv_path):
                            try:
                                df = pd.read_csv(csv_path)
                                
                                if RADIO_FILTER in ["4G", "5G"] and "radio_connection" in df.columns:
                                    df = df[df["radio_connection"].astype(str).str.upper() == RADIO_FILTER.upper()]

                                if df.empty:
                                    plot_data.append(row_counts)
                                    continue

                                col_map = {c.lower().strip(): c for c in df.columns}
                                
                                if param.lower() == 'modulation':
                                    mod_col = col_map.get('modulation')
                                    mcs_col = col_map.get('mcs') or col_map.get('mcs index')
                                    
                                    derived_mods = []
                                    for idx, row in df.iterrows():
                                        mod_val = str(row[mod_col]).strip() if mod_col and pd.notna(row[mod_col]) else ""
                                        if not mod_val or mod_val.lower() in ["nan", "none", ""]:
                                            if mcs_col and pd.notna(row[mcs_col]):
                                                mod_val = map_mcs_to_modulation(row[mcs_col])
                                        
                                        if mod_val:
                                            clean_mod = mod_val.replace(" ", "").upper()
                                            derived_mods.append(clean_mod)
                                            
                                    series = pd.Series(derived_mods)
                                else:
                                    target_col = col_map.get(param.lower())
                                    if target_col:
                                        series = df[target_col]
                                        numeric_series = pd.to_numeric(series, errors='coerce')
                                        if numeric_series.notna().any():
                                            series = numeric_series.round().dropna().astype(int)
                                    else:
                                        series = pd.Series([], dtype=str)

                                if not series.empty:
                                    counts = series.astype(str).str.strip().str.upper().value_counts()
                                    for cat in categories:
                                        cat_clean = cat.replace(" ", "").upper()
                                        matching_keys = [k for k in counts.keys() if k.replace(" ", "") == cat_clean]
                                        val = sum(counts[k] for k in matching_keys) if matching_keys else 0
                                        row_counts[cat] += val

                            except Exception as e:
                                print(f"Error reading {csv_path}: {e}")

                        plot_data.append(row_counts)

                    df_plot = pd.DataFrame(plot_data, index=OPERATORS)

                    row_sums = df_plot.sum(axis=1)
                    if row_sums.sum() == 0:
                        print(f"[!] No data available for {date} | {direction} {param} with filter '{RADIO_FILTER}'. Skipping plot.")
                        continue

                    df_percent = df_plot.div(row_sums, axis=0).fillna(0) * 100

                    fig, ax = plt.subplots(figsize=(10, 4.5))
                    palette_key = RADIO_FILTER if RADIO_FILTER in COLOR_PALETTES else 'Both'
                    colors = COLOR_PALETTES[palette_key]

                    df_percent.plot(
                        kind='barh',
                        stacked=True,
                        ax=ax,
                        color=colors[:len(categories)],
                        edgecolor='black',
                        linewidth=0.5
                    )

                    for container in ax.containers:
                        for patch in container:
                            width = patch.get_width()
                            if width > 4:
                                x_center = patch.get_x() + width / 2
                                y_center = patch.get_y() + patch.get_height() / 2
                                ax.text(
                                    x_center, y_center, f'{width:.1f}%',
                                    ha='center', va='center',
                                    color='black', fontweight='bold', fontsize=9
                                )

                    ax.set_xlim(0, 100)
                    ax.set_xlabel(f'Ratio of {param} (%)', fontsize=11)
                    ax.set_ylabel('Operators', fontsize=11)
                    
                    title_tag = f"({RADIO_FILTER})" if RADIO_FILTER != "Both" else "(Combined 4G+5G)"
                    ax.set_title(f'{date} - {direction} {param} Ratio Distribution {title_tag}', fontsize=12, fontweight='bold')

                    ax.invert_yaxis()
                    ax.legend(title=param.capitalize(), bbox_to_anchor=(1.02, 1), loc='upper left')

                    plt.tight_layout()

                    param_clean = param.replace(" ", "_").lower()
                    out_filename = f"{date}_{direction}_{param_clean}_{RADIO_FILTER.lower()}.png"
                    out_path = os.path.join(GRAPH_DIR, out_filename)
                    plt.savefig(out_path, dpi=300, bbox_inches='tight')
                    plt.close()
                    print(f"Successfully generated: {out_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--locations",
        nargs="+",
        default=["indoor_Shubham_JiaSarai"],
        help="List of measurement locations (space-separated)",
    )
    parser.add_argument(
        "--dates",
        nargs="+",                    
        default=["20261018"],
        help="List of dates in YYYYMMDD format (space-separated)",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default="speedtest",
        choices=["speedtest", "dummyVC"],
    )
    parser.add_argument(
        "--radio_connection",
        type=str,
        default="5G",
        choices=["5G", "4G"],
    )
    args = parser.parse_args()
    LOCATIONS = args.locations
    DATES = args.dates
    SCENARIO = args.scenario
    RADIO_FILTER = args.radio_connection
    
    if SCENARIO == "speedtest":
        BASE_DIR = 'results/granular_qmdl_metrics/speedtest'
        GRAPH_ROOT = 'graphs/speedtest/Granularity_Ratio_plots/1000ms'
    else:
        BASE_DIR = 'results/granular_qmdl_metrics'
        GRAPH_ROOT = 'graphs/dummyVC/Granularity_Ratio_plots/1000ms'
        
    main()