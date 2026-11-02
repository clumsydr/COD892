# #!/usr/bin/env python3
# """
# Ratio (stacked-bar) plots of RSRP / RSRQ signal factors per operator.

# Reads   <BASE_DIR>/<op>/<loc>/<date>_metrics.csv      (from coverage_metrics.py)
#           ..., rsrp, rsrq, sinr, ..., RSRP Factor, RSRQ Factor, ...
# Writes  <GRAPH_ROOT>/<loc>/<dates>_<param>.png

# Each bar = one operator; segments = % of samples that are Strong / Average /
# Poor / Very poor. The factor columns written by coverage_metrics.py are used
# directly, so the plot always matches the CSV. If a file has no factor column
# (older output), the factor is computed here from the raw value and SIG_LEVELS.
# Samples with a blank value / blank factor are not counted.

# Usage: edit SETTINGS, then run
#   python generate_ratio_plots.py
# """
# import os, sys, argparse
# import numpy as np
# import pandas as pd
# import matplotlib.pyplot as plt

# # ============================ SETTINGS =====================================
# OPERATORS = ['Airtel', 'Jio', 'Vodafone']
# BASE_DIRS = {
#     "speedtest": "results/coverage_metrics/speedtest",
#     "dummyVC":   "results/coverage_metrics",
# }
# GRAPH_ROOTS = {
#     "speedtest": "graphs/speedtest/Ratio_plots",
#     "dummyVC":   "graphs/dummyVC/Ratio_plots",
# }

# # Signal levels. Bands, best to worst:
# #   Strong    : value >  strong   (>= strong if strong_inclusive=True)
# #   Average   : average <= value < strong   (<= strong if strong_inclusive=False)
# #   Poor      : poor    <= value < average
# #   Very poor : value <  poor
# SIG_LEVELS = {
#     "rsrp": dict(strong=-85, average=-105, poor=-120, strong_inclusive=False),
#     "rsrq": dict(strong=-9, average=-14, poor=-19, strong_inclusive=True),
#     "sinr": dict(strong=20, average=13, poor=0, strong_inclusive=False),
# }
# UNITS = {"rsrp": "dBm", "rsrq": "dB", "sinr": "dB"}
# PLOT_PARAMS = ["rsrp", "rsrq"]     # add "sinr" to plot it too
# # factor column written by coverage_metrics.py for each metric
# FACTOR_COLUMNS = {"rsrp": "RSRP Factor", "rsrq": "RSRQ Factor", "sinr": "SINR Factor"}
# FACTOR_LABELS = ["Strong", "Average", "Poor", "Very poor"]   # best -> worst

# # Colours follow band order (best -> worst)
# BAND_COLORS = ['#BAED91', '#89CFEF', '#ffee8c', '#ff9999']
# LABEL_MIN_PCT = 4                  # write % on segments wider than this
# # ===========================================================================

# plt.rcParams["font.family"] = "serif"
# plt.rcParams["font.serif"] = ["Times New Roman", "Times", "DejaVu Serif"]
# plt.rcParams.update({
#     "text.usetex": False,
#     "font.family": "serif",
#     "font.size": 10,
#     "figure.figsize": (3.125, 1.56),
#     "legend.fontsize": 8,
#     "legend.fancybox": True,
#     "axes.linewidth": 0.5,
#     "patch.linewidth": 0.5,
#     "lines.linewidth": 1.0,
#     "grid.linewidth": 0.25,
#     "xtick.major.width": 0.25,
#     "xtick.minor.width": 0.25,
#     "ytick.major.width": 0.25,
#     "ytick.minor.width": 0.25,
#     "pdf.fonttype": 42,
#     "ps.fonttype": 42
# })


# def fmt(x):
#     return f"{x:g}"


# def legend_labels(lv):
#     """Factor names with their value ranges, for the legend."""
#     s, a, p = lv["strong"], lv["average"], lv["poor"]
#     inc = lv.get("strong_inclusive", False)
#     return [f"Strong ({'≥' if inc else '>'} {fmt(s)})",
#             f"Average ({fmt(a)} to {fmt(s)})",
#             f"Poor ({fmt(p)} to {fmt(a)})",
#             f"Very poor (< {fmt(p)})"]


# def factor_from_values(values, lv):
#     """Fallback: Strong / Average / Poor / Very poor from raw values (NaN stays NaN)."""
#     s, a, p = lv["strong"], lv["average"], lv["poor"]
#     strong = values >= s if lv.get("strong_inclusive", False) else values > s
#     out = pd.Series(np.nan, index=values.index, dtype=object)
#     out[values < p] = FACTOR_LABELS[3]
#     out[(values >= p) & (values < a)] = FACTOR_LABELS[2]
#     out[(values >= a) & ~strong] = FACTOR_LABELS[1]
#     out[strong] = FACTOR_LABELS[0]
#     return out


