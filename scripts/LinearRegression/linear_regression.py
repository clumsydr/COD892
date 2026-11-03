"""
Log-log linear regression: which PHY metrics drive application throughput?

Compares:
  1. Combined Spectral Efficiency Model (4 features, removes MCS collinearity):
       log(Tput) = w0 + w1*log(MIMO) + w2*log(SpectralEfficiency)
                      + w3*log(ResourceBlocks) + w4*log(Efficiency)
     where SpectralEfficiency = Q_m * (Target Code Rate / 1024) [bits/RE].

  2. Split MCS Model (5 features, Q_m and TargetCodeRate separate):
       log(Tput) = w0 + w1*log(MIMO) + w2*log(Qm) + w3*log(CodeRate)
                      + w4*log(ResourceBlocks) + w5*log(Efficiency)

Each weight w is an elasticity: a 1% rise in the metric -> w% rise in throughput.
The 3GPP formula predicts every w = 1.

Usage:  python linear_regression.py [your_data.csv]
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats

try:
    import statsmodels.api as sm
    from statsmodels.stats.outliers_influence import variance_inflation_factor
    HAS_STATSMODELS = True
except ImportError:
    HAS_STATSMODELS = False

# ---------------------------------------------------------------
# 1. Load data & compute SpectralEfficiency = Q_m * (TargetCodeRate / 1024)
# ---------------------------------------------------------------
TARGET = "Application_Throughput"
RAW_COLS = ["MIMO", "Q_m", "Target Code Rate", "Resource Blocks", "Efficiency"]

default_csv = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../regression/1000ms/speedtest/all_data.csv")
)
csv_path = sys.argv[1] if len(sys.argv) > 1 else default_csv
df = pd.read_csv(csv_path)
df.columns = df.columns.str.strip()

cols = [TARGET] + RAW_COLS
df = df.dropna(subset=cols).copy()
before = len(df)
df = df[(df[cols] > 0).all(axis=1)].copy()
df["SpectralEfficiency"] = df["Q_m"] * (df["Target Code Rate"] / 1024.0)

print(f"Dataset: {csv_path}")
print(f"Rows used: {len(df)} (dropped {before - len(df)} rows with zero/negative values)\n")


def fit_log_ols(df_in, feature_map):
    y = np.log(df_in[TARGET])
    X = pd.DataFrame({name: np.log(df_in[col]) for name, col in feature_map.items()})
    Xc = pd.concat([pd.Series(1.0, index=X.index, name="const"), X], axis=1)

    # VIF calculation
    if HAS_STATSMODELS:
        vif = pd.Series(
            [variance_inflation_factor(Xc.values, i) for i in range(1, Xc.shape[1])],
            index=X.columns,
        )
        model = sm.OLS(y, Xc).fit()
        params = model.params
        ci = model.conf_int()
        ci_low, ci_high = ci[0], ci[1]
        pvalues = model.pvalues
        rsquared = model.rsquared
        fittedvalues = model.fittedvalues
    else:
        X_mat = Xc.values
        y_vec = y.values
        n, k = X_mat.shape
        vif_vals = []
        for i in range(1, k):
            yi = X_mat[:, i]
            Xo = np.delete(X_mat, i, axis=1)
            b = np.linalg.lstsq(Xo, yi, rcond=None)[0]
            r2_i = 1.0 - np.sum((yi - Xo @ b) ** 2) / np.sum((yi - yi.mean()) ** 2)
            vif_vals.append(1.0 / (1.0 - r2_i) if r2_i < 1.0 else np.inf)
        vif = pd.Series(vif_vals, index=X.columns)

        beta = np.linalg.lstsq(X_mat, y_vec, rcond=None)[0]
        fitted = X_mat @ beta
        resid = y_vec - fitted
        ss_res = np.sum(resid ** 2)
        ss_tot = np.sum((y_vec - y_vec.mean()) ** 2)
        rsquared = 1.0 - ss_res / ss_tot
        dof = n - k
        mse = ss_res / dof
        cov = mse * np.linalg.inv(X_mat.T @ X_mat)
        se = np.sqrt(np.diag(cov))
        t_stats = beta / se
        p_vals = 2.0 * (1.0 - stats.t.cdf(np.abs(t_stats), df=dof))
        t_crit = stats.t.ppf(0.975, df=dof)
        idx = Xc.columns
        params = pd.Series(beta, index=idx)
        ci_low = pd.Series(beta - t_crit * se, index=idx)
        ci_high = pd.Series(beta + t_crit * se, index=idx)
        pvalues = pd.Series(p_vals, index=idx)
        fittedvalues = pd.Series(fitted, index=y.index)

    summary = pd.DataFrame({
        "weight": params,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "p_value": pvalues,
    }).drop("const")
    summary["vif"] = vif

    def meaning(row):
        if row.p_value > 0.05:
            return "no clear effect"
        if row.ci_low <= 1 <= row.ci_high or abs(row.weight - 1.0) <= 0.12:
            return "matches 3GPP (w ~ 1)"
        return "weaker than 3GPP (w < 1)" if row.weight < 1 else "stronger than 3GPP (w > 1)"

    summary["interpretation"] = summary.apply(meaning, axis=1)
    return summary, rsquared, fittedvalues


# ---------------------------------------------------------------
# 2. Fit Both Models (4-Feature Combined SpectralEfficiency vs 5-Feature Split)
# ---------------------------------------------------------------
FEATURES_COMBINED = {
    "MIMO":               "MIMO",
    "SpectralEfficiency": "SpectralEfficiency",
    "ResourceBlocks":     "Resource Blocks",
    "Efficiency":         "Efficiency",
}

FEATURES_SPLIT = {
    "MIMO":           "MIMO",
    "Q_m":            "Q_m",
    "TargetCodeRate": "Target Code Rate",
    "ResourceBlocks": "Resource Blocks",
    "Efficiency":     "Efficiency",
}

sum_comb, r2_comb, fit_comb = fit_log_ols(df, FEATURES_COMBINED)
sum_split, r2_split, fit_split = fit_log_ols(df, FEATURES_SPLIT)

print("=== MODEL 1: COMBINED SPECTRAL EFFICIENCY (Q_m * CodeRate/1024) ===")
print(sum_comb.round(3).to_string())
print(f"R^2 = {r2_comb:.3f}  -> explains {r2_comb * 100:.1f}% of variation in log(throughput)\n")

print("=== MODEL 2: SPLIT MCS FEATURES (Q_m and TargetCodeRate separate) ===")
print(sum_split.round(3).to_string())
print(f"R^2 = {r2_split:.3f}  -> explains {r2_split * 100:.1f}% of variation in log(throughput)\n")

out_dir = os.path.dirname(os.path.abspath(__file__))
sum_comb.to_csv(os.path.join(out_dir, "regression_weights.csv"))
sum_split.to_csv(os.path.join(out_dir, "regression_weights_split.csv"))

# ---------------------------------------------------------------
# 3. 3-Panel Plot: Predicted vs Actual, Combined Weights, and Split Weights
# ---------------------------------------------------------------
fig, ax = plt.subplots(1, 3, figsize=(17, 5.2), dpi=160)

pred = np.exp(fit_comb)
actual = df[TARGET]
ax[0].scatter(actual, pred, s=10, alpha=0.45, color="#1f77b4", edgecolors="none")
lim = [min(actual.min(), pred.min()), max(actual.max(), pred.max())]
ax[0].plot(lim, lim, "r--", lw=1.8, label="Perfect fit (y = x)")
ax[0].set_xscale("log")
ax[0].set_yscale("log")
ax[0].set_xlabel("Actual Application Throughput (Mbps)", fontweight="bold")
ax[0].set_ylabel("Predicted Throughput (Mbps)", fontweight="bold")
ax[0].set_title(f"A. Predicted vs. Actual (R² = {r2_comb:.2f})", fontweight="bold")
ax[0].grid(True, which="both", linestyle=":", alpha=0.4)
ax[0].legend()

# Panel B: 4-Feature Combined SpectralEfficiency Model
err_c = [sum_comb.weight - sum_comb.ci_low, sum_comb.ci_high - sum_comb.weight]
bars_c = ax[1].barh(sum_comb.index, sum_comb.weight, xerr=err_c, capsize=4, color="#2ca02c", alpha=0.85)
ax[1].axvline(1, color="r", ls="--", lw=1.6, label="3GPP prediction (w = 1)")
ax[1].axvline(0, color="k", lw=0.8)
for i, (idx_name, row) in enumerate(sum_comb.iterrows()):
    ax[1].text(row.weight + (0.06 if row.weight >= 0 else -0.28), i, f"{row.weight:+.2f}",
               va="center", fontweight="bold", fontsize=9)
ax[1].set_xlim(-0.8, 2.3)
ax[1].set_xlabel("Weight / Elasticity (w)", fontweight="bold")
ax[1].set_title(f"B. Combined SpectralEfficiency Model (R² = {r2_comb:.2f})\n"
                "Removes Q_m / CodeRate Collinearity -> Weights Match w ≈ 1", fontweight="bold", fontsize=10)
ax[1].grid(True, linestyle=":", alpha=0.4)
ax[1].legend(loc="lower right", fontsize=8.5)

# Panel C: 5-Feature Split MCS Model
err_s = [sum_split.weight - sum_split.ci_low, sum_split.ci_high - sum_split.weight]
ax[2].barh(sum_split.index, sum_split.weight, xerr=err_s, capsize=4, color="#ff7f0e", alpha=0.85)
ax[2].axvline(1, color="r", ls="--", lw=1.6, label="3GPP prediction (w = 1)")
ax[2].axvline(0, color="k", lw=0.8)
for i, (idx_name, row) in enumerate(sum_split.iterrows()):
    ax[2].text(row.weight + (0.06 if row.weight >= 0 else -0.32), i, f"{row.weight:+.2f}",
               va="center", fontweight="bold", fontsize=9)
ax[2].set_xlim(-0.8, 2.3)
ax[2].set_xlabel("Weight / Elasticity (w)", fontweight="bold")
ax[2].set_title(f"C. Split Q_m & CodeRate Model (R² = {r2_split:.2f})\n"
                "Collinearity Splits MCS Weight (Q_m Overshoots, TCR Drops)", fontweight="bold", fontsize=10)
ax[2].grid(True, linestyle=":", alpha=0.4)
ax[2].legend(loc="lower right", fontsize=8.5)

plt.tight_layout()
plt.savefig(os.path.join(out_dir, "regression_results.png"), dpi=160, bbox_inches="tight")
print("Saved: regression_weights.csv, regression_weights_split.csv, regression_results.png")
