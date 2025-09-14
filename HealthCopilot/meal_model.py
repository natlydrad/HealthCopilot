#
#  meal_model.py
# HealthCopilot
#
# Created by Natalie Radu on 8/4/25.
#

import pandas as pd
import xgboost as xgb
import shap
import matplotlib.pyplot as plt

# Load your CSV
import os
base_dir = os.path.dirname(__file__)
df = pd.read_csv(os.path.join(base_dir, "MealEvents.csv"))

# Drop missing values (you can make this more sophisticated later)
df = df.dropna()

# Choose target to analyze
# Options: "aucGlucose", or "spike" if you want classification
target = "aucGlucose"

# Set up features and labels
X = df[["carbs", "fiber", "fat", "protein", "preMealGlucose"]]  # add more later
y = df[target]

# Train model
model = xgb.XGBRegressor() if target == "aucGlucose" else xgb.XGBClassifier()
model.fit(X, y)

# Explain model with SHAP
explainer = shap.Explainer(model)
shap_values = explainer(X)

# SHAP plots
shap.summary_plot(shap_values, X, show=False)
plt.tight_layout()
plt.savefig("shap_summary.png")
print("✅ SHAP summary plot saved as shap_summary.png")

# Optional: show waterfall for first prediction
shap.plots.waterfall(shap_values[0], show=False)
plt.savefig("shap_waterfall_0.png")
print("✅ First prediction breakdown saved as shap_waterfall_0.png")


