# meal_model.py
# HealthCopilot Stage-1: Multi-target modeling with train/test split

import os
import json
import pandas as pd
import matplotlib.pyplot as plt
import shap
from sklearn.metrics import mean_absolute_error, r2_score, accuracy_score, f1_score
from datetime import datetime

# Train/test split
from sklearn.model_selection import train_test_split

# Try XGBoost, fallback to sklearn if missing
try:
    import xgboost as xgb
    USE_XGB = True
except ImportError:
    from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
    USE_XGB = False

# --- Timestamp + results folder ---
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
base_dir = os.path.dirname(__file__)
results_root = os.path.join(base_dir, "results")
os.makedirs(results_root, exist_ok=True)

results_dir = os.path.join(results_root, f"results_{timestamp}")
os.makedirs(results_dir, exist_ok=True)

# --- Load dataset ---
data_dir = os.path.join(base_dir, "data")
df = pd.read_csv(os.path.join(data_dir, "MealFeatures.csv"), parse_dates=["meal_time"])
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

    # ⏳ Chronological train/test split
    split_idx = int(len(df) * 0.7)  # 70% train, 30% test
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

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
    model.fit(X_train, y_train)
    print("✅ Model trained")

    # Evaluate on train and test
    metrics_summary[target] = {}
    if target == "spike":
        # Train
        y_train_pred = model.predict(X_train)
        acc_train = accuracy_score(y_train, y_train_pred)
        f1_train = f1_score(y_train, y_train_pred)
        metrics_summary[target]["train"] = {"ACC": acc_train, "F1": f1_train}

        # Test
        y_test_pred = model.predict(X_test)
        acc_test = accuracy_score(y_test, y_test_pred)
        f1_test = f1_score(y_test, y_test_pred)
        metrics_summary[target]["test"] = {"ACC": acc_test, "F1": f1_test}

        print(f"Train: ACC={acc_train:.3f}, F1={f1_train:.3f} | "
              f"Test: ACC={acc_test:.3f}, F1={f1_test:.3f}")

    else:
        # Train
        y_train_pred = model.predict(X_train)
        mae_train = mean_absolute_error(y_train, y_train_pred)
        r2_train = r2_score(y_train, y_train_pred)
        metrics_summary[target]["train"] = {"MAE": mae_train, "R2": r2_train}

        # Test
        y_test_pred = model.predict(X_test)
        mae_test = mean_absolute_error(y_test, y_test_pred)
        r2_test = r2_score(y_test, y_test_pred)
        metrics_summary[target]["test"] = {"MAE": mae_test, "R2": r2_test}

        print(f"Train: MAE={mae_train:.2f}, R2={r2_train:.2f} | "
              f"Test: MAE={mae_test:.2f}, R2={r2_test:.2f}")

    # SHAP plots (still from whole dataset for now)
    try:
        explainer = shap.Explainer(model, X_train)
        sample_X = X_test.sample(min(50, len(X_test)), random_state=42)
        shap_values = explainer(sample_X)

        shap.summary_plot(shap_values, sample_X, show=False)
        fig = plt.gcf()
        fig.savefig(os.path.join(results_dir, f"{target}_shap_summary.png"))
        plt.close(fig)

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
