#!/usr/bin/env python3
"""
End-to-end clean rebuild of 1-second cross-layer PHY + Application Throughput datasets
directly from raw uncollapsed parser CSVs (COD892/qmdl_output/) and PCAP throughput CSVs
(COD892/results/Throughput/), fixing all 5 upstream bugs:

  1. No WITHIN_RAT='max' truncation: sums ALL 0xB887 multi-slot/multi-carrier TBs and
     all 0xB173/0xB139 subframes per 1s bin; sums 4G + 5G simultaneously in EN-DC (1 PRB = 168 REs).
  2. 0xB881 (5G UL) uses total PRBs (`delta_num_prb`), NOT `avg_prb_this_interval`.
  3. 0xB173 (4G DL) converts `tb_size_bytes * 8` to bits and accounts for `num_layers` per subframe
     so dual-codeword 2x2 MIMO does not double-count RBs or underestimate code rate by 8x.
  4. 0xB881 (5G UL) uses continuous byte-ratio efficiency:
     `delta_new_tx_bytes / (delta_new_tx_bytes + delta_retx_bytes)` instead of binary `_retx == 0`.
  5. RB-weighted means for intensive metrics (`MIMO`, `Q_m`, `Target Code Rate`) + per-run
     cross-correlation lag alignment fixing Android PCAP vs. Qualcomm QXDM startup clock skew.
"""

import os
import glob
import json
import warnings
import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")

BASE = "/home/anyada/Documents/cod891/COD892"
QMDL_ROOT = os.path.join(BASE, "qmdl_output")
TP_ROOT = os.path.join(BASE, "results", "Throughput")
REG_ROOT = os.path.join(BASE, "regression", "1000ms")
LR_DIR = os.path.join(BASE, "scripts", "LinearRegression")

LOCATIONS = [
    "indoor_AzadApt",
    "indoor_Bharti501",
    "indoor_BlueTokai",
    "indoor_Shubham_JiaSarai",
    "outdoor_Car",
    "outdoor_Ground",
    "outdoor_Rajdhani",
]
OPERATORS = ["Airtel", "Jio", "Vodafone"]

# 3GPP TS 38.214 Table 5.1.3.1-2 (256QAM MCS table): mcs -> (Q_m, R * 1024)
NR_MCS_QM = np.full(32, np.nan)
NR_MCS_TCR = np.full(32, np.nan)
_NR_TABLE = {
    0: (2, 120), 1: (2, 193), 2: (2, 308), 3: (2, 449), 4: (2, 602),
    5: (4, 378), 6: (4, 434), 7: (4, 490), 8: (4, 553), 9: (4, 616), 10: (4, 658),
    11: (6, 466), 12: (6, 517), 13: (6, 567), 14: (6, 616), 15: (6, 666),
    16: (6, 719), 17: (6, 772), 18: (6, 822), 19: (6, 873),
    20: (8, 682.5), 21: (8, 711), 22: (8, 754), 23: (8, 797), 24: (8, 841),
    25: (8, 885), 26: (8, 916.5), 27: (8, 948),
    28: (2, np.nan), 29: (4, np.nan), 30: (6, np.nan), 31: (8, np.nan),
}
for k, (q, r) in _NR_TABLE.items():
    NR_MCS_QM[k] = q
    NR_MCS_TCR[k] = r

LTE_MOD_MAP = {
    "BPSK": 1.0, "QPSK": 2.0, "16QAM": 4.0, "16-QAM": 4.0,
    "64QAM": 6.0, "64-QAM": 6.0, "256QAM": 8.0, "256-QAM": 8.0,
}


def find_csv(folder, candidates):
    for rel in candidates:
        p = os.path.join(folder, rel)
        if os.path.exists(p) and os.path.getsize(p) > 80:
            return p
    return None


