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

# --- Population norm lookup ----------------------------------

def lookup_norm(name: str):
    norms = {
        "glucose_mean": {"mu": 100.0, "sigma": 10.0, "label": "24 h CGM reference"},
        "steps_sum": {"mu": 7500.0, "sigma": 3000.0, "label": "daily average"},
        "active_kcal": {"mu": 450.0, "sigma": 250.0, "label": "daily average"},
        "basal_kcal": {"mu": 1500.0, "sigma": 200.0, "label": "daily average"},
        "resting_hr_bpm": {"mu": 72.0, "sigma": 9.0, "label": "resting average"},
        "hrv_sdnn_ms": {"mu": 50.0, "sigma": 20.0, "label": "resting average"},
        "vo2max_ml_kg_min": {"mu": 38.5, "sigma": 7.0, "label": "population average"},
        "total_min": {"mu": 432.0, "sigma": 66.0, "label": "daily sleep"},
        "core_min": {"mu": 270.0, "sigma": 50.0, "label": "daily sleep"},
        "deep_min": {"mu": 80.0, "sigma": 30.0, "label": "daily sleep"},
        "rem_min": {"mu": 100.0, "sigma": 30.0, "label": "daily sleep"},
    }
    return norms.get(name.lower(), None)


# --- Helper to convert z-score -> percentile + emoji ----------

def percentile_from_z(z):
    from math import erf, sqrt
    pct = 50 * (1 + erf(z / sqrt(2)))
    if pct < 10 or pct > 90:
        flag = "🔴"
    elif pct < 25 or pct > 75:
        flag = "🟠"
    else:
        flag = "🟢"
    return pct, flag


# --- Write weekly report with clearer labels ------------------

def write_weekly_report(outdir, week_df, all_df, effects, week_range):
    lines = []
    start, end = week_range
    lines.append(f"# 🩺 Weekly Health Report ({start.date()} – {end.date()})\n")
    lines.append(f"Data coverage: {len(week_df)} / 7 days.\n")

    # --- COACH SUMMARY ---
    deltas = []
    for metric in ["steps_sum", "hrv_sdnn_ms", "deep_min", "glucose_mean"]:
        if metric in week_df.columns:
            mu_all = all_df[metric].mean()
            mu_week = week_df[metric].mean()
            change = (mu_week - mu_all) / mu_all * 100
            deltas.append((metric, change))
    summary = []
    if any(m == "steps_sum" and c > 10 for m, c in deltas):
        summary.append("You walked more than usual 🏃‍♀️ and kept strong activity.")
    if any(m == "hrv_sdnn_ms" and c > 5 for m, c in deltas):
        summary.append("Your recovery metrics (HRV) improved 💪.")
    if any(m == "glucose_mean" and c > 0 for m, c in deltas):
        summary.append("Glucose averaged slightly higher than your long-term norm ⚠️.")
    if any(m == "deep_min" and c < 0 for m, c in deltas):
        summary.append("Deep sleep dipped below your baseline 😴.")
    if not summary:
        summary.append("This week stayed close to your baseline across most systems.")
    lines.append("## Overview\n" + " ".join(summary) + "\n")

    # --- Per-domain metrics ---
    sections = {
        "Activity": ["steps_sum", "active_kcal"],
        "Cardiovascular": ["resting_hr_bpm", "hrv_sdnn_ms", "vo2max_ml_kg_min"],
        "Metabolic": ["glucose_mean"],
        "Sleep": ["total_min", "core_min", "deep_min", "rem_min"],
        "Energy": ["basal_kcal"],
    }

    for section, metrics in sections.items():
        lines.append(f"\n## {section}")
        for m in metrics:
            if m not in week_df.columns:
                continue
            mu_all = all_df[m].mean()
            mu_week = week_df[m].mean()
            pct_diff = (mu_week - mu_all) / mu_all * 100
            norm = lookup_norm(m)
            if norm:
                z = (mu_week - norm["mu"]) / norm["sigma"]
                pct, flag = percentile_from_z(z)
                label = norm.get("label", "")
                lines.append(
                    f"- **{m.replace('_',' ').title()}**: "
                    f"vs-self {pct_diff:+.1f}%  |  vs-population {pct:.0f}ᵗʰ pct ({label}) {flag}"
                )
            else:
                lines.append(f"- **{m}**: vs-self {pct_diff:+.1f}%")

    # --- Relationships ---
    lines.append("\n## Key Relationships")
    for _, row in effects.head(3).iterrows():
        pred, tgt = row["predictor"], row["target"]
        direction = "↑" if row["coef"] > 0 else "↓"
        lines.append(f"{direction} **{pred}** → {direction} **{tgt}** (p={row['p']:.3f})")

    (outdir / f"weekly_report_{start.date()}.md").write_text("\n".join(lines))
    print(f"✅ Weekly report written to {outdir}/weekly_report_{start.date()}.md")

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
    effects = pd.read_csv(effects_path) if effects_path.exists() else pd.DataFrame()
    norms = load_norm_bank()

    # pick most recent full week
    max_date = df["date"].max().normalize()
    start = max_date - timedelta(days=6)
    end = max_date

    # use the *new* write_weekly_report instead of summarize_week
    write_weekly_report(
        outdir=latest,
        week_df=df[(df["date"] >= start) & (df["date"] <= end)],
        all_df=df,
        effects=effects,
        week_range=(start, end),
    )

if __name__ == "__main__":
    main()

