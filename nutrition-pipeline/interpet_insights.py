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