def load_b887(folder):
    """5G NR DL (per-slot/TB). Returns columns: t, rb, rb_new, mimo, qm, tcr, tb_bytes, rat."""
    p = find_csv(folder, ["payloads_b887.csv", "readable_b887.csv"])
    if not p:
        return None
    try:
        df = pd.read_csv(p, usecols=["timestamp_epoch", "tb_size_bytes", "mcs", "num_rbs", "rv", "num_layers"])
    except Exception:
        return None
    if df.empty:
        return None
    t = pd.to_numeric(df["timestamp_epoch"], errors="coerce").values
    rb = pd.to_numeric(df["num_rbs"], errors="coerce").values
    mcs = pd.to_numeric(df["mcs"], errors="coerce").values
    rv = pd.to_numeric(df["rv"], errors="coerce").fillna(0).values
    mimo = pd.to_numeric(df["num_layers"], errors="coerce").fillna(1.0).clip(1.0, 4.0).values
    tb = pd.to_numeric(df["tb_size_bytes"], errors="coerce").fillna(0.0).values

    valid = np.isfinite(t) & np.isfinite(rb) & (rb > 0)
    if not valid.any():
        return None
    t, rb, mcs, rv, mimo, tb = t[valid], rb[valid], mcs[valid], rv[valid], mimo[valid], tb[valid]
    mcs_idx = np.clip(np.where(np.isfinite(mcs), np.rint(mcs), -1).astype(int), -1, 31)
    qm = np.where(mcs_idx >= 0, NR_MCS_QM[np.maximum(mcs_idx, 0)], np.nan)
    tcr = np.where(mcs_idx >= 0, NR_MCS_TCR[np.maximum(mcs_idx, 0)], np.nan)
    # New transmission = rv == 0 and mcs < 28
    is_new = (rv == 0) & (mcs_idx < 28)
    rb_new = np.where(is_new, rb, 0.0)
    return pd.DataFrame({
        "t": t, "rb": rb, "rb_new": rb_new, "mimo": mimo, "qm": qm, "tcr": tcr, "tb_bytes": tb, "is_5g": 1
    })


def load_b173(folder):
    """4G LTE DL (per-subframe/TB). Collapses dual-codeword 2x2 MIMO per (timestamp, frame, subframe)
    so RBs are not double-counted when 2 codewords share the same subframe RBs."""
    p = find_csv(folder, ["payloads_b173.csv", "lte/b173_pdsch_stats.csv"])
    if not p:
        return None
    try:
        hdr = pd.read_csv(p, nrows=0).columns.tolist()
        ts_col = "timestamp_epoch" if "timestamp_epoch" in hdr else ("epoch_sec" if "epoch_sec" in hdr else None)
        if ts_col is None:
            return None
        want = [c for c in [ts_col, "frame", "frame_num", "subframe", "subframe_num", "num_rbs_subframe", "num_layers",
                            "num_tbs_present", "rv", "rnti_type", "tb_size_bytes", "modulation", "tb_rbs"] if c in hdr]
        df = pd.read_csv(p, usecols=want)
    except Exception:
        return None
    if df.empty:
        return None
    if "rnti_type" in df.columns:
        c_mask = df["rnti_type"].astype(str).str.upper().str.contains("C-RNTI", na=False)
        if c_mask.any():
            df = df[c_mask]
    if df.empty:
        return None

    df["t"] = pd.to_numeric(df[ts_col], errors="coerce")
    df["tb_b"] = pd.to_numeric(df["tb_size_bytes"], errors="coerce").fillna(0.0)
    df["rv"] = pd.to_numeric(df["rv"], errors="coerce").fillna(0.0)
    df["mimo"] = pd.to_numeric(df["num_layers"], errors="coerce").fillna(1.0).clip(1.0, 4.0)
    rb_col = "tb_rbs" if "tb_rbs" in df.columns else "num_rbs_subframe"
    df["rb_raw"] = pd.to_numeric(df[rb_col], errors="coerce")
    df["qm"] = df["modulation"].astype(str).str.strip().str.upper().str.replace("-", "", regex=False).map(LTE_MOD_MAP)
    df = df.dropna(subset=["t", "rb_raw", "qm"])
    df = df[df["rb_raw"] > 0]
    if df.empty:
        return None

    # Divide per-TB RB by number of TBs in that subframe when dual-codeword MIMO shares the same RBs
    if "num_tbs_present" in df.columns:
        ntbs = pd.to_numeric(df["num_tbs_present"], errors="coerce").fillna(1.0).clip(1.0, 2.0).values
    else:
        ntbs = np.ones(len(df))
    rb_eff = df["rb_raw"].values / ntbs
    # Effective layers per TB row = mimo / ntbs (so sum(rb_eff) = subframe RB, RB-weighted mean(mimo) = subframe mimo!)
    mimo_per_tb = np.maximum(1.0, df["mimo"].values / ntbs)
    # 4G DL code rate in bits/(168 * rb * qm * layers_per_tb) * 1024  [FIXED: tb_size_bytes * 8!]
    bits = df["tb_b"].values * 8.0 + 24.0
    denom = 156.0 * df["rb_raw"].values * df["qm"].values * mimo_per_tb
    tcr = np.where(denom > 0, (bits / denom) * 1024.0, np.nan)
    tcr = np.clip(tcr, 50.0, 960.0)
    rb_new = np.where(df["rv"].values == 0, rb_eff, 0.0)
    return pd.DataFrame({
        "t": df["t"].values, "rb": rb_eff, "rb_new": rb_new,
        "mimo": df["mimo"].values, "qm": df["qm"].values, "tcr": tcr,
        "tb_bytes": df["tb_b"].values, "is_5g": 0
    })


