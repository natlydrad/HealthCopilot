# meal_model.py
# HealthCopilot Stage-1: Multi-target modeling + PDF Report
#
# Input: MealFeatures.csv
# Output: Single PDF report (metrics cover page + SHAP plots, timestamped)

import os
import pandas as pd
import matplotlib.pyplot as plt
import shap
from sklearn.metrics import mean_absolute_error, r2_score, accuracy_score, f1_score
from matplotlib.backends.backend_pdf import PdfPages
from datetime import datetime

# Try XGBoost, fallback to sklearn if missing
try:
    import xgboost as xgb
    USE_XGB = True
except ImportError:
    from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
    USE_XGB = False

# --- Timestamp for filenames ---
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")

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

# --- Storage for metrics + plots ---
metrics_summary = []
plots = []  # store (fig, title) pairs

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
        metrics_summary.append(f"{target}: ACC={acc:.3f}, F1={f1:.3f}")
        print(f"Metrics for {target}: ACC={acc:.3f}, F1={f1:.3f}")
    else:
        y_pred = model.predict(X)
        mae = mean_absolute_error(y, y_pred)
        r2 = r2_score(y, y_pred)
        metrics_summary.append(f"{target}: MAE={mae:.2f}, R2={r2:.2f}")
        print(f"Metrics for {target}: MAE={mae:.2f}, R2={r2:.2f}")

    # SHAP plots -> capture as figures
    try:
        explainer = shap.Explainer(model, X)
        sample_X = X.sample(min(50, len(X)), random_state=42)
        shap_values = explainer(sample_X)

        # Summary plot
        shap.summary_plot(shap_values, sample_X, show=False)
        fig = plt.gcf()
        plots.append((fig, f"{target} - SHAP Summary"))
        plt.close(fig)

        # Waterfall plot (first sample)
        shap.plots.waterfall(shap_values[0], show=False)
        fig = plt.gcf()
        plots.append((fig, f"{target} - SHAP Waterfall"))
        plt.close(fig)

        print(f"✅ SHAP plots captured for {target}")

    except Exception as e:
        print(f"⚠️ SHAP failed for {target}: {e}")

# --- Build PDF ---
pdf_path = os.path.join(base_dir, f"model_report_{timestamp}.pdf")
with PdfPages(pdf_path) as pdf:

    # Cover page: metrics summary
    fig, ax = plt.subplots(figsize=(8.5, 11))
    ax.axis("off")
    ax.text(0.05, 0.95, f"HealthCopilot Model Report {timestamp}", fontsize=18, weight="bold", va="top")

    y_pos = 0.9
    for line in metrics_summary:
        ax.text(0.05, y_pos, line, fontsize=12, va="top")
        y_pos -= 0.05

    pdf.savefig(fig)
    plt.close(fig)

    # Following pages: SHAP plots
    for fig, title in plots:
        fig.suptitle(title, fontsize=14)
        pdf.savefig(fig)
        plt.close(fig)

print(f"\n📄 PDF report saved at {pdf_path}")
