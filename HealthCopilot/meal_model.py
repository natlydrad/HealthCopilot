# meal_model.py
# HealthCopilot Stage-1: Multi-target modeling + Report
#
# Input: MealFeatures.csv
# Output: Model metrics + SHAP plots + Markdown report

import os
import pandas as pd
import matplotlib.pyplot as plt
import shap
from sklearn.metrics import mean_absolute_error, r2_score, accuracy_score, f1_score

# Try XGBoost, fallback to sklearn if missing
try:
    import xgboost as xgb
    USE_XGB = True
except ImportError:
    from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
    USE_XGB = False

# --- Load dataset ---
base_dir = os.path.dirname(__file__)
df = pd.read_csv(os.path.join(base_dir, "MealFeatures.csv"), parse_dates=["meal_time"])

df = df.dropna()

targets = [
    "aucGlucose",
    "deltaGlucose",
    "spike",
    "timeToPeak",
    "durationAboveBaseline",
    "timeToReturnBaseline",
    "numFluctuations"
]
targets = [t for t in targets if t in df.columns]

feature_cols = [c for c in df.columns if c not in targets + ["meal_time"]]

print("Features being used:", feature_cols)
print("Targets to analyze:", targets)

# --- Storage for metrics ---
metrics_summary = []

# --- Loop over targets ---
for target in targets:
    print(f"\n=== Training for target: {target} ===")
    y = df[target]
    X = df[feature_cols]

    # Pick model
    if target == "spike":  # classification
        if USE_XGB:
            model = xgb.XGBClassifier(
                n_estimators=100, max_depth=4, learning_rate=0.1,
                tree_method="hist", n_jobs=1, verbosity=0
            )
        else:
            from sklearn.ensemble import RandomForestClassifier
            model = RandomForestClassifier(n_estimators=100, random_state=42)
    else:  # regression
        if USE_XGB:
            model = xgb.XGBRegressor(
                n_estimators=100, max_depth=4, learning_rate=0.1,
                tree_method="hist", n_jobs=1, verbosity=0
            )
        else:
            from sklearn.ensemble import RandomForestRegressor
            model = RandomForestRegressor(n_estimators=100, random_state=42)

    # Train
    model.fit(X, y)
    print("✅ Model trained")

    # Evaluate
    y_pred = model.predict(X)
    if target == "spike":
        acc = accuracy_score(y, y_pred)
        f1 = f1_score(y, y_pred)
        metrics_summary.append({"target": target, "ACC": acc, "F1": f1})
        print(f"Metrics for {target}: ACC={acc:.3f}, F1={f1:.3f}")
    else:
        mae = mean_absolute_error(y, y_pred)
        r2 = r2_score(y, y_pred)
        metrics_summary.append({"target": target, "MAE": mae, "R2": r2})
        print(f"Metrics for {target}: MAE={mae:.2f}, R2={r2:.2f}")

    # SHAP plots
    try:
        explainer = shap.Explainer(model, X)
        sample_X = X.sample(min(50, len(X)), random_state=42)
        shap_values = explainer(sample_X)

        # Summary
        shap.summary_plot(shap_values, sample_X, show=False)
        plt.tight_layout()
        fname_summary = f"shap_summary_{target}.png"
        plt.savefig(fname_summary)
        plt.close()

        # First example waterfall
        shap.plots.waterfall(shap_values[0], show=False)
        fname_waterfall = f"shap_waterfall_{target}_0.png"
        plt.savefig(fname_waterfall)
        plt.close()

        print(f"✅ SHAP plots saved for {target}")

        # Attach filenames to metrics row
        metrics_summary[-1]["shap_summary"] = fname_summary
        metrics_summary[-1]["shap_waterfall"] = fname_waterfall

    except Exception as e:
        print(f"⚠️ SHAP failed for {target}: {e}")

# --- Write report ---
report_path = os.path.join(base_dir, "model_report.md")
with open(report_path, "w") as f:
    f.write("# HealthCopilot Model Report\n\n")
    f.write("## Summary Table\n\n")
    f.write("| Target | Metrics | SHAP Summary | SHAP Waterfall |\n")
    f.write("|--------|---------|--------------|----------------|\n")
    for row in metrics_summary:
        if "ACC" in row:  # classification
            metric_str = f"ACC={row['ACC']:.3f}, F1={row['F1']:.3f}"
        else:
            metric_str = f"MAE={row['MAE']:.2f}, R2={row['R2']:.2f}"
        shap_summary_link = f"![summary]({row.get('shap_summary','')})" if "shap_summary" in row else "n/a"
        shap_waterfall_link = f"![waterfall]({row.get('shap_waterfall','')})" if "shap_waterfall" in row else "n/a"
        f.write(f"| {row['target']} | {metric_str} | {shap_summary_link} | {shap_waterfall_link} |\n")

print(f"\n📄 Report saved at {report_path}")
