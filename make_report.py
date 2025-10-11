# make_report.py
# Build a PDF report from a results folder and snapshot CSV inputs

import os, sys, json
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from datetime import datetime

# --- Get results folder from command-line ---
if len(sys.argv) < 2:
    print("Usage: python make_report.py <results_dir>")
    sys.exit(1)

results_dir = sys.argv[1]
timestamp = results_dir.split("results_")[-1]

print(f"📂 Generating report from: {results_dir}")

# --- Snapshot input CSVs into results folder ---
base_dir = os.path.dirname(__file__)
for fname in ["MealFeatures.csv", "MealEvents.csv"]:
    src = os.path.join(base_dir, fname)
    if os.path.exists(src):
        dst = os.path.join(results_dir, f"{os.path.splitext(fname)[0]}_{timestamp}.csv")
        pd.read_csv(src).to_csv(dst, index=False)
        print(f"📂 Copied {fname} → {dst}")

# --- Load metrics ---
metrics_path = os.path.join(results_dir, "metrics.json")
with open(metrics_path, "r") as f:
    metrics_summary = json.load(f)

# --- Build PDF ---
pdf_path = os.path.join(results_dir, f"model_report_{timestamp}.pdf")

with PdfPages(pdf_path) as pdf:

    # Cover page: metrics
    fig, ax = plt.subplots(figsize=(8.5, 11))
    ax.axis("off")
    ax.text(0.05, 0.95, f"HealthCopilot Model Report {timestamp}", fontsize=18, weight="bold", va="top")

    y_pos = 0.9
    for target, vals in metrics_summary.items():
        parts = []
        for k, v in vals.items():
            if isinstance(v, (int, float)):
                parts.append(f"{k}={v:.3f}")
            else:
                parts.append(f"{k}={v}")
        line = f"{target}: " + ", ".join(parts)
        ax.text(0.05, y_pos, line, fontsize=12, va="top")
        y_pos -= 0.05

    pdf.savefig(fig)
    plt.close(fig)

    # Following pages: SHAP plots
    for fname in sorted(os.listdir(results_dir)):
        if fname.endswith(".png"):
            img_path = os.path.join(results_dir, fname)
            img = plt.imread(img_path)
            fig, ax = plt.subplots(figsize=(8.5, 11))
            ax.imshow(img)
            ax.axis("off")
            ax.set_title(fname, fontsize=12)
            pdf.savefig(fig)
            plt.close(fig)

print(f"📄 PDF report saved at {pdf_path}")