def load_b881(folder):
    """5G NR UL (per-interval stats). Uses delta_num_prb (NOT avg_prb) and continuous byte-ratio efficiency."""
    p = find_csv(folder, ["payloads_b881.csv", "readable_b881.csv"])
    if not p:
        return None
    try:
        df = pd.read_csv(p, usecols=[
            "timestamp_epoch", "delta_new_tx_bytes", "delta_retx_bytes",
            "delta_num_prb", "avg_mcs_this_interval"
        ])
    except Exception:
        return None
    if df.empty:
        return None
    t = pd.to_numeric(df["timestamp_epoch"], errors="coerce").values
    rb = pd.to_numeric(df["delta_num_prb"], errors="coerce").values
    new_b = pd.to_numeric(df["delta_new_tx_bytes"], errors="coerce").fillna(0.0).values
    retx_b = pd.to_numeric(df["delta_retx_bytes"], errors="coerce").fillna(0.0).values
    mcs = pd.to_numeric(df["avg_mcs_this_interval"], errors="coerce").values

    valid = np.isfinite(t) & np.isfinite(rb) & (rb > 0) & (rb < 500000) & ((new_b + retx_b) > 0)
    if not valid.any():
        return None
    t, rb, new_b, retx_b, mcs = t[valid], rb[valid], new_b[valid], retx_b[valid], mcs[valid]

    mcs_idx = np.clip(np.where(np.isfinite(mcs), np.rint(mcs), -1).astype(int), -1, 31)
    qm = np.where(mcs_idx >= 0, NR_MCS_QM[np.maximum(mcs_idx, 0)], np.nan)
    tcr = np.where(mcs_idx >= 0, NR_MCS_TCR[np.maximum(mcs_idx, 0)], np.nan)
    # Continuous byte-ratio efficiency!
    eff = new_b / np.maximum(new_b + retx_b, 1.0)
    rb_new = rb * eff
    return pd.DataFrame({
        "t": t, "rb": rb, "rb_new": rb_new, "mimo": np.ones(len(t)),
        "qm": qm, "tcr": tcr, "tb_bytes": new_b, "is_5g": 1
    })


def load_b139(folder):
    """4G LTE UL (per-subframe PUSCH grant)."""
    p = find_csv(folder, ["payloads_b139.csv", "lte/b139_pusch_tx.csv"])
    if not p:
        return None
    try:
        hdr = pd.read_csv(p, nrows=0).columns.tolist()
        ts_col = "timestamp_epoch" if "timestamp_epoch" in hdr else ("epoch_sec" if "epoch_sec" in hdr else None)
        if ts_col is None:
            return None
        want = [c for c in [ts_col, "num_rb", "coding_rate", "modulation", "tb_size_bytes", "is_retx", "rv"] if c in hdr]
        df = pd.read_csv(p, usecols=want)
    except Exception:
        return None
    if df.empty:
        return None
    t = pd.to_numeric(df[ts_col], errors="coerce").values
    rb = pd.to_numeric(df["num_rb"], errors="coerce").values
    cr = pd.to_numeric(df["coding_rate"], errors="coerce").values
    tb = pd.to_numeric(df["tb_size_bytes"], errors="coerce").fillna(0.0).values
    is_retx = pd.to_numeric(df["is_retx"], errors="coerce").fillna(0.0).values
    qm = df["modulation"].astype(str).str.strip().str.upper().str.replace("-", "", regex=False).map(LTE_MOD_MAP).values

    valid = np.isfinite(t) & np.isfinite(rb) & (rb > 0) & np.isfinite(qm)
    if not valid.any():
        return None
    t, rb, cr, tb, is_retx, qm = t[valid], rb[valid], cr[valid], tb[valid], is_retx[valid], qm[valid]
    tcr = np.where(np.isfinite(cr) & (cr > 0), np.clip(cr * 1024.0, 50.0, 960.0), np.nan)
    rb_new = np.where(is_retx == 0, rb, 0.0)
    return pd.DataFrame({
        "t": t, "rb": rb, "rb_new": rb_new, "mimo": np.ones(len(t)),
        "qm": qm, "tcr": tcr, "tb_bytes": tb, "is_5g": 0
    })


