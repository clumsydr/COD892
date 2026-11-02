#!/usr/bin/env python3
import csv, math, re
from pathlib import Path
from datetime import datetime

DATA_ROOT = Path("/scratch/5GMeasurements/qmdl_output")
OPERATOR = "Airtel"
OUTPUT_ROOT = Path("/scratch/5GMeasurements/graphs/tb_size_graphs")
NR_UL_NAME = "readable_b881.csv"
NR_DL_NAME = "readable_b887.csv"
LTE_UL_REL = Path("lte/b139_pusch_tx.csv")
LTE_DL_REL = Path("lte/b173_pdsch_stats.csv")
TIME_CANDIDATES = ["timestamp_epoch", "epoch_sec", "timestamp", "time"]

def norm(s):
    return re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_")

def number(v):
    try:
        x = float(str(v).strip().replace(",", ""))
        return x if math.isfinite(x) else None
    except (ValueError, TypeError):
        return None

def read(path):
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as f:
        r = csv.DictReader(f)
        return r.fieldnames or [], list(r)

def find_col(headers, candidates):
    lookup = {norm(h): h for h in headers}
    for c in candidates:
        if norm(c) in lookup:
            return lookup[norm(c)]
    for h in headers:
        hn = norm(h)
        if any(hn.endswith("_" + norm(c)) or hn.startswith(norm(c) + "_") for c in candidates):
            return h
    return None

def time_col(headers):
    return find_col(headers, TIME_CANDIDATES) or next(
        (h for h in headers if "timestamp" in norm(h) or norm(h) in ("epoch", "epoch_seconds")), None)

def find_metric(headers, metric):
    if metric == "new_tx_bytes":
        c = find_col(headers, ["delta_new_tx_bytes", "new_tx_bytes", "delta_new_transmitted_bytes"])
        return (c, "bytes", "bytes_per_interval") if c else (None, None, None)

    # Prefer explicit units. For generic tb_size, the script assumes bytes;
    # verify this against the decoder documentation if its units are unclear.
    c = find_col(headers, ["tb_size_bytes", "tb_size_byte", "transport_block_size_bytes", "tb_size_in_bytes"])
    if c:
        return c, "bytes", "bytes"
    c = find_col(headers, ["tb_size_bits", "tb_size_bit", "transport_block_size_bits", "tb_size_in_bits"])
    if c:
        return c, "bits", "bits"
    c = find_col(headers, ["tb_size", "transport_block_size", "tbsize"])
    if c:
        hn = norm(c)
        if "bit" in hn and "byte" not in hn:
            return c, "bits", "bits"
        return c, "bytes (assumed)", "bytes"
    return None, None, None

def locate(operator_dir, filename):
    matches = sorted(operator_dir.rglob(filename))
    return matches[0] if matches else None

def main():
    # Use one-second bins and express every panel as estimated Mbps.
    BIN_SECONDS = 1.0
    opdir = DATA_ROOT / OPERATOR
    nrul, nrdl = locate(opdir, NR_UL_NAME), locate(opdir, NR_DL_NAME)
    if not nrul or not nrdl:
        raise SystemExit(f"Could not locate both NR CSVs under {opdir}")
    captures = sorted(p for p in opdir.rglob("capture_*") if p.is_dir())
    capture = next((p for p in captures if (p/LTE_UL_REL).is_file() and (p/LTE_DL_REL).is_file()), None)
    if capture is None:
        raise SystemExit(f"No capture under {opdir} contains both {LTE_UL_REL} and {LTE_DL_REL}")

    sources = [
        ("NR UL", nrul, "new_tx_bytes"),
        ("NR DL", nrdl, "tb"),
        ("LTE UL", capture/LTE_UL_REL, "tb"),
        ("LTE DL", capture/LTE_DL_REL, "tb"),
    ]

    # Store Mbps estimates by integer epoch-second bins.
    series = []
    for label, path, metric in sources:
        headers, rows = read(path)
        tc = time_col(headers)
        vc, source_unit, kind = find_metric(headers, metric)
        if not tc or not vc:
            print(f"[SKIP] {label}: timestamp/metric not found. Columns: {headers}")
            continue

        bins = {}
        valid = 0
        for row in rows:
            t, v = number(row.get(tc)), number(row.get(vc))
            if t is None or v is None:
                continue
            tn = norm(tc)
            if tn.endswith("_ms"): t /= 1000
            elif tn.endswith("_us"): t /= 1e6
            elif tn.endswith("_ns"): t /= 1e9
            if v < 0:
                continue
            b = math.floor(t / BIN_SECONDS) * BIN_SECONDS
            if kind == "bytes_per_interval":
                # delta_new_tx_bytes is a byte delta over its source interval.
                # Sum interval byte deltas falling in each wall-clock second.
                bins.setdefault(b, []).append(v * 8.0)
            else:
                # Sum TB sizes within each second, then convert bits/bytes to Mbps.
                bits = v if kind == "bits" else v * 8.0
                bins.setdefault(b, []).append(bits)
            valid += 1

        if not bins:
            print(f"[SKIP] {label}: no valid timestamp/value pairs")
            continue

        mbps = {}
        for b, values in bins.items():
            # Both byte deltas and TB sizes are converted to bits and divided by
            # the one-second bin duration, yielding an estimated Mbps value.
            mbps[b] = sum(values) / BIN_SECONDS / 1_000_000.0

        series.append((label, path, vc, source_unit, mbps))
        print(f"[OK] {label}: {path}")
        print(f"     timestamp={tc}; source field={vc}; source unit={source_unit}; valid rows={valid}; plotted bins={len(mbps)}")

    if not series:
        raise SystemExit("No valid series found.")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(len(series), 1, figsize=(15, 3.4*len(series)), sharex=True)
    if len(series) == 1:
        axes = [axes]

    for ax, (label, path, vc, source_unit, binned) in zip(axes, series):
        xs = [datetime.fromtimestamp(t) for t in sorted(binned)]
        ys = [binned[t] for t in sorted(binned)]
        ax.plot(xs, ys, linewidth=0.9)
        ax.set_ylabel("Mbps")
        ax.set_title(f"{label} — {vc}", loc="left", fontsize=10)
        ax.grid(True, alpha=0.3)

    axes[-1].set_xlabel("Time")
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    fig.suptitle(
        f"{OPERATOR}: LTE/NR UL/DL estimated PHY throughput\n"
        "All panels use Mbps in 1-second bins; TB-size panels estimate scheduled PHY volume, not application goodput",
        fontsize=12
    )
    fig.autofmt_xdate()
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    out = OUTPUT_ROOT / f"{OPERATOR.lower()}_lte_nr_ul_dl_tb_metrics.png"
    fig.savefig(out, dpi=180, bbox_inches="tight")
    print(f"\nSaved plot: {out}\nLTE capture selected: {capture}")
    print("Unit note: NR UL delta_new_tx_bytes is summed by timestamp into 1-second bins; TB sizes are also summed per second and converted to Mbps.")
    print("Important: generic 'tb_size' fields are assumed to be bytes. Confirm the decoder's unit if not documented. Confirm delta_new_tx_bytes interval semantics before treating it as a byte rate.")
    print("Interpretation: this is estimated PHY-layer volume/rate, not proof of application payload bytes.")

if __name__ == "__main__":
    main()
