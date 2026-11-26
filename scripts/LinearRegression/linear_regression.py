#!/usr/bin/env python3
"""
Clean Stratified 3GPP Log-Linear Regression & Active-Phase Deficit Decomposition
(Ceiling-Anchored Linear SHAP) on rebuilt 1-second datasets (`all_data_clean.csv`).

Outputs:
  - COD892/scripts/LinearRegression/regression_results.png          (3-panel stratified OLS)
  - COD892/scripts/LinearRegression/deficit_decomposition_results.png (2-panel deficit timeline + regimes)
  - COD892/scripts/LinearRegression/regression_weights.csv          (pooled 4-feature clean weights)
  - COD892/scripts/LinearRegression/regression_weights_split.csv    (pooled 5-feature split MCS weights)
  - COD892/scripts/LinearRegression/regression_weights_stratified_clean.csv
  - COD892/scripts/LinearRegression/deficit_summary_clean.csv
  - Also copies fig4_regression_stratified.png & fig5_deficit_decomposition.png to presentation figs dir.
"""

import os
import shutil
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
from scipy import stats

warnings.filterwarnings("ignore")

BASE = "/home/anyada/Documents/cod891/COD892"
LR_DIR = os.path.join(BASE, "scripts", "LinearRegression")
ST_CSV = os.path.join(BASE, "regression", "1000ms", "speedtest", "all_data_clean.csv")
VC_CSV = os.path.join(BASE, "regression", "1000ms", "all_data_clean.csv")
PRES_FIGS = "/home/anyada/.gemini/antigravity-cli/brain/52f47cde-ddd7-4587-9b64-593c06f902d1/scratch/figs"
os.makedirs(PRES_FIGS, exist_ok=True)

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Liberation Sans", "Arial"],
    "font.size": 10.5,
    "axes.titlesize": 11.5,
    "axes.titleweight": "bold",
    "axes.labelsize": 10.5,
    "axes.labelweight": "bold",
    "axes.edgecolor": "#CBD5E1",
    "axes.linewidth": 0.9,
    "xtick.color": "#1E293B",
    "ytick.color": "#1E293B",
    "text.color": "#0F172A",
    "figure.facecolor": "white",
    "axes.facecolor": "#FFFFFF",
    "grid.color": "#E2E8F0",
    "grid.linestyle": "--",
    "grid.linewidth": 0.6,
    "legend.frameon": True,
    "legend.facecolor": "white",
    "legend.edgecolor": "#CBD5E1",
})

OP_COLORS = {"Jio": "#1D4ED8", "Airtel": "#DC2626", "Vodafone": "#D97706"}
OPS = ["Jio", "Airtel", "Vodafone"]
TARGET = "Application_Throughput"
REQ = [TARGET, "MIMO", "Q_m", "Target Code Rate", "Resource Blocks", "Efficiency"]

# 1. Load clean rebuilt datasets
st = pd.read_csv(ST_CSV)
st = st.dropna(subset=REQ).copy()
st = st[(st[REQ] > 0).all(axis=1)].copy()
st["SpectralEfficiency"] = st["Q_m"] * (st["Target Code Rate"] / 1024.0)

vc = pd.read_csv(VC_CSV)
vc = vc.dropna(subset=REQ).copy()
vc = vc[(vc[REQ] > 0).all(axis=1)].copy()
vc["SpectralEfficiency"] = vc["Q_m"] * (vc["Target Code Rate"] / 1024.0)