# def load_factors(op, loc, param):
#     """Factor label per sample for one operator, pooled over DATES.
#     Returns (Series of labels, NaN where blank, source description)."""
#     parts, sources = [], set()
#     for date in DATES:
#         path = os.path.join(BASE_DIRS[SCENARIO], op, loc, f"{date}_metrics.csv")
#         if not os.path.exists(path):
#             print(f"[!] missing {path}")
#             continue
#         try:
#             df = pd.read_csv(path)
#         except Exception as e:
#             print(f"Error reading {path}: {e}")
#             continue
#         cols = {c.lower().strip(): c for c in df.columns}
#         fcol = cols.get(FACTOR_COLUMNS.get(param, "").lower())
#         if fcol:
#             f = df[fcol].astype(str).str.strip()
#             norm = {l.lower(): l for l in FACTOR_LABELS}
#             f = f.str.lower().map(norm)                    # unknown / blank -> NaN
#             sources.add(fcol)
#         elif cols.get(param.lower()):
#             v = pd.to_numeric(df[cols[param.lower()]], errors='coerce')
#             f = factor_from_values(v, SIG_LEVELS[param])
#             sources.add(f"{param} + SIG_LEVELS")
#         else:
#             print(f"[!] Neither '{FACTOR_COLUMNS.get(param)}' nor '{param}' in {path}")
#             continue
#         parts.append(f)
#     s = pd.concat(parts, ignore_index=True) if parts else pd.Series(dtype=object)
#     return s, ", ".join(sorted(sources))


# def main():
#     if SCENARIO not in BASE_DIRS:
#         sys.exit(f'SCENARIO must be one of {list(BASE_DIRS)}')
#     date_tag = "_".join(DATES)

#     for loc in LOCATIONS:
#         graph_dir = os.path.join(GRAPH_ROOTS[SCENARIO], loc)
#         os.makedirs(graph_dir, exist_ok=True)

#         for param in PLOT_PARAMS:
#             lv = SIG_LEVELS[param]
#             labels = legend_labels(lv)
#             counts, n_valid, n_blank, source = {}, {}, {}, {}

#             for op in OPERATORS:
#                 f, source[op] = load_factors(op, loc, param)
#                 n_blank[op] = int(f.isna().sum())
#                 f = f.dropna()
#                 n_valid[op] = len(f)
#                 c = f.value_counts()
#                 counts[op] = [int(c.get(l, 0)) for l in FACTOR_LABELS]

#             df_plot = pd.DataFrame.from_dict(counts, orient='index', columns=labels)
#             row_sums = df_plot.sum(axis=1)
#             if row_sums.sum() == 0:
#                 print(f"[!] No {param} data for {loc} ({SCENARIO}). Skipping plot.")
#                 continue
#             df_percent = df_plot.div(row_sums.replace(0, np.nan), axis=0).fillna(0) * 100
#             # show sample count next to the operator name
#             df_percent.index = [f"{op}\n(n={n_valid[op]:,})" for op in df_percent.index]

#             fig, ax = plt.subplots(figsize=(10, 4.5))
#             df_percent.plot(kind='barh', stacked=True, ax=ax,
#                             color=BAND_COLORS[:len(labels)],
#                             edgecolor='black', linewidth=0.5)

#             for container in ax.containers:
#                 for patch in container:
#                     width = patch.get_width()
#                     if width > LABEL_MIN_PCT:
#                         ax.text(patch.get_x() + width / 2,
#                                 patch.get_y() + patch.get_height() / 2,
#                                 f'{width:.1f}%', ha='center', va='center',
#                                 color='black', fontweight='bold', fontsize=9)

#             ax.set_xlim(0, 100)
#             ax.set_xlabel(f'Ratio of {param.upper()} samples (%)', fontsize=11)
#             ax.set_ylabel('Operators', fontsize=11)
#             ax.set_title(f'{param.upper()} Ratio Distribution ({SCENARIO}, {loc})',
#                          fontsize=12, fontweight='bold')
#             ax.invert_yaxis()                       # first operator on top
#             ax.legend(title=f"{param.upper()} ({UNITS.get(param, '')})",
#                       bbox_to_anchor=(1.02, 1), loc='upper left')
#             plt.tight_layout()

#             out_path = os.path.join(graph_dir, f"{date_tag}_{param}.png")
#             plt.savefig(out_path, dpi=300, bbox_inches='tight')
#             plt.close()

