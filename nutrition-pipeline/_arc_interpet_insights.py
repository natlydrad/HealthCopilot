#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
interpret_insights.py
Turns HealthCopilot Phase 3 outputs into human-readable insights.
"""

import json, pandas as pd, numpy as np
from pathlib import Path

# === CONFIG ===
RESULTS_DIR = sorted(Path("RESULTS").glob("results_*"))[-1]  # latest run
print(f"📂 Loading latest results from: {RESULTS_DIR}")

# === LOAD FILES ===
combined = json.load(open(RESULTS_DIR / "combined_models.json"))
sig_corrs = json.load(open(RESULTS_DIR / "significant_correlations.json"))
effects = pd.read_csv(RESULTS_DIR / "all_effects.csv")

# ------------------------------------------------------------
# 🔹 Step 2 — helper to filter out self-derived features
# ------------------------------------------------------------
def is_self_derivation(tgt: str, pred: str) -> bool:
    """Treat variations of the target (lags / moving-averages) as self-derivations."""
    base = tgt.replace("_mean", "")
    return pred.startswith(base)

# === INSIGHT ENGINE ===
lines = [f"# 🧠 HealthCopilot Insight Report\n", f"Source folder: `{RESULTS_DIR.name}`\n"]

# 1️⃣ Predictability ranking
dfm = pd.DataFrame([x["metrics"] | {"target": x["target"]} for x in combined]).sort_values("adj_r2", ascending=False)
lines.append("\n## 📊 Model Predictability\n")
lines.append("| Rank | Target | R² | adjR² | AIC |\n|------|---------|----|--------|------|")
for i, row in enumerate(dfm.head(15).itertuples(), 1):
    lines.append(f"| {i} | {row.target} | {row.r2:.3f} | {row.adj_r2:.3f} | {row.aic:.1f} |")

mean_r2, med_r2 = dfm["r2"].mean(), dfm["r2"].median()
lines.append(f"\n**Mean R²:** {mean_r2:.3f} **Median R²:** {med_r2:.3f}\n")

# 2️⃣ Key effects per top target
lines.append("\n## 🔍 Top Model Insights\n")
for row in dfm.head(10).itertuples():
    tgt = row.target
    sub = (
        effects[effects["target"] == tgt]
        .sort_values("q")
        .query("q < 0.10")  # optional tighter filter
    )
    # remove self-derivatives
    sub = sub[~sub["predictor"].apply(lambda p: is_self_derivation(tgt, p))].head(5)

    lines.append(f"\n### 🎯 {tgt} (adjR²={row.adj_r2:.3f})")
    if sub.empty:
        lines.append("_No significant predictors found._\n")
        continue
    for _, e in sub.iterrows():
        direction = "↑" if e["coef"] > 0 else "↓"
        sig = "⭐" if e["q"] < 0.05 else ""
        lines.append(f"- {direction} **{e['predictor']}** → {tgt} ({e['coef']:+.3f}, q={e['q']:.3f}) {sig}")
    lines.append("")

# 3️⃣ Significant correlations summary
lines.append("\n## 🔗 Network-Like Correlations\n")
top_corrs = sorted(sig_corrs.items(),
                   key=lambda kv: len(kv[1]['top_pos']) + len(kv[1]['top_neg']),
                   reverse=True)[:10]

for tgt, d in top_corrs:
    lines.append(f"\n### {tgt}")
    # filter out trivial self-features
    pos = [(n, r, q) for (n, r, _, q) in d["top_pos"] if not is_self_derivation(tgt, n)][:3]
    neg = [(n, r, q) for (n, r, _, q) in d["top_neg"] if not is_self_derivation(tgt, n)][:3]
    for n, r, q in pos:
        lines.append(f"- Positive: **{n}** (r={r:+.2f}, q={q:.3f})")
    for n, r, q in neg:
        lines.append(f"- Negative: **{n}** (r={r:+.2f}, q={q:.3f})")

# 4️⃣ Save report
out_path = RESULTS_DIR / "insight_report.md"
out_path.write_text("\n".join(lines))
print(f"\n✅ Insight report saved to: {out_path}")
print("Open it in VS Code / Obsidian / any markdown viewer!")

# =========================
# ----- EXPERIMENTS! -----
# =========================

def _base_name(name: str) -> str:
    # strip common derivations to get the base signal
    n = name
    for tok in ["_3d_ma", "_7d_ma", "_3d_ma_7d_ma"]:
        n = n.replace(tok, "")
    # strip chained lags like _lag1_lag2_lag3 to just the first lag token
    n = n.split("_lag")[0] if "_lag" in n else n
    return n

def _latency_days(name: str) -> int:
    # e.g., "steps_sum_lag3" -> 3; chained forms -> use the smallest lag we see
    lags = []
    for part in name.split("_"):
        if part.startswith("lag"):
            try: lags.append(int(part[3:]))
            except: pass
    return min(lags) if lags else 0

def _pretty(name: str) -> str:
    out = name.replace("_", " ")
    out = out.replace("3d ma", "3-day avg").replace("7d ma", "7-day avg")
    out = out.replace("vo2max ml kg min", "VO₂max")
    out = out.replace("hrv sdnn ms", "HRV (SDNN)")
    out = out.replace("resting hr bpm", "Resting HR")
    out = out.replace("kcal", "kcal")
    out = out.replace("min", "min")
    # lag hint
    lat = _latency_days(name)
    if lat:
        out += f" (lag {lat}d)"
    return out

def is_controllable(base: str) -> bool:
    # direct behavioral levers you can change today
    CONTROLLABLE = {
        "steps_sum", "active_kcal",
        "total_min", "core_min", "deep_min", "rem_min",  # sleep mins
        # add more levers you want to tinker with:
        # "bedtime", "wake_time", "fiber_g", "water_intake", ...
    }
    return base in CONTROLLABLE

# Load daily features for baselines (optional but helpful)
try:
    daily = pd.read_csv(RESULTS_DIR / "daily_features.csv", parse_dates=["date"])
except Exception:
    daily = None

def _suggest_magnitude(col: str) -> str:
    if daily is None or col not in daily.columns:
        return "by a **meaningful but sustainable** amount"
    s = daily[col].dropna()
    if s.empty: return "by a **meaningful but sustainable** amount"
    step = np.nanpercentile(s, 75) - np.nanpercentile(s, 25)  # IQR as a safe nudge
    if step <= 0 or not np.isfinite(step):
        return "by a **meaningful but sustainable** amount"
    # round to a friendly value
    if "steps" in col:
        step = int(round(step / 500.0) * 500) or 500
        return f"by **~{step} steps/day**"
    if "kcal" in col:
        step = int(round(step / 50.0) * 50) or 50
        return f"by **~{step} kcal/day**"
    if col.endswith("_min") or "min" in col:
        step = int(round(step / 10.0) * 10) or 10
        return f"by **~{step} min/day**"
    # generic %
    pct = 0.15  # 15% nudge
    return f"by **~{int(pct*100)}%**"

plan_lines = ["# 🧪 N-of-1 Experiment Plan\n",
              f"_Generated from `{RESULTS_DIR.name}`_\n"]

# Work off the same dfm/effects already loaded
TOP_N_TARGETS = 6
MAX_LEVERS_PER_TARGET = 3
Q_CUTOFF = 0.10

any_added = False

for row in dfm.head(TOP_N_TARGETS).itertuples():
    tgt = row.target

    # candidate levers: significant, not self-derivation, controllable bases
    cand = (
        effects[effects["target"] == tgt]
        .copy()
        .sort_values("q")
    )
    if "q" not in cand.columns:
        continue
    cand = cand[cand["q"] < Q_CUTOFF]
    if cand.empty: 
        continue

    # filter out self-derivatives of target
    cand = cand[~cand["predictor"].apply(lambda p: is_self_derivation(tgt, p))]

    # keep only controllables (by base name)
    cand["base"] = cand["predictor"].apply(_base_name)
    cand = cand[cand["base"].apply(is_controllable)]
    if cand.empty:
        continue

    # rank by q then effect size
    cand = cand.sort_values(["q", "coef"], ascending=[True, False]).head(MAX_LEVERS_PER_TARGET)

    # format section
    plan_lines.append(f"\n## {tgt} (adjR²={row.adj_r2:.3f})")
    plan_lines.append(f"- **Goal metric:** daily `{tgt}`")
    plan_lines.append("- **Design:** 14 days → **7-day baseline** (no change), then **7-day intervention**")
    plan_lines.append("- **Tracking:** 7-day rolling mean, day-to-day deltas, annotate weekends")
    plan_lines.append("- **Success:** Baseline vs intervention mean improves in desired direction; sanity-check with a simple OLS on days 1..14 with an intervention dummy.\n")

    for _, e in cand.iterrows():
        direction = "increase" if e["coef"] > 0 else "decrease"
        lat = _latency_days(e["predictor"])
        latency_note = f" (expect effect after ~{lat} day{'s' if lat!=1 else ''})" if lat else ""
        magnitude = _suggest_magnitude(e["predictor"])
        pretty_pred = _pretty(e["predictor"])
        star = " ⭐" if e["q"] < 0.05 else ""
        plan_lines.append(
            f"- **Intervention:** {direction} **{pretty_pred}** {magnitude}{latency_note} "
            f"(model coef {e['coef']:+.3f}, q={e['q']:.3f}){star}"
        )

    plan_lines.append(
        "\n**Confounders to log:** illness, travel, caffeine, alcohol, unusually hard workouts, "
        "late meals, menstrual cycle phase.\n"
    )
    any_added = True

if not any_added:
    plan_lines.append("\n_No immediately actionable levers with q < 0.10 were found among controllables. "
                      "Try relaxing the threshold or add more controllable features (e.g., fiber, water, bedtime)._")

exp_path = RESULTS_DIR / "experiment_plan.md"
exp_path.write_text("\n".join(plan_lines))
print(f"🧪 Experiment plan saved to: {exp_path}")