def fit_ols(df_in, feat_cols, loc_fe=False):
    y = np.log(df_in[TARGET].values)
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
    dof = max(1, n - k)
    mse = ss_res / dof
    cov = mse * np.linalg.pinv(X.T @ X)
    se = np.sqrt(np.maximum(0, np.diag(cov)))
    t_crit = stats.t.ppf(0.975, df=dof)
    t_vals = beta / np.maximum(se, 1e-12)
    p_vals = 2.0 * (1.0 - stats.t.cdf(np.abs(t_vals), df=dof))
    # VIF
    Xc = np.hstack([np.ones((len(df_in), 1)), Xf])
    vifs = {}
    for i, c in enumerate(feat_cols):
        yi = Xc[:, i + 1]
        Xo = np.delete(Xc, i + 1, axis=1)
        b = np.linalg.lstsq(Xo, yi, rcond=None)[0]
        r2_i = 1.0 - np.sum((yi - Xo @ b) ** 2) / max(1e-12, np.sum((yi - yi.mean()) ** 2))
        vifs[c] = 1.0 / (1.0 - r2_i) if r2_i < 0.999999 else np.inf
    summary = []
    for i, c in enumerate(feat_cols):
        bi = n_int + i
        summary.append({
            "feature": c, "weight": float(beta[bi]),
            "ci_low": float(beta[bi] - t_crit * se[bi]),
            "ci_high": float(beta[bi] + t_crit * se[bi]),
            "ci_half": float(t_crit * se[bi]),
            "p_value": float(p_vals[bi]), "vif": float(vifs[c]),
        })
    return pd.DataFrame(summary).set_index("feature"), r2, yhat, ss_res, n, k


# Active steady-state phase for Speedtest (used consistently for BOTH pooled & stratified models)
is_act_dl = (st["Direction"] == "Downlink") & (st[TARGET] >= st["Opposite_Throughput"]) & (st[TARGET] >= 0.05)
is_act_ul = (st["Direction"] == "Uplink") & (st[TARGET] > st["Opposite_Throughput"]) & (st[TARGET] >= 0.05)
st_act = st[is_act_dl | is_act_ul].copy()
st_act["act_pos"] = st_act.groupby(["Location", "Operator", "Date", "Run", "Direction"]).cumcount()
st_act["act_len"] = st_act.groupby(["Location", "Operator", "Date", "Run", "Direction"])["act_pos"].transform("max") + 1
st_steady = st_act[(st_act["act_pos"] >= 1) & (st_act["act_pos"] <= st_act["act_len"] - 2)].copy()

# Pooled models saved on exact same active steady-state rows (n = 5,163)
sum_comb, r2_comb, _, _, _, _ = fit_ols(st_steady, ["MIMO", "SpectralEfficiency", "Resource Blocks", "Efficiency"], loc_fe=False)
sum_split, r2_split, _, _, _, _ = fit_ols(st_steady, ["MIMO", "Q_m", "Target Code Rate", "Resource Blocks", "Efficiency"], loc_fe=False)
sum_comb.to_csv(os.path.join(LR_DIR, "regression_weights.csv"))
sum_split.to_csv(os.path.join(LR_DIR, "regression_weights_split.csv"))

# Stratified Operator x Direction OLS with Location Fixed Effects
reg_models = {}
pred_parts = []
all_yt, all_yp = [], []
strat_rows = []
for op in OPS:
    for d in ["Downlink", "Uplink"]:
        sub = st_steady[(st_steady["Operator"] == op) & (st_steady["Direction"] == d)].copy()
        fcols = ["MIMO", "SpectralEfficiency", "Resource Blocks", "Efficiency"] if d == "Downlink" else ["SpectralEfficiency", "Resource Blocks", "Efficiency"]
        sdf, r2, yhat, _, ng, _ = fit_ols(sub, fcols, loc_fe=True)
        w_dict = {"MIMO": 0.0}
        ci_dict = {"MIMO": 0.0}
        for fname, row in sdf.iterrows():
            key = "ResourceBlocks" if fname == "Resource Blocks" else fname
            w_dict[key] = row["weight"]
            ci_dict[key] = row["ci_half"]
        reg_models[(op, d)] = {"w": w_dict, "ci": ci_dict, "r2": r2, "n": ng}
        all_yt.append(np.log(sub[TARGET].values))
        all_yp.append(yhat)
        pred_parts.append(pd.DataFrame({"Operator": op, "Direction": d, "Actual": sub[TARGET].values, "Pred": np.exp(yhat)}))
        strat_rows.append({
            "Operator": op, "Direction": d, "n": ng, "R2": round(r2, 4),
            "w_MIMO": round(w_dict["MIMO"], 3), "ci_MIMO": round(ci_dict["MIMO"], 3),
            "w_SE": round(w_dict["SpectralEfficiency"], 3), "ci_SE": round(ci_dict["SpectralEfficiency"], 3),
            "w_RB": round(w_dict["ResourceBlocks"], 3), "ci_RB": round(ci_dict["ResourceBlocks"], 3),
            "w_Eff": round(w_dict["Efficiency"], 3), "ci_Eff": round(ci_dict["Efficiency"], 3),
        })

