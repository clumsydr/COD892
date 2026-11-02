import os
import pandas as pd
import matplotlib.pyplot as plt

# Configuration
OPERATORS = ['Airtel', 'Jio', 'Vodafone']
LOCATIONS = ['indoor_Bharti501']
PARAMETERS = {
    'modulation': ['QPSK', '16QAM', '64QAM', '256QAM'],
    'rsrp': ['Strong', 'Average', 'Poor'],
    'rsrq': ['Strong', 'Average', 'Poor'],
    'sinr': ['Strong', 'Average', 'Poor'],
    'MIMO (layers)': ['1', '2', '3', '4']
}
BASE_DIR = 'results/allMetrics_4G/speedtest'
GRAPH_ROOT = 'graphs/speedtest/Ratio_plots'
G="4G"
traffic_types = {
    'DL': 'combined_downlink.csv',
    'UL': 'combined_uplink.csv'
}

# Setting Graph Specifications
plt.rcParams["font.family"] = "serif"
plt.rcParams["font.serif"] = ["Times New Roman", "Times", "DejaVu Serif"]
plt.rcParams.update({
    "text.usetex": False,
    "font.family": "serif",
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

for loc in LOCATIONS:
    GRAPH_DIR = os.path.join(GRAPH_ROOT, loc)
    os.makedirs(GRAPH_DIR, exist_ok=True)

    for direction, filename in traffic_types.items():
        for param, categories in PARAMETERS.items():
            plot_data = []

            for op in OPERATORS:
                csv_path = os.path.join(BASE_DIR, op, loc, filename)
                row_counts = {cat: 0 for cat in categories}

                if os.path.exists(csv_path):
                    try:
                        df = pd.read_csv(csv_path)
                        col_map = {c.lower().strip(): c for c in df.columns}
                        target_col = col_map.get(param.lower())

                        if target_col and not df.empty:
                            series = df[target_col]
                            numeric_series = pd.to_numeric(series, errors='coerce')
                            if numeric_series.notna().any():
                                series = numeric_series.round().dropna().astype(int)

                            counts = series.astype(str).str.strip().value_counts()
                            for cat in categories:
                                matching_keys = [k for k in counts.keys() if k.lower() == cat.lower()]
                                val = sum(counts[k] for k in matching_keys) if matching_keys else 0
                                row_counts[cat] = val
                        elif not target_col:
                            print(f"[!] Column '{param}' not found in {csv_path}")
                    except Exception as e:
                        print(f"Error reading {csv_path}: {e}")
                else:
                    print(f"[!] File not found: {csv_path}")

                plot_data.append(row_counts)

            df_plot = pd.DataFrame(plot_data, index=OPERATORS)

            # Convert absolute counts to percentages (0 to 100%)
            row_sums = df_plot.sum(axis=1)
            df_percent = df_plot.div(row_sums, axis=0).fillna(0) * 100

            # Plotting Horizontal Stacked Bar Chart
            fig, ax = plt.subplots(figsize=(10, 4.5))

            colors = ['#89CFEF', '#ffee8c', '#BAED91', '#8172b2']

            bars = df_percent.plot(
                kind='barh',
                stacked=True,
                ax=ax,
                color=colors[:len(categories)],
                edgecolor='black',
                linewidth=0.5
            )

            # Annotate each bar segment with its percentage
            for container in ax.containers:
                for patch in container:
                    width = patch.get_width()
                    if width > 4:  # Only label if segment is wider than 4% to avoid overlap clutter
                        x_center = patch.get_x() + width / 2
                        y_center = patch.get_y() + patch.get_height() / 2
                        ax.text(
                            x_center, y_center, f'{width:.1f}%',
                            ha='center', va='center',
                            color='black', fontweight='bold', fontsize=9
                        )

            # Formatting axes and layout matching your sketch
            ax.set_xlim(0, 100)
            ax.set_xlabel(f'Ratio of {param} (%)', fontsize=11)
            ax.set_ylabel('Operators', fontsize=11)
            ax.set_title(f'{direction} - {param.upper()} Ratio Distribution', fontsize=12, fontweight='bold')

            # Invert y-axis so Airtel is at the top and Vodafone at the bottom
            ax.invert_yaxis()

            # Place legend clearly outside
            ax.legend(title=param.capitalize(), bbox_to_anchor=(1.02, 1), loc='upper left')

            plt.tight_layout()

            # Save output image
            out_filename = f"{direction}_{param}_{G}.png"
            out_path = os.path.join(GRAPH_DIR, out_filename)
            plt.savefig(out_path, dpi=300, bbox_inches='tight')
            plt.close()
            print(f"Successfully generated: {out_path}")