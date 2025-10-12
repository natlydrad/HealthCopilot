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
    all_stats = []
    num_cols = [c for c in df.columns if c != "date" and np.issubdtype(df[c].dtype, np.number)]
    lines = [f"# 🩺 Weekly Health Report ({start.date()} – {end.date()})", ""]
    lines.append(f"Data coverage: {len(week)} / 7 days.\n")

    for col in num_cols:
        week_mean = week[col].mean(skipna=True)
        all_mean = df[col].mean(skipna=True)
        if not np.isfinite(week_mean) or not np.isfinite(all_mean):
            continue
        change = ((week_mean - all_mean) / all_mean * 100) if all_mean else 0
        arrow = "↑" if change > 0 else ("↓" if change < 0 else "→")
        pct_str = f"{change:+.1f}%" if abs(change) >= 0.5 else "≈0%"
        desc = f"- **{col.replace('_',' ')}**: {arrow} {pct_str} vs all-time (avg {all_mean:.2f})."
        # Add population context if available
        if norms is not None:
            try:
                ref = lookup_norm(col, week_mean, norms=norms)
                if ref:
                    mean, sd, pct, src = ref
                    desc += f" → {pct:.0f}ᵗʰ percentile (ref μ={mean:.1f}, σ={sd:.1f})."
            except Exception:
                pass
        lines.append(desc)
        all_stats.append((col, change))
    lines.append("")

    # highlight top changes
    top = sorted(all_stats, key=lambda x: abs(x[1]), reverse=True)[:5]
    if top:
        lines.append("## Highlights")
        for col, ch in top:
            if abs(ch) >= 5:
                lines.append(f"✅ {col.replace('_',' ')} changed {ch:+.1f}% vs baseline.")
        lines.append("")

    # integrate effects for top levers
    if effects is not None and not effects.empty:
        sig = effects[effects["q"] < 0.05].copy()
        sig = sig.sort_values("q").groupby("target").head(2)
        if not sig.empty:
            lines.append("## Key Relationships")
            for _, r in sig.iterrows():
                direction = "↑" if r["coef"] > 0 else "↓"
                lines.append(f"{direction} **{r['predictor']}** → {direction if r['coef']>0 else '↓'} {r['target']} (p={r['p']:.3f}, q={r['q']:.3f})")
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