#             # numbers behind the plot
#             table = df_plot.copy()
#             table.insert(0, 'blank', pd.Series(n_blank))
#             table.insert(0, 'samples', pd.Series(n_valid))
#             table['source'] = pd.Series(source)
#             print(f"\n{param.upper()} — {loc} ({SCENARIO})")
#             print(table.to_string())
#             print(f"Successfully generated: {out_path}")


# if __name__ == "__main__":
#     parser = argparse.ArgumentParser()
#     parser.add_argument(
#         "--locations",
#         nargs="+",
#         default=["indoor_Shubham_JiaSarai"],
#         help="List of measurement locations (space-separated)",
#     )
#     parser.add_argument(
#         "--dates",
#         nargs="+",                    
#         default=["20261018"],
#         help="List of dates in YYYYMMDD format (space-separated)",
#     )
#     parser.add_argument(
#         "--scenario",
#         type=str,
#         default="speedtest",
#         choices=["speedtest", "dummyVC"],
#     )
#     args = parser.parse_args()
#     LOCATIONS = args.locations
#     DATES = args.dates
#     SCENARIO = args.scenario
#     main()

#!/usr/bin/env python3
"""
Ratio (stacked-bar) plots of RSRP / RSRQ signal factors per operator.

Reads   <BASE_DIR>/<op>/<loc>/<date>_metrics.csv      (from coverage_metrics.py)
          ..., rsrp, rsrq, sinr, ..., RSRP Factor, RSRQ Factor, ...
Writes  <GRAPH_ROOT>/<loc>/<date>_<param>.png

Each bar = one operator; segments = % of samples that are Strong / Average /
Poor / Very poor. The factor columns written by coverage_metrics.py are used
directly, so the plot always matches the CSV. If a file has no factor column
(older output), the factor is computed here from the raw value and SIG_LEVELS.
Samples with a blank value / blank factor are not counted.

Usage: edit SETTINGS, then run
  python generate_ratio_plots.py
"""
import os, sys, argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ============================ SETTINGS =====================================
OPERATORS = ['Airtel', 'Jio', 'Vodafone']
BASE_DIRS = {
    "speedtest": "results/coverage_metrics/speedtest",
    "dummyVC":   "results/coverage_metrics",
}
GRAPH_ROOTS = {
    "speedtest": "graphs/speedtest/Ratio_plots",
    "dummyVC":   "graphs/dummyVC/Ratio_plots",
}

# Signal levels. Bands, best to worst:
#   Strong    : value >  strong   (>= strong if strong_inclusive=True)
#   Average   : average <= value < strong   (<= strong if strong_inclusive=False)
#   Poor      : poor    <= value < average
#   Very poor : value <  poor
SIG_LEVELS = {
    "rsrp": dict(strong=-85, average=-105, poor=-120, strong_inclusive=False),
    "rsrq": dict(strong=-9, average=-14, poor=-19, strong_inclusive=True),
    "sinr": dict(strong=20, average=13, poor=0, strong_inclusive=False),
}
UNITS = {"rsrp": "dBm", "rsrq": "dB", "sinr": "dB"}
PLOT_PARAMS = ["rsrp", "rsrq"]     # add "sinr" to plot it too
# factor column written by coverage_metrics.py for each metric
FACTOR_COLUMNS = {"rsrp": "RSRP Factor", "rsrq": "RSRQ Factor", "sinr": "SINR Factor"}
FACTOR_LABELS = ["Strong", "Average", "Poor", "Very poor"]   # best -> worst

# Colours follow band order (best -> worst)
BAND_COLORS = ['#BAED91', '#89CFEF', '#ffee8c', '#ff9999']
LABEL_MIN_PCT = 4                  # write % on segments wider than this
# ===========================================================================

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


def fmt(x):
    return f"{x:g}"


def legend_labels(lv):
    """Factor names with their value ranges, for the legend."""
    s, a, p = lv["strong"], lv["average"], lv["poor"]
    inc = lv.get("strong_inclusive", False)
    return [f"Strong ({'≥' if inc else '>'} {fmt(s)})",
            f"Average ({fmt(a)} to {fmt(s)})",
            f"Poor ({fmt(p)} to {fmt(a)})",
            f"Very poor (< {fmt(p)})"]


def factor_from_values(values, lv):
    """Fallback: Strong / Average / Poor / Very poor from raw values (NaN stays NaN)."""
    s, a, p = lv["strong"], lv["average"], lv["poor"]
    strong = values >= s if lv.get("strong_inclusive", False) else values > s
    out = pd.Series(np.nan, index=values.index, dtype=object)
    out[values < p] = FACTOR_LABELS[3]
    out[(values >= p) & (values < a)] = FACTOR_LABELS[2]
    out[(values >= a) & ~strong] = FACTOR_LABELS[1]
    out[strong] = FACTOR_LABELS[0]
    return out