yt_all = np.concatenate(all_yt)
yp_all = np.concatenate(all_yp)
r2_overall = 1.0 - np.sum((yt_all - yp_all) ** 2) / np.sum((yt_all - yt_all.mean()) ** 2)
r_overall = np.corrcoef(yt_all, yp_all)[0, 1]
pred_df = pd.concat(pred_parts, ignore_index=True)
pd.DataFrame(strat_rows).to_csv(os.path.join(LR_DIR, "regression_weights_stratified_clean.csv"), index=False)
print(f"Stratified Active-Phase Overall: n={len(st_steady)}, R^2={r2_overall:.4f}, r={r_overall:.4f}")

# ==============================================================================
# FIGURE 4: 3-Panel Stratified Regression Results
# ==============================================================================
fig, (ax0, ax1, ax2) = plt.subplots(1, 3, figsize=(13.4, 4.4), dpi=300)
markers = {"Downlink": "o", "Uplink": "^"}

for op in OPS:
    for d in ["Downlink", "Uplink"]:
        sub = pred_df[(pred_df["Operator"] == op) & (pred_df["Direction"] == d)]
        r2_g = reg_models[(op, d)]["r2"]
        sd = "DL" if d == "Downlink" else "UL"
        ax0.scatter(sub["Actual"], sub["Pred"], s=8, alpha=0.35, color=OP_COLORS[op],
                    marker=markers[d], edgecolors="none", label=f"{op} {sd} (R²={r2_g:.2f})")

lim = [5e-2, 1e3]
ax0.plot(lim, lim, "k--", lw=1.4, label="Perfect fit (y = x)")
ax0.set_xscale("log"); ax0.set_yscale("log")
ax0.set_xlim(lim); ax0.set_ylim(lim)
ax0.set_xlabel("Actual Application Throughput (Mbps)")
ax0.set_ylabel("Predicted Throughput (Mbps)")
ax0.set_title(f"A. Predicted vs. Actual (R² = {r2_overall:.2f}, r = {r_overall:.2f})", fontsize=11)
ax0.grid(True, which="major")
ax0.legend(loc="upper left", fontsize=7.5, markerscale=1.6, framealpha=0.93)
ax0.spines["top"].set_visible(False); ax0.spines["right"].set_visible(False)

feat_order = ["MIMO", "SpectralEfficiency", "ResourceBlocks", "Efficiency"]
feat_labels = ["MIMO Layers", "Spectral Eff.\n(MCS)", "Resource\nBlocks", "Efficiency\n(1 - Retx)"]
y_pos = np.arange(len(feat_order))
bar_h = 0.25
op_off = {"Jio": -bar_h, "Airtel": 0.0, "Vodafone": bar_h}

for ax, d, ptitle, xlim in [
    (ax1, "Downlink", "B. Active Downlink Elasticities by Operator", (-0.3, 3.05)),
    (ax2, "Uplink", "C. Active Uplink Elasticities by Operator (SISO)", (-1.85, 1.75)),
]:
    for op in OPS:
        m = reg_models[(op, d)]
        vals = [m["w"][f] for f in feat_order]
        errs = [m["ci"][f] for f in feat_order]
        ys = y_pos + op_off[op]
        ax.barh(ys, vals, height=bar_h, xerr=errs, capsize=2.5,
                color=OP_COLORS[op], alpha=0.86, edgecolor="#1E293B", linewidth=0.5)
        for yv, val, err in zip(ys, vals, errs):
            if d == "Uplink" and abs(val) < 1e-6:
                continue
            x_txt = val + err + 0.06 if val >= 0 else val - err - 0.06
            ha = "left" if val >= 0 else "right"
            ax.text(x_txt, yv, f"{val:+.2f}", va="center", ha=ha, fontsize=7.8, fontweight="bold", color=OP_COLORS[op])
    if d == "Uplink":
        ax.text(0.08, 0.0, "UL = SISO (MIMO = 1)", va="center", ha="left", fontsize=8.5, style="italic", color="#475569",
                bbox=dict(boxstyle="round,pad=0.25", fc="#F8FAFC", ec="#CBD5E1"))
    ax.axvline(1.0, color="#DC2626", ls="--", lw=1.4)
    ax.axvline(0.0, color="#334155", lw=0.8)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(feat_labels, fontsize=9, fontweight="bold")
    ax.set_xlim(*xlim)
    ax.set_xlabel("Regression Elasticity (w)")
    ax.set_title(ptitle, fontsize=11)
    ax.grid(axis="x")
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)