def bin_1s(df_combined, t0):
    """Aggregate combined 4G+5G rows into 1s bins using RB-weighted means and exact RB sums."""
    if df_combined is None or df_combined.empty:
        return pd.DataFrame()
    df = df_combined.copy()
    df["bin"] = np.floor(df["t"].values - t0).astype(np.int64)
    df = df[df["bin"] >= 0]
    if df.empty:
        return pd.DataFrame()

    # Vectorized RB-weighted aggregation
    rb = df["rb"].values
    df["w_mimo"] = rb * df["mimo"].values
    valid_qm = np.isfinite(df["qm"].values)
    df["w_qm"] = np.where(valid_qm, rb * df["qm"].values, 0.0)
    df["rb_qm"] = np.where(valid_qm, rb, 0.0)
    valid_tcr = np.isfinite(df["tcr"].values)
    df["w_tcr"] = np.where(valid_tcr, rb * df["tcr"].values, 0.0)
    df["rb_tcr"] = np.where(valid_tcr, rb, 0.0)
    df["rb_5g"] = rb * df["is_5g"].values

    g = df.groupby("bin", as_index=False).agg(
        t_first=("t", "first"),
        rb_total=("rb", "sum"),
        rb_new=("rb_new", "sum"),
        rb_5g=("rb_5g", "sum"),
        tb_bytes=("tb_bytes", "sum"),
        w_mimo=("w_mimo", "sum"),
        w_qm=("w_qm", "sum"),
        rb_qm=("rb_qm", "sum"),
        w_tcr=("w_tcr", "sum"),
        rb_tcr=("rb_tcr", "sum"),
    )
    g["MIMO"] = g["w_mimo"] / g["rb_total"]
    g["Q_m"] = np.where(g["rb_qm"] > 0, g["w_qm"] / g["rb_qm"], np.nan)
    g["Target Code Rate"] = np.where(g["rb_tcr"] > 0, g["w_tcr"] / g["rb_tcr"], np.nan)
    g["Resource Blocks"] = g["rb_total"]
    g["Efficiency"] = np.clip(g["rb_new"] / g["rb_total"], 0.0, 1.0)
    g["PHY_Mbps"] = g["tb_bytes"] * 8.0 / 1e6
    g["Frac_5G"] = g["rb_5g"] / g["rb_total"]
    return g[["bin", "t_first", "MIMO", "Q_m", "Target Code Rate", "Resource Blocks", "Efficiency", "PHY_Mbps", "Frac_5G"]]


