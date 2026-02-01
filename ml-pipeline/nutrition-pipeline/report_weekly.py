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

import pandas as pd, numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from math import erf, sqrt

# ---------- Config ----------
ROOT = Path(__file__).parent.parent / "results"

# ---------- Metric metadata ----------
def metric_meta(metric: str):
    META = {
        "steps_sum": {
            "unit": "steps",
            "optimal": (8000, 12000),
            "direction": "higher",
            "pop": {"mu": 7500.0, "sigma": 3000.0, "label": "daily average"},
        },
        "active_kcal": {
            "unit": "kcal",
            "optimal": (350, 700),
            "direction": "higher",
            "pop": {"mu": 450.0, "sigma": 250.0, "label": "daily average"},
        },
        "basal_kcal": {
            "unit": "kcal",
            "optimal": (1300, 1800),
            "direction": "neutral",
            "pop": {"mu": 1500.0, "sigma": 200.0, "label": "daily average"},
        },
        "resting_hr_bpm": {
            "unit": "bpm",
            "optimal": (50, 70),
            "direction": "lower",
            "pop": {"mu": 72.0, "sigma": 9.0, "label": "resting average"},
        },
        "hrv_sdnn_ms": {
            "unit": "ms",
            "optimal": (60, 150),
            "direction": "higher",
            "pop": {"mu": 50.0, "sigma": 20.0, "label": "resting average"},
        },
        "vo2max_ml_kg_min": {
            "unit": "ml/kg/min",
            "optimal": (35, 55),
            "direction": "higher",
            "pop": {"mu": 38.5, "sigma": 7.0, "label": "population average"},
        },
        "glucose_mean": {
            "unit": "mg/dL",
            "optimal": (90, 105),
            "direction": "lower",
            "pop": {"mu": 100.0, "sigma": 10.0, "label": "24 h CGM reference"},
        },
        "total_min": {
            "unit": "min",
            "optimal": (420, 540),
            "direction": "mid",
            "pop": {"mu": 432.0, "sigma": 66.0, "label": "daily sleep"},
        },
        "core_min": {
            "unit": "min",
            "optimal": (240, 300),
            "direction": "mid",
            "pop": {"mu": 270.0, "sigma": 50.0, "label": "daily sleep"},
        },
        "deep_min": {
            "unit": "min",
            "optimal": (70, 120),
            "direction": "mid",
            "pop": {"mu": 80.0, "sigma": 30.0, "label": "daily sleep"},
        },
        "rem_min": {
            "unit": "min",
            "optimal": (90, 130),
            "direction": "mid",
            "pop": {"mu": 100.0, "sigma": 30.0, "label": "daily sleep"},
        },
    }
    return META.get(metric)

# ---------- Helpers ----------
def phi_percentile(z: float) -> float:
    return 50 * (1 + erf(z / sqrt(2)))

def fmt_pct(x: float) -> str:
    return f"{x:+.1f}%" if np.isfinite(x) else "—"

def fmt_val(x: float, unit: str) -> str:
    return f"{x:.1f} {unit}" if np.isfinite(x) else f"— {unit}"

def health_flag(metric: str, value: float):
    m = metric_meta(metric)
    if not m or not np.isfinite(value):
        return "⚪", "no reference available"
    low, high = m["optimal"]
    direction = m["direction"]
    if direction == "mid":
        if value < low: return "🟠", "below optimal range"
        if value > high: return "🟠", "above optimal range"
        return "🟢", "within optimal range"
    if direction == "higher":
        if value < low: return "🔴", "below optimal (more is better)"
        if value > high: return "🟢", "excellent (above optimal)"
        return "🟢", "within optimal range"
    if direction == "lower":
        if value > high: return "🔴", "above optimal (lower is better)"
        if value < low: return "🟢", "excellent (below optimal)"
        return "🟢", "within optimal range"
    return "🟢", "within typical range"

