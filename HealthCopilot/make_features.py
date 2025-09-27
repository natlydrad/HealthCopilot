# make_features.py
# Build feature set for meal-level modeling
#
# Input: MealEvents.csv, GlucoseReadings.csv
# Output: MealFeatures.csv

import os
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression

# --- Paths ---
base_dir = os.path.dirname(__file__)
meals_path = os.path.join(base_dir, "MealEvents.csv")
glucose_path = os.path.join(base_dir, "GlucoseReadings.csv")

meals = pd.read_csv(meals_path, parse_dates=["meal_time"])
glucose = pd.read_csv(glucose_path, parse_dates=["timestamp"])

# Ensure lowercase headers
glucose.columns = glucose.columns.str.strip().str.lower()
meals.columns = meals.columns.str.strip()

# --- Helper: rolling glucose stats ---
def compute_glucose_stats(glucose, t0, window="30min"):
    """Compute mean, std, slope of glucose in window before t0"""
    t0 = pd.to_datetime(t0)
    g = glucose[(glucose["timestamp"] > t0 - pd.Timedelta(window)) &
                (glucose["timestamp"] <= t0)]
    if g.empty:
        return np.nan, np.nan, np.nan
    
    mean = g["glucose"].mean()
    std = g["glucose"].std()

    # slope = linear regression over time
    x = (g["timestamp"] - g["timestamp"].min()).dt.total_seconds().values.reshape(-1, 1)
    y = g["glucose"].values
    if len(x) > 1:
        model = LinearRegression().fit(x, y)
        slope = model.coef_[0] * 60  # mg/dL per minute
    else:
        slope = np.nan
    
    return mean, std, slope

# --- Build features per meal ---
records = []

for _, meal in meals.iterrows():
    t0 = meal["meal_time"]

    row = {}
    row["meal_time"] = t0

    # --- Meal-level features ---
    row["carbs"] = meal.get("carbs", 0)
    row["fiber"] = meal.get("fiber", 0)
    row["protein"] = meal.get("protein", 0)
    row["fat"] = meal.get("fat", 0)

    # Ratios (avoid divide-by-zero)
    row["carb_fiber_ratio"] = row["carbs"] / (row["fiber"] + 1e-6)
    row["carb_protein_ratio"] = row["carbs"] / (row["protein"] + 1e-6)

    # --- Pre-meal glucose context ---
    mean30, std30, slope30 = compute_glucose_stats(glucose, t0, "30min")
    mean60, std60, slope60 = compute_glucose_stats(glucose, t0, "60min")

    row["glucose_mean_30m"] = mean30
    row["glucose_std_30m"] = std30
    row["glucose_slope_30m"] = slope30
    row["glucose_mean_60m"] = mean60
    row["glucose_std_60m"] = std60
    row["glucose_slope_60m"] = slope60

    # --- Circadian / timing context ---
    row["hour_of_day"] = t0.hour
    row["day_of_week"] = t0.weekday()
    row["is_weekend"] = 1 if row["day_of_week"] >= 5 else 0

    # --- Hack flags (starter: fiber preload) ---
    row["fiber_preload"] = 1 if row["fiber"] >= 5 else 0  # tweak threshold later

    # --- Targets (from MealEvents.csv) ---
    # pass through outcome variables so X + y are aligned
    for col in ["aucGlucose", "deltaGlucose", "spike",
                "timeToPeak", "durationAboveBaseline",
                "timeToReturnBaseline", "numFluctuations"]:
        if col in meal:
            row[col] = meal[col]

    records.append(row)

features = pd.DataFrame(records)

# --- Save ---
out_path = os.path.join(base_dir, "MealFeatures.csv")
features.to_csv(out_path, index=False)
print(f"✅ Saved MealFeatures.csv with {features.shape[0]} rows and {features.shape[1]} columns")
