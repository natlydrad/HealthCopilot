import pandas as pd
import numpy as np
import os

base_dir = os.path.dirname(__file__)

# --- Load CSVs ---
glucose = pd.read_csv(os.path.join(base_dir, "GlucoseReadings.csv"))
meals = pd.read_csv(os.path.join(base_dir, "Meals.csv"))

# Normalize headers
glucose.columns = glucose.columns.str.strip().str.lower()
meals.columns = meals.columns.str.strip().str.lower()

# Parse timestamps
glucose["timestamp"] = pd.to_datetime(glucose["timestamp"])
meals["time (utc)"] = pd.to_datetime(meals["time (utc)"])

# --- Detect available macro columns ---
col_map = {}
for target, keyword in {
    "carbs": "carb",
    "fat": "fat",
    "protein": "protein",
    "fiber": "fiber"
}.items():
    matches = [c for c in meals.columns if keyword in c]
    if matches:
        col_map[target] = matches[0]

print("Detected columns:", col_map)

# --- Group rows into meals ---
agg_dict = {v: "sum" for v in col_map.values()}
meal_groups = meals.groupby("time (utc)").agg(agg_dict).reset_index()

# Rename to clean names
meal_groups.rename(columns={v: k for k, v in col_map.items()}, inplace=True)

# Ensure all expected macros exist
for col in ["carbs", "fat", "protein", "fiber"]:
    if col not in meal_groups.columns:
        meal_groups[col] = 0

# --- Parameters ---
window = pd.Timedelta("2h")
records = []

# --- Extended Episode Metrics ---
records = []

for _, meal in meal_groups.iterrows():
    t0 = meal["time (utc)"]

    # Pre-meal glucose
    pre_glucose = glucose.loc[glucose["timestamp"] <= t0].tail(1)
    pre_val = pre_glucose["glucose"].values[0] if not pre_glucose.empty else np.nan

    # Post-meal glucose window (2h)
    post = glucose[(glucose["timestamp"] > t0) & (glucose["timestamp"] <= t0 + window)]
    if post.empty or np.isnan(pre_val):
        continue

    # Median interval (assume 5 min if missing)
    interval = post["timestamp"].diff().median()
    if pd.isna(interval):
        interval = pd.Timedelta("5min")
    minutes = interval.total_seconds() / 60

    # --- Outcome metrics ---
    g_vals = post["glucose"].values
    t_vals = (post["timestamp"] - t0).dt.total_seconds() / 60  # minutes since meal

    auc = np.trapz(g_vals, dx=minutes)
    delta = g_vals.max() - pre_val
    spike = int(g_vals.max() > pre_val + 30)

    # Time to peak
    peak_idx = g_vals.argmax()
    time_to_peak = t_vals.iloc[peak_idx] if len(t_vals) > 0 else np.nan

    # Duration above baseline (+10 mg/dL)
    above_mask = g_vals > (pre_val + 10)
    duration_above = above_mask.sum() * minutes

    # Time to return to baseline (±10 mg/dL of pre_val)
    return_mask = np.where(np.abs(g_vals - pre_val) <= 10)[0]
    time_to_return = np.nan
    if len(return_mask) > 0:
        time_to_return = t_vals.iloc[return_mask[0]]
    # If never returns in 2h window → censored (NaN)

    # Count major fluctuations (>±30 mg/dL swings relative to pre)
    fluct_mask = np.abs(g_vals - pre_val) > 30
    num_fluctuations = int(fluct_mask.sum())

    records.append({
        "meal_time": t0,
        "carbs": meal["carbs"],
        "fat": meal["fat"],
        "protein": meal["protein"],
        "fiber": meal["fiber"],
        "preMealGlucose": pre_val,
        "aucGlucose": auc,
        "deltaGlucose": delta,
        "spike": spike,
        "timeToPeak": time_to_peak,
        "durationAboveBaseline": duration_above,
        "timeToReturnBaseline": time_to_return,
        "numFluctuations": num_fluctuations
    })

df = pd.DataFrame(records)
out_path = os.path.join(base_dir, "MealEvents.csv")
df.to_csv(out_path, index=False)
print(f"✅ Saved MealEvents.csv with {len(df)} rows and new episode metrics")


df = pd.DataFrame(records)
out_path = os.path.join(base_dir, "MealEvents.csv")
df.to_csv(out_path, index=False)
print(f"✅ Saved MealEvents.csv with {len(df)} rows")