def align_and_merge_run(dl_bins, ul_bins, tp_df, max_lag=8):
    """Find ONE shared integer lag per run maximizing combined DL+UL correlation between
    PHY_Mbps (exact decoded PHY rate) and PCAP Application_Throughput, then merge."""
    n_tp = len(tp_df)
    if n_tp < 4:
        return None, None, 0

    dl_app = pd.to_numeric(tp_df["Download (Mbps)"], errors="coerce").fillna(0.0).values
    ul_app = pd.to_numeric(tp_df["Upload (Mbps)"], errors="coerce").fillna(0.0).values

    # Build dense 1s PHY arrays over [0 .. max_bin]
    max_b = 0
    if not dl_bins.empty:
        max_b = max(max_b, int(dl_bins["bin"].max()))
    if not ul_bins.empty:
        max_b = max(max_b, int(ul_bins["bin"].max()))
    if max_b < 2:
        return None, None, 0

    phy_dl = np.zeros(max_b + 1)
    phy_ul = np.zeros(max_b + 1)
    if not dl_bins.empty:
        phy_dl[dl_bins["bin"].values] = dl_bins["PHY_Mbps"].values
    if not ul_bins.empty:
        phy_ul[ul_bins["bin"].values] = ul_bins["PHY_Mbps"].values

    # Shared lag: app[k] corresponds to phy[k + lag] (so bin_aligned = bin - lag)
    best_lag, best_score = 0, -9.0
    for lag in range(-max_lag, max_lag + 1):
        # Overlapping indices k in app where 0 <= k + lag <= max_b
        k_lo = max(0, -lag)
        k_hi = min(n_tp, max_b + 1 - lag)
        if k_hi - k_lo < 5:
            continue
        p_d = phy_dl[k_lo + lag : k_hi + lag]
        a_d = dl_app[k_lo : k_hi]
        p_u = phy_ul[k_lo + lag : k_hi + lag]
        a_u = ul_app[k_lo : k_hi]
        scores = []
        if np.std(p_d) > 0 and np.std(a_d) > 0:
            scores.append(np.corrcoef(p_d, a_d)[0, 1])
        if np.std(p_u) > 0 and np.std(a_u) > 0:
            scores.append(np.corrcoef(p_u, a_u)[0, 1])
        if scores:
            sc = float(np.mean(scores))
            if sc > best_score:
                best_score, best_lag = sc, lag

    def attach_app(bins_df, app_arr, opp_arr):
        if bins_df.empty:
            return pd.DataFrame()
        out = bins_df.copy()
        out["Aligned_Bin"] = out["bin"] - best_lag
        out = out[(out["Aligned_Bin"] >= 0) & (out["Aligned_Bin"] < n_tp)].copy()
        if out.empty:
            return pd.DataFrame()
        idx = out["Aligned_Bin"].values.astype(int)
        out["Application_Throughput"] = app_arr[idx]
        out["Opposite_Throughput"] = opp_arr[idx]
        return out

    dl_m = attach_app(dl_bins, dl_app, ul_app)
    ul_m = attach_app(ul_bins, ul_app, dl_app)
    return dl_m, ul_m, best_lag


def build_dataset(is_speedtest=True):
    rows_out = []
    n_runs, n_shifted = 0, 0
    for op in OPERATORS:
        for loc in LOCATIONS:
            op_loc_q = os.path.join(QMDL_ROOT, op, loc)
            if not os.path.isdir(op_loc_q):
                continue
            for dt in sorted(os.listdir(op_loc_q)):
                if not dt.startswith("202610"):
                    continue
                q_dt = os.path.join(op_loc_q, dt)
                tp_dt = os.path.join(TP_ROOT, op, loc, dt)
                if not os.path.isdir(tp_dt):
                    continue
                for cap_path in sorted(glob.glob(os.path.join(q_dt, "capture_*"))):
                    run_name = os.path.basename(cap_path)
                    if is_speedtest:
                        st_dirs = glob.glob(os.path.join(cap_path, "speedtest_qmdl_*"))
                        if not st_dirs:
                            continue
                        q_dir = st_dirs[0]
                        tp_files = glob.glob(os.path.join(tp_dt, run_name, "speedtest_qmdl_*", "throughput_1s_speedtest*.csv"))
                    else:
                        q_dir = cap_path
                        tp_files = glob.glob(os.path.join(tp_dt, run_name, "throughput_1s_capture_*.csv"))
                    if not tp_files:
                        continue

                    tp_df = pd.read_csv(tp_files[0])
                    tp_df.columns = [c.strip() for c in tp_df.columns]
                    if "Download (Mbps)" not in tp_df.columns or "Upload (Mbps)" not in tp_df.columns:
                        continue

                    d5 = load_b887(q_dir)
                    d4 = load_b173(q_dir)
                    u5 = load_b881(q_dir)
                    u4 = load_b139(q_dir)
                    dl_parts = [x for x in (d5, d4) if x is not None and not x.empty]
                    ul_parts = [x for x in (u5, u4) if x is not None and not x.empty]
                    if not dl_parts and not ul_parts:
                        continue

                    dl_raw = pd.concat(dl_parts, ignore_index=True) if dl_parts else pd.DataFrame()
                    ul_raw = pd.concat(ul_parts, ignore_index=True) if ul_parts else pd.DataFrame()
                    t_mins = []
                    if not dl_raw.empty:
                        t_mins.append(dl_raw["t"].min())
                    if not ul_raw.empty:
                        t_mins.append(ul_raw["t"].min())
                    t0 = min(t_mins)

                    dl_bins = bin_1s(dl_raw, t0)
                    ul_bins = bin_1s(ul_raw, t0)
                    dl_m, ul_m, lag = align_and_merge_run(dl_bins, ul_bins, tp_df)
                    n_runs += 1
                    if lag != 0:
                        n_shifted += 1

                    for direction, mdf in (("Downlink", dl_m), ("Uplink", ul_m)):
                        if mdf is None or mdf.empty:
                            continue
                        mdf["Location"] = loc
                        mdf["Operator"] = op
                        mdf["Date"] = dt
                        mdf["Run"] = run_name
                        mdf["Direction"] = direction
                        mdf["Lag_Sec"] = lag
                        rows_out.append(mdf)

    full = pd.concat(rows_out, ignore_index=True)
    full["Timestamp"] = pd.to_datetime(full["t_first"], unit="s", utc=True)
    cols = [
        "Location", "Operator", "Date", "Run", "Timestamp", "Aligned_Bin", "Lag_Sec", "Direction",
        "MIMO", "Q_m", "Target Code Rate", "Resource Blocks", "Efficiency",
        "PHY_Mbps", "Frac_5G", "Application_Throughput", "Opposite_Throughput"
    ]
    return full[cols], n_runs, n_shifted


