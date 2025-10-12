
import pandas as pd, numpy as np
from pathlib import Path
from math import erf, sqrt
from typing import Dict, Optional

# ----------------- Helpers -----------------

def _pick_ref(df: pd.DataFrame, metric: str, age: int, sex: str) -> Optional[pd.Series]:
    if df is None or df.empty: 
        return None
    cand = df[(df["metric"]==metric) &
              (df["age_min"]<=age) & (df["age_max"]>=age) &
              (df["sex"].str.lower().isin([sex.lower(),"any","all"]))]
    if cand.empty:
        return None
    cand = cand.sort_values(["age_max","age_min"])
    return cand.iloc[0]

def _percentile_from_param(x: float, mean: float, sd: float) -> float:
    if not np.isfinite(x) or not np.isfinite(mean) or not np.isfinite(sd) or sd <= 0:
        return np.nan
    z = (x - mean) / sd
    return 0.5*(1.0 + erf(z / sqrt(2))) * 100.0

def _band(percentile: float, better_if: str) -> str:
    if not np.isfinite(percentile):
        return "Unknown"
    b = (better_if or "range").lower()
    if b == "higher":
        return "Green" if percentile >= 75 else ("Amber" if percentile >= 50 else "Red")
    if b == "lower":
        return "Green" if percentile <= 25 else ("Amber" if percentile <= 50 else "Red")
    # neutral/range → IQR treated as green
    return "Green" if 25 <= percentile <= 75 else ("Amber" if 10 <= percentile <= 90 else "Red")

def _fmt(x, nd=2):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{x:.{nd}f}" if isinstance(x, float) else str(x)

# ----------------- Public API -----------------

def summarize_user(daily: pd.DataFrame, metrics, window_days: int = 90) -> pd.DataFrame:
    df = daily.copy()
    if "date" in df.columns:
        df = df.sort_values("date").tail(window_days)
    rows = []
    for m in metrics:
        if m not in df.columns: 
            continue
        ser = pd.to_numeric(df[m], errors="coerce").dropna()
        if ser.empty: 
            continue
        rows.append({"metric": m, "you_mean": ser.mean(), "you_sd": ser.std(ddof=1), "n_days": int(ser.shape[0])})
    return pd.DataFrame(rows)

def load_norms(param_csv: Path) -> pd.DataFrame:
    if param_csv and param_csv.exists():
        return pd.read_csv(param_csv)
    # empty fallback
    return pd.DataFrame(columns=["domain","metric","age_min","age_max","sex","mean","sd","unit","source"])

def compare_to_norms(daily: pd.DataFrame, age: int, sex: str,
                     norms_param: pd.DataFrame,
                     metric_prefs: Dict[str, str],
                     pretty_names: Dict[str, str],
                     unit_map: Dict[str, str],
                     window_days: int = 90) -> pd.DataFrame:
    summary = summarize_user(daily, list(metric_prefs.keys()), window_days)
    out = []
    for _, r in summary.iterrows():
        m = r["metric"]; x = float(r["you_mean"])
        ref = _pick_ref(norms_param, m, age, sex)
        perc = np.nan; ref_mean = np.nan; ref_sd = np.nan; source = None
        if ref is not None:
            ref_mean, ref_sd = float(ref["mean"]), float(ref["sd"])
            perc = _percentile_from_param(x, ref_mean, ref_sd)
            source = ref.get("source", None)
        better_if = metric_prefs.get(m, "range")
        out.append({
            "metric": m,
            "label": pretty_names.get(m, m.replace("_"," ")),
            "unit": unit_map.get(m, ""),
            "you_mean": x,
            "ref_mean": ref_mean,
            "ref_sd": ref_sd,
            "percentile": None if not np.isfinite(perc) else float(np.round(perc,1)),
            "band": _band(perc, better_if),
            "n_days": int(r["n_days"]),
            "better_if": better_if,
            "source": source
        })
    return pd.DataFrame(out).sort_values("metric")

def render_markdown(table: pd.DataFrame, asof: str) -> str:
    lines = [f"# 🌍 How You Compare to the General Population ({asof})\n"]
    sections = [
        ("Cardio & Fitness", ["vo2max_ml_kg_min","resting_hr_bpm","hrv_sdnn_ms","steps_sum","active_kcal","basal_kcal"]),
        ("Metabolic", ["glucose_mean","glucose_cv_pct"]),
        ("Sleep", ["sleep_duration_h","total_min","core_min","deep_min","rem_min","sleep_efficiency_pct"]),
    ]
    def line_for(row):
        mean_str = _fmt(row["you_mean"])
        unit = f" {row['unit']}" if row["unit"] else ""
        pct = f"{_fmt(row['percentile'],1)}th pct" if np.isfinite(row["percentile"]) else "no ref"
        band = row["band"]
        ref = f"(ref μ={_fmt(row['ref_mean'])}{unit}, σ={_fmt(row['ref_sd'])})" if np.isfinite(row["ref_mean"]) else "(no ref)"
        # Simple human message
        status = {
            "Green": "within/healthy",
            "Amber": "borderline",
            "Red": "outside typical range",
            "Unknown": "no reference"
        }.get(band, "—")
        return f"- **{row['label']}**: {mean_str}{unit} → *{pct}*, **{band}** — {status} {ref}."
    for title, keys in sections:
        subset = table[table["metric"].isin(keys)]
        if subset.empty: 
            continue
        lines.append(f"\n## {title}\n")
        for _, row in subset.iterrows():
            lines.append(line_for(row))
    # Catch-all for anything not listed
    other = table[~table["metric"].isin(sum([k for _,k in sections], []))]
    if not other.empty:
        lines.append("\n## Other\n")
        for _, row in other.iterrows():
            lines.append(line_for(row))
    lines.append("\n_Notes: ‘percentile’ compares your 90‑day average to reference data. "
                 "Green means good for the stated direction; Amber is borderline; Red needs attention._")
    return "\n".join(lines)