# ---------- Report writer ----------
def write_weekly_report(outdir, week_df, all_df, effects, week_range):
    start, end = week_range
    lines = [f"# 🩺 Weekly Health Report ({start.date()} – {end.date()})", f"Data coverage: {len(week_df)} / 7 days.", ""]

    # --- Overview ---
    deltas=[]
    for m in ["steps_sum","hrv_sdnn_ms","deep_min","glucose_mean"]:
        if m in week_df.columns:
            mu_all, mu_week = all_df[m].mean(), week_df[m].mean()
            if np.isfinite(mu_all) and mu_all: deltas.append((m,(mu_week-mu_all)/mu_all*100))
    summary=[]
    if any(m=="steps_sum" and c>10 for m,c in deltas): summary.append("You walked more than usual 🏃‍♀️ and kept strong activity.")
    if any(m=="hrv_sdnn_ms" and c>5 for m,c in deltas): summary.append("Your recovery metrics (HRV) improved 💪.")
    if any(m=="glucose_mean" and c>0 for m,c in deltas): summary.append("Glucose averaged slightly higher than your long-term norm ⚠️.")
    if any(m=="deep_min" and c<0 for m,c in deltas): summary.append("Deep sleep dipped below your baseline 😴.")
    if not summary: summary.append("This week stayed close to your baseline across most systems.")
    lines += ["## Overview", " ".join(summary), ""]

    sections={
        "Activity":["steps_sum","active_kcal"],
        "Cardiovascular":["resting_hr_bpm","hrv_sdnn_ms","vo2max_ml_kg_min"],
        "Metabolic":["glucose_mean"],
        "Sleep":["total_min","core_min","deep_min","rem_min"],
        "Energy":["basal_kcal"],
    }

    for sec,metrics in sections.items():
        lines.append(f"## {sec}")
        for m in metrics:
            if m not in week_df.columns: continue
            meta=metric_meta(m)
            unit=meta["unit"] if meta else ""
            mu_week, mu_all = week_df[m].mean(), all_df[m].mean()
            vs_self=((mu_week-mu_all)/mu_all*100) if (np.isfinite(mu_week) and np.isfinite(mu_all) and mu_all) else np.nan
            pop=meta.get("pop") if meta else None
            if pop and np.isfinite(mu_week):
                z=(mu_week-pop["mu"])/pop["sigma"]
                pct=phi_percentile(z)
                vs_pop=((mu_week-pop["mu"])/pop["mu"]*100)
                pop_txt=f"μ={pop['mu']:.1f}, σ={pop['sigma']:.1f} ({pop['label']})"
            else:
                pct=vs_pop=np.nan; pop_txt="—"
            lo,hi=meta["optimal"]; opt_txt=f"{lo:.0f}–{hi:.0f} {unit}"
            flag,status=health_flag(m,mu_week)
            name=m.replace("_"," ").title()
            lines += [
                f"- **{name}**",
                f"  - This week: {fmt_val(mu_week,unit)}",
                f"  - Your usual: {fmt_val(mu_all,unit)}",
                f"  - Change vs-self: {fmt_pct(vs_self)}",
                f"  - Change vs-population: {fmt_pct(vs_pop)} (percentile ≈ {pct:.0f}ᵗʰ; {pop_txt})",
                f"  - Optimal: {opt_txt}",
                f"  - Status: {flag} {status}",
            ]
        lines.append("")

    # --- Key relationships ---
    lines.append("## Key Relationships")
    if effects is not None and not effects.empty:
        eff=effects.sort_values(["p","target","predictor"]).round(3).head(3)
        for _,r in eff.iterrows():
            dirsym="↑" if r["coef"]>0 else "↓"
            lines.append(f"{dirsym} **{r['predictor']}** → {dirsym} **{r['target']}** (p={r['p']:.3f})")
    else:
        lines.append("_No significant effects detected._")

    (outdir/f"weekly_report_{start.date()}.md").write_text("\n".join(lines))
    print(f"✅ Weekly report written to {outdir}/weekly_report_{start.date()}.md")

# ---------- Core ----------
def load_latest_results(root=ROOT):
    dirs=sorted(root.glob("results_*"))
    if not dirs: raise FileNotFoundError("No results_* directories found.")
    latest=dirs[-1]
    print(f"📂 Using latest results: {latest}")
    return latest

def main():
    latest=load_latest_results()
    df=pd.read_csv(latest/"daily_features.csv",parse_dates=["date"])
    effects_path=latest/"all_effects.csv"
    effects=pd.read_csv(effects_path) if effects_path.exists() else pd.DataFrame()
    max_date=df["date"].max().normalize()
    start=max_date-timedelta(days=6)
    week_df=df[(df["date"]>=start)&(df["date"]<=max_date)]
    write_weekly_report(latest,week_df,df,effects,(start,max_date))

if __name__=="__main__":
    main()