print("=================================================================")
print("STEP 1: Rebuilding clean 1s datasets directly from qmdl_output...")
print("=================================================================")
st_df, st_runs, st_shifted = build_dataset(is_speedtest=True)
st_out = os.path.join(REG_ROOT, "speedtest", "all_data_clean.csv")
st_df.to_csv(st_out, index=False)
print(f"Speedtest: {st_runs} runs ({st_shifted} lag-aligned), {len(st_df)} total 1s rows -> {st_out}")

vc_df, vc_runs, vc_shifted = build_dataset(is_speedtest=False)
vc_out = os.path.join(REG_ROOT, "all_data_clean.csv")
vc_df.to_csv(vc_out, index=False)
print(f"DummyVC:   {vc_runs} runs ({vc_shifted} lag-aligned), {len(vc_df)} total 1s rows -> {vc_out}")


# ==============================================================================
# STEP 2: Run Clean Regression Suite (Pooled Split, Pooled SE, Stratified Active)
# ==============================================================================
print("\n=================================================================")
print("STEP 2: Running 3GPP Log-Linear Regression & Chow Structural Test")
print("=================================================================")

REQ = ["Application_Throughput", "MIMO", "Q_m", "Target Code Rate", "Resource Blocks", "Efficiency"]
st_valid = st_df.dropna(subset=REQ).copy()
st_valid = st_valid[(st_valid[REQ] > 0).all(axis=1)].copy()
st_valid["SpectralEfficiency"] = st_valid["Q_m"] * (st_valid["Target Code Rate"] / 1024.0)

def ols_fit(df_in, feat_cols, loc_fe=False):
    y = np.log(df_in["Application_Throughput"].values)
    Xf = np.column_stack([np.log(df_in[c].values) for c in feat_cols])
    if loc_fe:
        locs = sorted(df_in["Location"].unique())
        Xl = np.column_stack([(df_in["Location"].values == l).astype(float) for l in locs])
        X = np.hstack([Xl, Xf])
        n_int = len(locs)
    else:
        X = np.hstack([np.ones((len(df_in), 1)), Xf])
        n_int = 1
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    yhat = X @ beta
    resid = y - yhat
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot
    n, k = X.shape
    mse = ss_res / max(1, n - k)
    cov = mse * np.linalg.pinv(X.T @ X)
    se = np.sqrt(np.maximum(0, np.diag(cov)))
    t_crit = stats.t.ppf(0.975, df=max(1, n - k))
    # VIF on feature block
    vifs = {}
    X_c = np.hstack([np.ones((len(df_in), 1)), Xf])
    for i, c in enumerate(feat_cols):
        yi = X_c[:, i + 1]
        Xo = np.delete(X_c, i + 1, axis=1)
        b = np.linalg.lstsq(Xo, yi, rcond=None)[0]
        r2_i = 1.0 - np.sum((yi - Xo @ b) ** 2) / max(1e-12, np.sum((yi - yi.mean()) ** 2))
        vifs[c] = 1.0 / (1.0 - r2_i) if r2_i < 0.999999 else np.inf
    weights = {c: float(beta[n_int + i]) for i, c in enumerate(feat_cols)}
    cis = {c: float(t_crit * se[n_int + i]) for i, c in enumerate(feat_cols)}
    return weights, cis, vifs, r2, ss_res, n, k, yhat

