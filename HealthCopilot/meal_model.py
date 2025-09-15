# meal_model.py
# HealthCopilot
#
# Created by Natalie Radu on 8/4/25.

import os
import pandas as pd
import matplotlib.pyplot as plt
import shap

# Try XGBoost, fallback to sklearn if it fails
try:
    import xgboost as xgb
    USE_XGB = True
except ImportError:
    from sklearn.ensemble import RandomForestRegressor
    USE_XGB = False

# --- Load CSV ---
base_dir = os.path.dirname(__file__)
df = pd.read_csv(os.path.join(base_dir, "MealEvents.csv"))

# Drop missing values
df = df.dropna()

# Target
target = "aucGlucose"  # or "spike" for classification

# Features and labels
X = df[["carbs", "fiber", "fat", "protein", "preMealGlucose"]]
y = df[target]

print("Dataset shape:", X.shape, "| Target:", target)

# --- Train model ---
model = None
try:
    if USE_XGB:
        if target == "aucGlucose":
            model = xgb.XGBRegressor(
                n_estimators=50,
                max_depth=3,
                learning_rate=0.1,
                tree_method="hist",
                n_jobs=1,
                verbosity=1
            )
        else:
            model = xgb.XGBClassifier(
                n_estimators=50,
                max_depth=3,
                learning_rate=0.1,
                tree_method="hist",
                n_jobs=1,
                verbosity=1
            )

        print("🚀 Training with XGBoost...")
        model.fit(X, y)

    else:
        raise ImportError("XGBoost not available")

except Exception as e:
    print(f"⚠️ XGBoost failed: {e}")
    print("👉 Falling back to RandomForest")

    from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
    if target == "aucGlucose":
        model = RandomForestRegressor(n_estimators=100, random_state=42)
    else:
        model = RandomForestClassifier(n_estimators=100, random_state=42)

    model.fit(X, y)

print("✅ Model trained")

# --- SHAP explanation (sample for speed) ---
try:
    explainer = shap.Explainer(model, X)
    sample_X = X.sample(min(30, len(X)), random_state=42)
    shap_values = explainer(sample_X)

    shap.summary_plot(shap_values, sample_X, show=False)
    plt.tight_layout()
    plt.savefig("shap_summary.png")
    print("✅ SHAP summary plot saved as shap_summary.png")

    shap.plots.waterfall(shap_values[0], show=False)
    plt.savefig("shap_waterfall_0.png")
    print("✅ First prediction breakdown saved as shap_waterfall_0.png")

except Exception as e:
    print(f"⚠️ SHAP failed: {e}")
