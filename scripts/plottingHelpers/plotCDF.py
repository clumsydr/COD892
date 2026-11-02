import glob, os, sys, argparse
import numpy as np
import pandas as pd 
import matplotlib.pyplot as plt

# ============================ SETTINGS =====================================
OPERATORS = None                       # e.g. ["Airtel"] or None for all
DIRECTIONS = ["downlink", "uplink"]    # one panel per direction
GROUP_BY = "op"      # "op"     -> one line per operator
                     # "op_rat" -> one line per operator and radio_connection (4G / 5G / tie)
WEIGHT   = "record"  # "record" -> every record counts equally (plain CDF)
                     # "run"    -> every run counts equally within its line
LOG_X    = False     # True = log-scale x axis
# ===========================================================================


def load(target_loc, target_date):
    frames = []
    op_list = [OPERATORS] if isinstance(OPERATORS, str) else OPERATORS

    for p in glob.glob(os.path.join(IN, "*", "*", "*_*.csv")):
        op, loc, fname = os.path.normpath(p).split(os.sep)[-3:]
        if fname.endswith("_collisions.csv"):
            continue
        # date, direction = fname[:-4].split("_")
        name_without_ext = fname[:-4]  # or os.path.splitext(fname)[0]
        date, direction, window_size = name_without_ext.split("_")
        
        if direction not in DIRECTIONS:
            continue
        if op_list and op not in op_list: continue
        if loc != target_loc: continue
        if date != target_date: continue
        
        # Read matching columns from the unified CSV
        df = pd.read_csv(p, usecols=["run", "radio_connection", "Resource blocks"])
        df["Resource blocks"] = pd.to_numeric(df["Resource blocks"], errors="coerce")
        df = df.dropna(subset=["Resource blocks"])
        df["op"], df["loc"], df["date"], df["direction"] = op, loc, date, direction
        df["run_id"] = loc + "/" + date + "/" + df["run"].astype(str)
        frames.append(df)
        
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


def wecdf(x, w):
    i = np.argsort(x, kind="mergesort")
    x, w = x[i], w[i]
    c = np.cumsum(w)
    return np.r_[x[0], x], np.r_[0.0, c / c[-1]]


def main():
    if GROUP_BY not in ("op", "op_rat"):
        sys.exit('GROUP_BY must be "op" or "op_rat"')
    if WEIGHT not in ("record", "run"):
        sys.exit('WEIGHT must be "record" or "run"')

    # Loop through each location and date independently
    for loc in LOCATIONS:
        for date in DATES:
            print(f"\n--- Processing Location: {loc} | Date: {date} ---")
            df = load(target_loc=loc, target_date=date)
            
            if df is None or df.empty:
                print(f"[!] No data found for {loc} on {date}, skipped.")
                continue

            # Map columns accurately to match your file schema
            df["line"] = df["op"] if GROUP_BY == "op" else df["op"] + " " + df["radio_connection"]

            # Weights: plain, or each run contributes equally within its line
            if WEIGHT == "record":
                df["w"] = 1.0
            else:
                df["w"] = 1.0 / df.groupby(["direction", "line", "run_id"])["Resource blocks"].transform("size")

            # Summary table
            summ = (df.groupby(["direction", "line"])
                      .agg(runs=("run_id", "nunique"), records=("Resource blocks", "size"),
                           median_rb=("Resource blocks", "median"),
                           p90_rb=("Resource blocks", lambda s: s.quantile(0.9)))
                      .round(1))
            print(summ.to_string())
            
            if GROUP_BY == "op":
                print("\nShare of records by Connection Type (per operator):")
                print((df.groupby(["direction", "op"])["radio_connection"]
                         .value_counts(normalize=True).unstack(fill_value=0) * 100)
                      .round(1).to_string())

            dirs = [d for d in DIRECTIONS if d in df["direction"].unique()]
            lines = sorted(df["line"].unique())
            colors = {l: plt.cm.tab10(i % 10) for i, l in enumerate(lines)}

            fig, axes = plt.subplots(1, len(dirs), figsize=(5.5 * len(dirs), 4), squeeze=False)
            for ax, d in zip(axes[0], dirs):
                sub = df[df["direction"] == d]
                for l, g in sub.groupby("line"):
                    x, F = wecdf(g["Resource blocks"].to_numpy(), g["w"].to_numpy())
                    ax.step(x, F, where="post", lw=1.8, color=colors[l],
                            label=f"{l} ({g['run_id'].nunique()} runs)")
                ax.set_title(d.capitalize())
                ax.set_xlabel("Resource blocks per record (4G RB / 5G PRB)")
                ax.set_ylabel("CDF")
                ax.set_ylim(0, 1)
                if LOG_X:
                    ax.set_xscale("log")
                ax.grid(alpha=0.3)
                ax.legend(fontsize=8)
                
            fig.suptitle(f"RB CDF ({loc} - {date}), weight = {WEIGHT}", fontsize=10)
            fig.tight_layout()
            
            # Set dynamic output path for each location and date
            if USE_SPEEDTEST:
                out_path = f"graphs/speedtest/Granularity_Ratio_plots/1000ms/{loc}/{date}_rb_cdf_combined.png"
            else:
                out_path = f"graphs/dummyVC/Granularity_Ratio_plots/1000ms/{loc}/{date}_rb_cdf_combined.png"

            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            fig.savefig(out_path, dpi=200)
            plt.close(fig)  # Close figure to free memory across iterations
            print(f"[✓] Saved figure to {out_path}")


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
        "--use_speedtest",
        action="store_true",
        help="Enable speedtest processing",
    )
    args = parser.parse_args()
    
    LOCATIONS = args.locations
    DATES = args.dates
    USE_SPEEDTEST = args.use_speedtest

    if USE_SPEEDTEST:
        IN = "results/granular_qmdl_metrics/speedtest"
    else:
        IN = "results/granular_qmdl_metrics/"
        
    main()