# Model A: Pooled 5-feature Split MCS (all valid speedtest bins)
w_sp, ci_sp, vif_sp, r2_sp, ss_sp, n_sp, k_sp, _ = ols_fit(
    st_valid, ["MIMO", "Q_m", "Target Code Rate", "Resource Blocks", "Efficiency"], loc_fe=False
)
print(f"\n[Model 1] Pooled 5-feat Split MCS (n={n_sp}): R2 = {r2_sp:.4f}")
for c in w_sp:
    print(f"   {c:20s}: w={w_sp[c]:+.3f} ± {ci_sp[c]:.3f}  (VIF={vif_sp[c]:.2f})")

# Model B: Pooled 4-feature Combined SE (all valid speedtest bins)
w_cb, ci_cb, vif_cb, r2_cb, ss_cb, n_cb, k_cb, _ = ols_fit(
    st_valid, ["MIMO", "SpectralEfficiency", "Resource Blocks", "Efficiency"], loc_fe=False
)
print(f"\n[Model 2] Pooled 4-feat Combined SE (n={n_cb}): R2 = {r2_cb:.4f}")
for c in w_cb:
    print(f"   {c:20s}: w={w_cb[c]:+.3f} ± {ci_cb[c]:.3f}  (VIF={vif_cb[c]:.2f})")

# Active-phase separation: Active DL = (DL >= UL and App_Tput > 0.5 Mbps or DL >= UL);
# Exclude start/stop/transition boundary bins (first 2s, switch window, last 2s of each run)
is_act_dl = (st_valid["Direction"] == "Downlink") & (st_valid["Application_Throughput"] >= st_valid["Opposite_Throughput"]) & (st_valid["Application_Throughput"] >= 0.05)
is_act_ul = (st_valid["Direction"] == "Uplink") & (st_valid["Application_Throughput"] > st_valid["Opposite_Throughput"]) & (st_valid["Application_Throughput"] >= 0.05)
st_act = st_valid[is_act_dl | is_act_ul].copy()

# Within each (Run, Direction) active phase, drop the very first and very last active second (TCP ramp-up / teardown)
st_act["act_pos"] = st_act.groupby(["Location", "Operator", "Date", "Run", "Direction"]).cumcount()
st_act["act_len"] = st_act.groupby(["Location", "Operator", "Date", "Run", "Direction"])["act_pos"].transform("max") + 1
st_steady = st_act[(st_act["act_pos"] >= 1) & (st_act["act_pos"] <= st_act["act_len"] - 2)].copy()

# Chow F-test on st_steady: pooled 4-feat vs 6 stratified (Op x Dir) models (no loc_fe for clean F-test)
_, _, _, r2_pool_st, ss_pool, n_tot, k_pool, _ = ols_fit(
    st_steady, ["MIMO", "SpectralEfficiency", "Resource Blocks", "Efficiency"], loc_fe=False
)
ss_unres = 0.0
k_unres = 0
print(f"\n[Model 3A] Stratified Operator x Direction Active-Phase (NO loc FE, n={len(st_steady)}):")
yt_no, yp_no = [], []
for op in ["Jio", "Airtel", "Vodafone"]:
    for d in ["Downlink", "Uplink"]:
        sub = st_steady[(st_steady["Operator"] == op) & (st_steady["Direction"] == d)]
        fcols = ["MIMO", "SpectralEfficiency", "Resource Blocks", "Efficiency"] if d == "Downlink" else ["SpectralEfficiency", "Resource Blocks", "Efficiency"]
        w, ci, vif, r2, ssr, ng, kg, yh = ols_fit(sub, fcols, loc_fe=False)
        ss_unres += ssr; k_unres += kg
        yt_no.append(np.log(sub["Application_Throughput"].values)); yp_no.append(yh)
        wm = w.get("MIMO", 0.0)
        print(f"   {op:8s} {d:8s} (n={ng:4d}): R2={r2:.3f} | MIMO={wm:+.2f}, SE={w['SpectralEfficiency']:+.2f}, RB={w['Resource Blocks']:+.2f}, Eff={w['Efficiency']:+.2f}")
