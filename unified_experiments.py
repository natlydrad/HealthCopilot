#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
unified_experiments.py
Reads the Phase 3 outputs and writes ONE human-readable Markdown:
- Overview of data + analysis
- Top correlations and model metrics
- Actionable N-of-1 experiment plans
"""

import json, numpy as np, pandas as pd
from pathlib import Path
from datetime import datetime

# ---------- CONFIG ----------
RESULTS_DIR = sorted(Path("RESULTS").glob("results_*"))[-1]
OUT = RESULTS_DIR / f"report_phase3_experiments.md"

# Behavioral levers you can actually change
ACTIONABLE = {
    "steps_sum", "sleep_hours", "bedtime_hour", "waketime_hour",
    "fiber_g", "protein_g", "added_sugar_g", "sat_fat_g",
    "water_l", "eating_window_h", "late_meal_count", "alcohol_units",
    "outdoor_minutes", "meditation_min", "screen_time_h"
}

def emoji_confidence(q):
    if q < 0.01: return "💎 Strong"
    if q < 0.05: return "⭐ Moderate"
    if q < 0.10: return "⚪ Suggestive"
    return "❔ Weak"

# ---------- LOAD RESULTS ----------
print(f"📂 Reading latest results from {RESULTS_DIR}")
daily = pd.read_csv(RESULTS_DIR / "daily_features.csv", parse_dates=["date"])
effects = pd.read_csv(RESULTS_DIR / "all_effects.csv")
combined = json.load(open(RESULTS_DIR / "combined_models.json"))
sig_corrs = json.load(open(RESULTS_DIR / "significant_correlations.json"))

lines = []

# ================================================================
# 1️⃣ Overview
# ================================================================
n_days = len(daily)
n_feats = len(daily.columns)
n_targets = len(combined)
lines += [
    "# 📊 Phase 3 → N-of-1 Summary",
    "",
    f"- **Days analyzed:** {n_days}",
    f"- **Features:** {n_feats}",
    f"- **Targets modeled:** {n_targets}",
    "",
    "We ran:",
    "1. Descriptive correlations (Pearson r + FDR)",
    "2. OLS + HAC regressions per target",
    "3. Behavioral-lever filter → N-of-1 experiments",
    "",
    "---",
]

# ================================================================
# 2️⃣ Descriptive correlations
# ================================================================
lines += ["## 🔗 Strongest correlations", ""]
count = 0
for tgt, d in sig_corrs.items():
    pos = d.get("top_pos", [])[:2]
    neg = d.get("top_neg", [])[:2]
    for name, r, p, q in pos + neg:
        if abs(r) >= 0.25 and q < 0.05:
            lines.append(f"- **{tgt}** ↔ **{name}** (r = {r:+.2f}, q = {q:.3f})")
            count += 1
    if count > 12: break
lines.append("")
lines.append("---")

# ================================================================
# 3️⃣ Model-based insights
# ================================================================
lines += ["## 📈 Model performance", ""]
dfm = pd.DataFrame([x["metrics"] | {"target": x["target"]} for x in combined])
dfm = dfm.sort_values("adj_r2", ascending=False)
for i, r in enumerate(dfm.head(8).itertuples(), 1):
    lines.append(f"{i}. **{r.target}** — adj R² = {r.adj_r2:.3f}")
lines += ["", "---"]

# ================================================================
# 4️⃣ Actionable Experiments
# ================================================================
lines += ["## 🧪 Experiments you can actually run", ""]

# Filter for top predictors per target that are actionable
for tgt in dfm.head(8)["target"]:
    sub = effects.query("target == @tgt").copy()
    sub = sub[sub["predictor"].isin(ACTIONABLE)]
    sub = sub[sub["q"] < 0.10]
    if sub.empty: 
        continue

    med = float(np.nanmedian(daily[tgt])) if tgt in daily else np.nan
    lines.append(f"### 🎯 Goal: optimize **{tgt}** (median ≈ {med:.1f})")
    for _, row in sub.sort_values("q").head(3).iterrows():
        direction = "increase" if row["coef"] > 0 else "decrease"
        conf = emoji_confidence(row["q"])
        lines.append(
            f"- {conf} evidence: {direction} **{row['predictor']}** → {tgt} "
            f"(coef ={row['coef']:+.3f}, q ={row['q']:.3f})"
        )

        # Rough design rule-of-thumb
        if "steps" in row["predictor"]:
            lines.append("  - Design: Stepped 4-week program (+2k → +3k → maintain).")
        else:
            lines.append("  - Design: ABAB 2-day blocks (A = usual, B = apply change).")

    lines.append("")

# ================================================================
# 5️⃣ Save output
# ================================================================
OUT.write_text("\n".join(lines))
print(f"✅ Wrote {OUT}")