handles_reg = [
    Patch(facecolor=OP_COLORS["Jio"], edgecolor="#1E293B", alpha=0.86,
          label=f"Jio 5G SA (DL R²={reg_models[('Jio','Downlink')]['r2']:.2f}, UL R²={reg_models[('Jio','Uplink')]['r2']:.2f})"),
    Patch(facecolor=OP_COLORS["Airtel"], edgecolor="#1E293B", alpha=0.86,
          label=f"Airtel 5G NSA (DL R²={reg_models[('Airtel','Downlink')]['r2']:.2f}, UL R²={reg_models[('Airtel','Uplink')]['r2']:.2f})"),
    Patch(facecolor=OP_COLORS["Vodafone"], edgecolor="#1E293B", alpha=0.86,
          label=f"Vodafone NSA/4G (DL R²={reg_models[('Vodafone','Downlink')]['r2']:.2f}, UL R²={reg_models[('Vodafone','Uplink')]['r2']:.2f})"),
    Line2D([0], [0], color="#DC2626", ls="--", lw=1.6, label="3GPP theoretical law (w = 1)"),
]
fig.legend(handles=handles_reg, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.05), fontsize=8.3, frameon=True)
plt.tight_layout(rect=[0, 0.04, 1, 1], w_pad=1.6)
fig4_path = os.path.join(LR_DIR, "regression_results.png")
plt.savefig(fig4_path, dpi=300, bbox_inches="tight")
shutil.copyfile(fig4_path, os.path.join(PRES_FIGS, "fig4_regression_stratified.png"))
plt.close(fig)

# ==============================================================================
# FIGURE 5: Active-Phase Log-Linear Deficit Decomposition (Clean Data)
# ==============================================================================
ceilings = {}
for op in OPS:
    for d in ["Downlink", "Uplink"]:
        sub = st_steady[(st_steady["Operator"] == op) & (st_steady["Direction"] == d)]
        ceilings[(op, d)] = {
            "MIMO": float(np.percentile(sub["MIMO"], 99)),
            "SpectralEfficiency": float(np.percentile(sub["SpectralEfficiency"], 99)),
            "ResourceBlocks": float(np.percentile(sub["Resource Blocks"], 99)),
            "Efficiency": float(np.percentile(sub["Efficiency"], 99)),
        }


def compute_deficits(df_in):
    out = df_in.copy()
    for fn, col in [("MIMO", "MIMO"), ("SpectralEfficiency", "SpectralEfficiency"),
                    ("ResourceBlocks", "Resource Blocks"), ("Efficiency", "Efficiency")]:
        vals = np.zeros(len(out))
        for (op, d), idx in out.groupby(["Operator", "Direction"]).groups.items():
            w_k = max(0.0, reg_models[(op, d)]["w"][fn]) if fn != "Efficiency" else abs(reg_models[(op, d)]["w"][fn])
            if d == "Uplink" and fn == "MIMO":
                w_k = 0.0
            c_k = ceilings[(op, d)][fn]
            ratio = np.minimum(out.loc[idx, col].values / max(c_k, 1e-9), 1.0)
            vals[out.index.get_indexer(idx)] = -w_k * np.log(np.maximum(ratio, 1e-6))
        out[f"def_{fn}"] = vals
    out["def_total"] = out["def_MIMO"] + out["def_SpectralEfficiency"] + out["def_ResourceBlocks"] + out["def_Efficiency"]
    return out


st_def = compute_deficits(st_steady)
vc_def = compute_deficits(vc)

# Pick the clean Bharti501 Airtel capture_000_20261013_093651 run (or best complete Bharti501 Airtel run)
run_target = "capture_000_20261013_093651"
sub_run = st_def[(st_def["Location"] == "indoor_Bharti501") & (st_def["Operator"] == "Airtel") & (st_def["Run"] == run_target)].copy()
if len(sub_run) < 10:
    # Fallback to richest Bharti501 Airtel run
    cand = st_def[(st_def["Location"] == "indoor_Bharti501") & (st_def["Operator"] == "Airtel")]
    best_r = cand.groupby("Run").size().idxmax()
    run_target = best_r
    sub_run = cand[cand["Run"] == best_r].copy()

