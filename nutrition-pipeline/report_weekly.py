#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
report_weekly.py — Human-readable weekly health report

Reads your latest RESULTS folder and produces:
  weekly_report_<startdate>.md

Comparison:
  - Last 7 days vs. full-dataset average
  - Adds percentile (if norms_param.csv found)
  - Lists top significant levers from all_effects.csv

Usage:
  python report_weekly.py
"""

import pandas as pd, numpy as np, json, math, os
from pathlib import Path
from datetime import datetime, timedelta
from math import erf, sqrt

# ---------- Config ----------
ROOT = Path("/Users/natalieradu/Desktop/HealthCopilot/RESULTS")
AGE, SEX = 22, "f"

# ---------- Norm utilities (copied from your n1_experiments) ----------
def load_norm_bank(path="norms_param.csv"):
    p = Path(path)
    if not p.exists(): return None
    return pd.read_csv(p)

def lookup_norm(metric, value, age=AGE, sex=SEX, norms=None):
    if norms is None or norms.empty or metric not in norms.metric.values:
        return None
    ref = norms[(norms.metric == metric) &
                (norms.age_min <= age) & (norms.age_max >= age) &
                (norms.sex.str.lower().isin([sex.lower(), "any", "all"]))]

    if ref.empty: return None
    ref = ref.iloc[0]
    mean, sd = float(ref["mean"]), float(ref["sd"])
    z = (value - mean) / sd if sd > 0 else 0
    pct = 0.5 * (1 + erf(z / sqrt(2))) * 100
    return mean, sd, pct, ref.get("source", "")

# ---------- Core ----------
def load_latest_results(root=ROOT):
    dirs = sorted(root.glob("results_*"))
    if not dirs:
        raise FileNotFoundError("No results_* directories found.")
    latest = dirs[-1]
    print(f"📂 Using latest results: {latest}")
    return latest

def summarize_week(df, start, norms=None, effects=None):
    end = start + timedelta(days=6)
    week = df[(df["date"] >= start) & (df["date"] <= end)]
    if week.empty:
        return f"_No data for week starting {start.date()}._"

    # === only keep core metrics ===
    KEEP = [
        "steps_sum", "active_kcal", "basal_kcal",
        "resting_hr_bpm", "hrv_sdnn_ms", "vo2max_ml_kg_min",
        "glucose_mean", "sleep_hours", "rem_min", "deep_min", "core_min", "total_min"
    ]
    df = df[[c for c in df.columns if c in KEEP or c == "date"]]
    week = week[[c for c in week.columns if c in KEEP or c == "date"]]

    CATEGORIES = {
        "Activity": ["steps_sum", "active_kcal"],
        "Cardiovascular": ["resting_hr_bpm", "hrv_sdnn_ms", "vo2max_ml_kg_min"],
        "Metabolic": ["glucose_mean"],
        "Sleep": ["sleep_hours", "rem_min", "deep_min", "core_min", "total_min"],
        "Energy": ["basal_kcal"]
    }

    PRETTY = {
        "steps_sum": "Daily steps",
        "active_kcal": "Active calories",
        "basal_kcal": "Basal calories",
        "resting_hr_bpm": "Resting HR",
        "hrv_sdnn_ms": "HRV (SDNN)",
        "vo2max_ml_kg_min": "VO₂max",
        "glucose_mean": "Mean glucose",
        "sleep_hours": "Sleep hours",
        "rem_min": "REM sleep (min)",
        "deep_min": "Deep sleep (min)",
        "core_min": "Core sleep (min)",
        "total_min": "Total sleep (min)"
    }

    lines = [f"# 🩺 Weekly Health Report ({start.date()} – {end.date()})", ""]
    lines.append(f"Data coverage: {len(week)} / 7 days.\n")

    # === loop by category ===
    for cat, cols in CATEGORIES.items():
        section_lines = []
        for col in cols:
            if col not in df.columns: 
                continue
            week_mean = week[col].mean(skipna=True)
            all_mean = df[col].mean(skipna=True)
            if not np.isfinite(week_mean) or not np.isfinite(all_mean): 
                continue
            change = ((week_mean - all_mean) / all_mean * 100) if all_mean else 0
            arrow = "↑" if change > 0 else ("↓" if change < 0 else "→")
            pct_str = f"{change:+.1f}%" if abs(change) >= 0.5 else "≈0%"
            desc = f"- **{PRETTY[col]}**: {arrow} {pct_str} vs all-time (avg {all_mean:.1f})."

            # Add percentile context if available
            if norms is not None:
                try:
                    ref = lookup_norm(col, week_mean, norms=norms)
                    if ref:
                        mean, sd, pct, src = ref
                        desc += f" → {pct:.0f}ᵗʰ percentile (ref μ={mean:.1f}, σ={sd:.1f})."
                        if pct < 25:
                            desc += " ⚠️ below norm."
                        elif pct > 75:
                            desc += " ✅ above norm."
                except Exception:
                    pass
            section_lines.append(desc)

        if section_lines:
            lines.append(f"## {cat}")
            lines += section_lines
            lines.append("")

    # === top 3 significant levers ===
    if effects is not None and not effects.empty:
        sig = effects[effects["q"] < 0.05].sort_values("q").head(3)
        if not sig.empty:
            lines.append("## Key Relationships")
            for _, r in sig.iterrows():
                dir_symbol = "↑" if r["coef"] > 0 else "↓"
                lines.append(f"{dir_symbol} **{r['predictor']}** → {dir_symbol if r['coef']>0 else '↓'} {r['target']} (p={r['p']:.3f}, q={r['q']:.3f})")
            lines.append("")
    return "\n".join(lines)


def main():
    latest = load_latest_results()
    df = pd.read_csv(latest / "daily_features.csv", parse_dates=["date"])
    effects_path = latest / "all_effects.csv"
    effects = pd.read_csv(effects_path) if effects_path.exists() else None
    norms = load_norm_bank()

    # pick most recent full week
    max_date = df["date"].max().normalize()
    start = max_date - timedelta(days=6)
    out = summarize_week(df, start, norms=norms, effects=effects)
    out_path = latest / f"weekly_report_{start.date()}.md"
    out_path.write_text(out)
    print(f"📝 Weekly report saved to {out_path}")

if __name__ == "__main__":
    main()