yt_no, yp_no = np.concatenate(yt_no), np.concatenate(yp_no)
r2_no_all = 1.0 - np.sum((yt_no - yp_no) ** 2) / np.sum((yt_no - yt_no.mean()) ** 2)
df_num = k_unres - k_pool
df_den = n_tot - k_unres
chow_f = ((ss_pool - ss_unres) / df_num) / (ss_unres / df_den)
chow_p = 1.0 - stats.f.cdf(chow_f, df_num, df_den)
print(f"   OVERALL (no loc FE): R2={r2_no_all:.4f}, r={np.corrcoef(yt_no, yp_no)[0,1]:.4f} | Pooled R2={r2_pool_st:.4f} | Chow F={chow_f:.2f}, p={chow_p:.2e}")

print(f"\n[Model 3B] Stratified Operator x Direction Active-Phase (WITH Location FE, n={len(st_steady)}):")
strat_rows = []
yt_fe, yp_fe = [], []
for op in ["Jio", "Airtel", "Vodafone"]:
    for d in ["Downlink", "Uplink"]:
        sub = st_steady[(st_steady["Operator"] == op) & (st_steady["Direction"] == d)]
        fcols = ["MIMO", "SpectralEfficiency", "Resource Blocks", "Efficiency"] if d == "Downlink" else ["SpectralEfficiency", "Resource Blocks", "Efficiency"]
        w, ci, vif, r2, ssr, ng, kg, yh = ols_fit(sub, fcols, loc_fe=True)
        yt_fe.append(np.log(sub["Application_Throughput"].values)); yp_fe.append(yh)
        wm = w.get("MIMO", 0.0)
        cim = ci.get("MIMO", 0.0)
        print(f"   {op:8s} {d:8s} (n={ng:4d}): R2={r2:.3f} | MIMO={wm:+.2f}±{cim:.2f}, SE={w['SpectralEfficiency']:+.2f}±{ci['SpectralEfficiency']:.2f}, RB={w['Resource Blocks']:+.2f}±{ci['Resource Blocks']:.2f}, Eff={w['Efficiency']:+.2f}±{ci['Efficiency']:.2f}")
        strat_rows.append({
            "Operator": op, "Direction": d, "n": ng, "R2": r2,
            "w_MIMO": wm, "ci_MIMO": cim,
            "w_SE": w["SpectralEfficiency"], "ci_SE": ci["SpectralEfficiency"],
            "w_RB": w["Resource Blocks"], "ci_RB": ci["Resource Blocks"],
            "w_Eff": w["Efficiency"], "ci_Eff": ci["Efficiency"],
        })

yt_fe, yp_fe = np.concatenate(yt_fe), np.concatenate(yp_fe)
r2_fe_all = 1.0 - np.sum((yt_fe - yp_fe) ** 2) / np.sum((yt_fe - yt_fe.mean()) ** 2)
r_fe_all = np.corrcoef(yt_fe, yp_fe)[0, 1]
print(f"   OVERALL (with loc FE): R2={r2_fe_all:.4f}, Pearson r={r_fe_all:.4f}")

# Also check DummyVC R2
vc_valid = vc_df.dropna(subset=REQ).copy()
vc_valid = vc_valid[(vc_valid[REQ] > 0).all(axis=1)].copy()
vc_valid["SpectralEfficiency"] = vc_valid["Q_m"] * (vc_valid["Target Code Rate"] / 1024.0)
_, _, _, r2_vc, _, n_vc, _, _ = ols_fit(vc_valid, ["MIMO", "SpectralEfficiency", "Resource Blocks", "Efficiency"], loc_fe=False)
print(f"\n[DummyVC Check] Pooled 4-feat (n={n_vc}): R2 = {r2_vc:.4f}")

pd.DataFrame(strat_rows).to_csv(os.path.join(LR_DIR, "regression_weights_stratified_clean.csv"), index=False)
print("\nSaved regression_weights_stratified_clean.csv")