dl_part = sub_run[sub_run["Direction"] == "Downlink"].sort_values("Aligned_Bin").reset_index(drop=True)
ul_part = sub_run[sub_run["Direction"] == "Uplink"].sort_values("Aligned_Bin").reset_index(drop=True)
timeline = pd.concat([dl_part, ul_part], ignore_index=True)
timeline["sec_idx"] = np.arange(1, len(timeline) + 1)
n_dl = len(dl_part)

fig, (axL, axR) = plt.subplots(1, 2, figsize=(13.2, 4.7), dpi=300, gridspec_kw={"width_ratios": [1.05, 1.15]})
c_rb, c_se, c_mimo, c_eff = "#2563EB", "#F97316", "#16A34A", "#DC2626"

t_x = timeline["sec_idx"].values
b_rb = timeline["def_ResourceBlocks"].values
b_se = timeline["def_SpectralEfficiency"].values
b_mi = timeline["def_MIMO"].values
b_ef = timeline["def_Efficiency"].values

axL.axvspan(0.4, n_dl + 0.5, color="#EFF6FF", alpha=0.6, zorder=0)
axL.axvspan(n_dl + 0.5, len(timeline) + 0.6, color="#FDF4FF", alpha=0.6, zorder=0)
axL.bar(t_x, b_rb, width=0.72, color=c_rb, alpha=0.88)
axL.bar(t_x, b_se, width=0.72, bottom=b_rb, color=c_se, alpha=0.88)
axL.bar(t_x, b_mi, width=0.72, bottom=b_rb+b_se, color=c_mimo, alpha=0.88)
axL.bar(t_x, b_ef, width=0.72, bottom=b_rb+b_se+b_mi, color=c_eff, alpha=0.88)
axL.axvline(n_dl + 0.5, color="#1E293B", ls="--", lw=1.4)
axL.set_xlabel("Speedtest Timeline (Active DL Phase → Active UL Phase, Seconds)")
axL.set_ylabel("Log-Capacity Deficit Magnitude (-Δ_k)")
axL.set_ylim(0, max(b_rb+b_se+b_mi+b_ef) * 1.45)
axL.text(n_dl / 2 + 0.5, axL.get_ylim()[1] * 0.94, f"← Active DL (1–{n_dl}s)", ha="center", va="top",
         fontsize=8.5, fontweight="bold", color="#1D4ED8", bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#93C5FD"))
axL.text(n_dl + (len(timeline)-n_dl)/2 + 0.5, axL.get_ylim()[1] * 0.94, f"Active UL ({n_dl+1}–{len(timeline)}s) →", ha="center", va="top",
         fontsize=8.5, fontweight="bold", color="#7E22CE", bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#D8B4FE"))

axL2 = axL.twinx()
axL2.plot(t_x[:n_dl], dl_part[TARGET].values, "o-", color="#0F172A", lw=2.0, ms=5)
axL2.plot(t_x[n_dl:], ul_part[TARGET].values, "^--", color="#7E22CE", lw=2.0, ms=5.5)
axL2.set_ylabel("Active Application Throughput (Mbps)", color="#0F172A")
axL2.set_ylim(0, max(dl_part[TARGET].max(), 200) * 1.22)
axL.set_title("A. Two-Phase Speedtest Deficit Timeline (Bharti501, Airtel)", fontsize=11)
axL.grid(axis="y", zorder=0)
axL.spines["top"].set_visible(False); axL2.spines["top"].set_visible(False)

regimes = [
    ("VC DL (Airtel)", vc_def, "Airtel", "Downlink"),
    ("VC DL (Jio)", vc_def, "Jio", "Downlink"),
    ("VC DL (Vi)", vc_def, "Vodafone", "Downlink"),
    ("VC UL (Airtel)", vc_def, "Airtel", "Uplink"),
    ("VC UL (Jio)", vc_def, "Jio", "Uplink"),
    ("VC UL (Vi)", vc_def, "Vodafone", "Uplink"),
    ("ST DL (Airtel)", st_def, "Airtel", "Downlink"),
    ("ST DL (Jio)", st_def, "Jio", "Downlink"),
    ("ST DL (Vi)", st_def, "Vodafone", "Downlink"),
    ("ST UL (Airtel)", st_def, "Airtel", "Uplink"),
    ("ST UL (Jio)", st_def, "Jio", "Uplink"),
    ("ST UL (Vi)", st_def, "Vodafone", "Uplink"),
]

r_labels, s_rb, s_se, s_mi, s_ef = [], [], [], [], []
def_summary_rows = []
for lbl, df_src, op, d in regimes:
    sub = df_src[(df_src["Operator"] == op) & (df_src["Direction"] == d)]
    sub = sub[sub["def_total"] > 1e-6]
    v_rb = 100.0 * (sub["def_ResourceBlocks"] / sub["def_total"]).mean()
    v_se = 100.0 * (sub["def_SpectralEfficiency"] / sub["def_total"]).mean()
    v_mi = 100.0 * (sub["def_MIMO"] / sub["def_total"]).mean()
    v_ef = 100.0 * (sub["def_Efficiency"] / sub["def_total"]).mean()
    r_labels.append(lbl)
    s_rb.append(v_rb); s_se.append(v_se); s_mi.append(v_mi); s_ef.append(v_ef)
    def_summary_rows.append({"Regime": lbl, "n": len(sub), "RB_pct": round(v_rb, 1), "SE_pct": round(v_se, 1), "MIMO_pct": round(v_mi, 1), "Eff_pct": round(v_ef, 1)})

def_sum_df = pd.DataFrame(def_summary_rows)
def_sum_df.to_csv(os.path.join(LR_DIR, "deficit_summary_clean.csv"), index=False)
print("\n=== CLEAN DEFICIT DECOMPOSITION SHARES (%) ===")
print(def_sum_df.to_string(index=False))

y_r = np.arange(len(r_labels))
s_rb, s_se, s_mi, s_ef = map(np.array, (s_rb, s_se, s_mi, s_ef))
axR.barh(y_r, s_rb, color=c_rb, alpha=0.88, height=0.68)
axR.barh(y_r, s_se, left=s_rb, color=c_se, alpha=0.88, height=0.68)
axR.barh(y_r, s_mi, left=s_rb+s_se, color=c_mimo, alpha=0.88, height=0.68)
axR.barh(y_r, s_ef, left=s_rb+s_se+s_mi, color=c_eff, alpha=0.88, height=0.68)
axR.axhline(5.5, color="#1E293B", ls="--", lw=1.1)

for i in range(len(r_labels)):
    for val, left in [(s_rb[i], 0), (s_se[i], s_rb[i]), (s_mi[i], s_rb[i]+s_se[i]), (s_ef[i], s_rb[i]+s_se[i]+s_mi[i])]:
        if val >= 9.5:
            axR.text(left + val/2, i, f"{val:.0f}%", ha="center", va="center", color="white", fontsize=8.5, fontweight="bold")

axR.set_yticks(y_r)
axR.set_yticklabels(r_labels, fontsize=9, fontweight="bold")
axR.set_xlim(0, 100)
axR.set_xlabel("Mean Share of Total PHY Log-Deficit (%)")
axR.set_title("B. Mean PHY Deficit Share Across 12 Regimes (ST vs. VC)", fontsize=11)
axR.spines["top"].set_visible(False); axR.spines["right"].set_visible(False)

handles_def = [
    Patch(facecolor=c_rb, label="Resource Blocks (RB)"),
    Patch(facecolor=c_se, label="Spectral Efficiency (MCS)"),
    Patch(facecolor=c_mimo, label="MIMO Layers"),
    Patch(facecolor=c_eff, label="Efficiency (Retx)"),
]
fig.legend(handles=handles_def, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.04), fontsize=9.2, frameon=True)
plt.tight_layout(rect=[0, 0.04, 1, 1], w_pad=2.0)
fig5_path = os.path.join(LR_DIR, "deficit_decomposition_results.png")
plt.savefig(fig5_path, dpi=300, bbox_inches="tight")
shutil.copyfile(fig5_path, os.path.join(PRES_FIGS, "fig5_deficit_decomposition.png"))
plt.close(fig)
print("\nSaved clean regression_results.png and deficit_decomposition_results.png!")