def load_factors(op, loc, date, param):
    """Factor label per sample for one operator for a specific date.
    Returns (Series of labels, NaN where blank, source description)."""
    sources = set()
    path = os.path.join(BASE_DIRS[SCENARIO], op, loc, f"{date}_metrics.csv")
    if not os.path.exists(path):
        print(f"[!] missing {path}")
        return pd.Series(dtype=object), ""
    try:
        df = pd.read_csv(path)
    except Exception as e:
        print(f"Error reading {path}: {e}")
        return pd.Series(dtype=object), ""
    cols = {c.lower().strip(): c for c in df.columns}
    fcol = cols.get(FACTOR_COLUMNS.get(param, "").lower())
    if fcol:
        f = df[fcol].astype(str).str.strip()
        norm = {l.lower(): l for l in FACTOR_LABELS}
        f = f.str.lower().map(norm)                    # unknown / blank -> NaN
        sources.add(fcol)
    elif cols.get(param.lower()):
        v = pd.to_numeric(df[cols[param.lower()]], errors='coerce')
        f = factor_from_values(v, SIG_LEVELS[param])
        sources.add(f"{param} + SIG_LEVELS")
    else:
        print(f"[!] Neither '{FACTOR_COLUMNS.get(param)}' nor '{param}' in {path}")
        return pd.Series(dtype=object), ""
    return f, ", ".join(sorted(sources))


def main():
    if SCENARIO not in BASE_DIRS:
        sys.exit(f'SCENARIO must be one of {list(BASE_DIRS)}')

    for loc in LOCATIONS:
        graph_dir = os.path.join(GRAPH_ROOTS[SCENARIO], loc)
        os.makedirs(graph_dir, exist_ok=True)

        for date in DATES:
            for param in PLOT_PARAMS:
                lv = SIG_LEVELS[param]
                labels = legend_labels(lv)
                counts, n_valid, n_blank, source = {}, {}, {}, {}

                for op in OPERATORS:
                    f, source[op] = load_factors(op, loc, date, param)
                    n_blank[op] = int(f.isna().sum())
                    f = f.dropna()
                    n_valid[op] = len(f)
                    c = f.value_counts()
                    counts[op] = [int(c.get(l, 0)) for l in FACTOR_LABELS]

                df_plot = pd.DataFrame.from_dict(counts, orient='index', columns=labels)
                row_sums = df_plot.sum(axis=1)
                if row_sums.sum() == 0:
                    print(f"[!] No {param} data for {loc} on {date} ({SCENARIO}). Skipping plot.")
                    continue
                df_percent = df_plot.div(row_sums.replace(0, np.nan), axis=0).fillna(0) * 100
                # show sample count next to the operator name
                df_percent.index = [f"{op}\n(n={n_valid[op]:,})" for op in df_percent.index]

                fig, ax = plt.subplots(figsize=(10, 4.5))
                df_percent.plot(kind='barh', stacked=True, ax=ax,
                                color=BAND_COLORS[:len(labels)],
                                edgecolor='black', linewidth=0.5)

                for container in ax.containers:
                    for patch in container:
                        width = patch.get_width()
                        if width > LABEL_MIN_PCT:
                            ax.text(patch.get_x() + width / 2,
                                    patch.get_y() + patch.get_height() / 2,
                                    f'{width:.1f}%', ha='center', va='center',
                                    color='black', fontweight='bold', fontsize=9)

                ax.set_xlim(0, 100)
                ax.set_xlabel(f'Ratio of {param.upper()} samples (%)', fontsize=11)
                ax.set_ylabel('Operators', fontsize=11)
                ax.set_title(f'{param.upper()} Ratio Distribution ({SCENARIO}, {loc}, {date})',
                             fontsize=12, fontweight='bold')
                ax.invert_yaxis()                       # first operator on top
                ax.legend(title=f"{param.upper()} ({UNITS.get(param, '')})",
                          bbox_to_anchor=(1.02, 1), loc='upper left')
                plt.tight_layout()

                out_path = os.path.join(graph_dir, f"{date}_{param}.png")
                plt.savefig(out_path, dpi=300, bbox_inches='tight')
                plt.close()

                # numbers behind the plot
                table = df_plot.copy()
                table.insert(0, 'blank', pd.Series(n_blank))
                table.insert(0, 'samples', pd.Series(n_valid))
                table['source'] = pd.Series(source)
                print(f"\n{param.upper()} — {loc} on {date} ({SCENARIO})")
                print(table.to_string())
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
    args = parser.parse_args()
    LOCATIONS = args.locations
    DATES = args.dates
    SCENARIO = args.scenario
    main()