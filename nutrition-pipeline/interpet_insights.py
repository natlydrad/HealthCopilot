#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
interpret_insights.py
Turns HealthCopilot Phase 3 outputs into human-readable insights.
"""

import json
import pandas as pd
from pathlib import Path
import numpy as np

# === CONFIG ===
RESULTS_DIR = sorted(Path("RESULTS").glob("results_*"))[-1]  # latest run
print(f"📂 Loading latest results from: {RESULTS_DIR}")

# === LOAD FILES ===
combined = json.load(open(RESULTS_DIR / "combined_models.json"))
sig_corrs = json.load(open(RESULTS_DIR / "significant_correlations.json"))
effects = pd.read_csv(RESULTS_DIR / "all_effects.csv")

# === INSIGHT ENGINE ===
lines = [f"# 🧠 HealthCopilot Insight Report\n", f"Source folder: `{RESULTS_DIR.name}`\n"]

# 1️⃣ Predictability ranking
dfm = pd.DataFrame([x["metrics"] | {"target": x["target"]} for x in combined])
dfm = dfm.sort_values("adj_r2", ascending=False)
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
    sub = effects[effects["target"] == tgt].sort_values("q").head(5)
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
    for name, r, p, q in d["top_pos"][:3]:
        lines.append(f"- Positive: **{name}** (r={r:+.2f}, q={q:.3f})")
    for name, r, p, q in d["top_neg"][:3]:
        lines.append(f"- Negative: **{name}** (r={r:+.2f}, q={q:.3f})")

# 4️⃣ Save report
out_path = RESULTS_DIR / "insight_report.md"
out_path.write_text("\n".join(lines))
print(f"\n✅ Insight report saved to: {out_path}")
print("Open it in VS Code / Obsidian / any markdown viewer!")
