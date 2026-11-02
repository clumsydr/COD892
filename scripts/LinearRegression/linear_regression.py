"""
Log-log linear regression: which PHY metrics drive application throughput?

Model:
  log(Tput) = w0 + w1*log(Layers) + w2*log(Qm) + w3*log(CodeRate)
                 + w4*log(RB_total) + w5*log(Efficiency)

Each weight w is an elasticity: a 1% rise in the metric -> w% rise in throughput.
The 3GPP formula predicts every w = 1.

Usage:  python linear_regression.py your_data.csv
"""

import sys
import numpy as np
import pandas as pd
import statsmodels.api as sm
import matplotlib.pyplot as plt
from statsmodels.stats.outliers_influence import variance_inflation_factor

# ---------------------------------------------------------------
# 1. EDIT THESE to match the column names in your CSV
# ---------------------------------------------------------------
TARGET = "Application_Throughput"   # application throughput
FEATURES = {                        # name to show : column in CSV
    "MIMO":            "MIMO",
    "Q_m":             "Q_m",
    "TargetCodeRate":  "Target Code Rate",
    "ResourceBlocks":  "Resource Blocks",
    "Efficiency":      "Efficiency",
}

# ---------------------------------------------------------------
# 2. Load data
# ---------------------------------------------------------------
csv_path = sys.argv[1] if len(sys.argv) > 1 else "/scratch/5GMeasurements/regression/1000ms/all_data.csv"
df = pd.read_csv(csv_path)
df.columns = df.columns.str.strip()   # remove accidental spaces in headers
cols = [TARGET] + list(FEATURES.values())
df = df[cols].dropna()

# log() is undefined for values <= 0, so drop those rows
before = len(df)
df = df[(df[cols] > 0).all(axis=1)]
print(f"Rows used: {len(df)} (dropped {before - len(df)} rows with zero/negative values)\n")

# ---------------------------------------------------------------
# 3. Take logs
# ---------------------------------------------------------------
y = np.log(df[TARGET])
X = pd.DataFrame({name: np.log(df[col]) for name, col in FEATURES.items()})

# ---------------------------------------------------------------
# 4. Check collinearity (VIF). Above ~10 = metric overlaps strongly with others
# ---------------------------------------------------------------
Xc = sm.add_constant(X)
vif = pd.Series([variance_inflation_factor(Xc.values, i) for i in range(1, Xc.shape[1])],
                index=X.columns)
print("Collinearity check (VIF):")
print(vif.round(2).to_string(), "\n")

# ---------------------------------------------------------------
# 5. Fit linear regression (least squares)
# ---------------------------------------------------------------
model = sm.OLS(y, Xc).fit()
print(model.summary())

# ---------------------------------------------------------------
# 6. Simple summary table of the weights
# ---------------------------------------------------------------
ci = model.conf_int()
summary = pd.DataFrame({
    "weight":   model.params,
    "ci_low":   ci[0],
    "ci_high":  ci[1],
    "p_value":  model.pvalues,
}).drop("const")

def meaning(row):
    if row.p_value > 0.05:
        return "no clear effect"
    if row.ci_low <= 1 <= row.ci_high:
        return "matches 3GPP (w ~ 1)"
    return "weaker than 3GPP (w < 1)" if row.weight < 1 else "stronger than 3GPP (w > 1)"

summary["interpretation"] = summary.apply(meaning, axis=1)
print("\nWEIGHTS")
print(summary.round(3).to_string())
print(f"\nR^2 = {model.rsquared:.3f}  -> PHY metrics explain "
      f"{model.rsquared * 100:.1f}% of the variation in log(throughput)")

summary.to_csv("regression_weights.csv")

# ---------------------------------------------------------------
# 7. Plots: predicted vs actual, and weights with 95% CI
# ---------------------------------------------------------------
fig, ax = plt.subplots(1, 2, figsize=(12, 5))

pred = np.exp(model.fittedvalues)
actual = df[TARGET]
ax[0].scatter(actual, pred, s=10, alpha=0.5)
lim = [min(actual.min(), pred.min()), max(actual.max(), pred.max())]
ax[0].plot(lim, lim, "r--", label="perfect fit")
ax[0].set_xlabel("Actual throughput")
ax[0].set_ylabel("Predicted throughput")
ax[0].set_title(f"Predicted vs actual (R² = {model.rsquared:.2f})")
ax[0].legend()

err = [summary.weight - summary.ci_low, summary.ci_high - summary.weight]
ax[1].barh(summary.index, summary.weight, xerr=err, capsize=4)
ax[1].axvline(1, color="r", ls="--", label="3GPP prediction (w = 1)")
ax[1].axvline(0, color="k", lw=0.8)
ax[1].set_xlabel("Weight (elasticity)")
ax[1].set_title("Estimated weights with 95% CI")
ax[1].legend()

plt.tight_layout()
plt.savefig("regression_results.png", dpi=150)
print("\nSaved: regression_weights.csv, regression_results.png")