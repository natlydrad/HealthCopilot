# meal_model.py
# HealthCopilot Stage-1: Multi-target modeling
#
# Input: MealFeatures.csv
# Output: RESULTS/results_<timestamp>/ with:
#         - metrics.json
#         - SHAP plots (PNG files)
#
# Note: CSV snapshots & PDF are handled in make_report.py

import os
import json
import pandas as pd
import matplotlib.pyplot as plt
import shap
from sklearn.metrics import mean_absolute_error, r2_score, accuracy_score, f1_score
from datetime import datetime

# Try XGBoost, fallback to sklearn if missing
try:
    import xgboost as xgb
    USE_XGB = True
except ImportError:
    from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
    USE_XGB = False

# --- Timestamp + results folder ---
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
project_dir = os.path.dirname(os.path.dirname(__file__))
results_root = os.path.join(project_dir, "RESULTS")
os.makedirs(results_root, exist_ok=True)

results_dir = os.path.join(results_root, f"results_{timestamp}")
os.makedirs(results_dir, exist_ok=True)

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
metrics_summary = {}

# --- Train + evaluate + collect plots ---
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
    if target == "spike":
        y_pred = model.predict(X)
        acc = accuracy_score(y, y_pred)
        f1 = f1_score(y, y_pred)
        metrics_summary[target] = {"ACC": acc, "F1": f1}
        print(f"Metrics for {target}: ACC={acc:.3f}, F1={f1:.3f}")
    else:
        y_pred = model.predict(X)
        mae = mean_absolute_error(y, y_pred)
        r2 = r2_score(y, y_pred)
        metrics_summary[target] = {"MAE": mae, "R2": r2}
        print(f"Metrics for {target}: MAE={mae:.2f}, R2={r2:.2f}")

    # SHAP plots
    try:
        explainer = shap.Explainer(model, X)
        sample_X = X.sample(min(50, len(X)), random_state=42)
        shap_values = explainer(sample_X)

        # Save summary plot
        shap.summary_plot(shap_values, sample_X, show=False)
        fig = plt.gcf()
        fig.savefig(os.path.join(results_dir, f"{target}_shap_summary.png"))
        plt.close(fig)

        # Save waterfall plot (first sample)
        shap.plots.waterfall(shap_values[0], show=False)
        fig = plt.gcf()
        fig.savefig(os.path.join(results_dir, f"{target}_shap_waterfall.png"))
        plt.close(fig)

        print(f"✅ SHAP plots saved for {target}")

    except Exception as e:
        print(f"⚠️ SHAP failed for {target}: {e}")

# --- Save metrics as JSON ---
metrics_path = os.path.join(results_dir, "metrics.json")
with open(metrics_path, "w") as f:
    json.dump(metrics_summary, f, indent=2)
print(f"\n📊 Metrics saved at {metrics_path}")

# --- Call make_report.py automatically ---
import subprocess, sys
print("📝 Generating PDF report...")
subprocess.run([sys.executable, os.path.join(base_dir, "make_report.py"), results_dir])
