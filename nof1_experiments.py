#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
<<<<<<< HEAD
n1_experiments.py
Plan and evaluate simple N-of-1 experiments using your existing daily_features.csv.
- Generates a randomized schedule CSV with baseline/intervention flags
- Provides a clean log template (CSV) to record adherence notes (optional)
- Evaluates effect with:
    A) Difference-in-means (Newey-West / HAC SE)
    B) Interrupted time series OLS: y ~ time + post + post*time + DOW + weekend + AR-ish controls
"""

import json, math, numpy as np, pandas as pd
from pathlib import Path
import statsmodels.api as sm
from datetime import datetime, timedelta

RESULTS_DIR = sorted(Path("RESULTS").glob("results_*"))[-1]       # latest run folder
DF_PATH      = RESULTS_DIR / "daily_features.csv"
CONF_PATH    = Path("experiments_config.json")

OUT_PLAN     = RESULTS_DIR / "n1_schedule.csv"
OUT_LOG      = RESULTS_DIR / "n1_log_template.csv"
OUT_SUMMARY  = RESULTS_DIR / "n1_results_summary.md"

def _normalize_date(s: pd.Series) -> pd.Series:
    # Make everything comparable: parse as UTC if needed, then drop tz to get naive
    return pd.to_datetime(s, utc=True, errors="coerce").dt.tz_localize(None)
=======
n1_experiments.py — Coach-style N-of-1 planner + (optional) evaluator

Adds:
- Filters to remove self/derived features (e.g., *_3d_ma, *_7d_ma) and non-actionable levers
- Behavioral lever whitelist (steps, sleep, alcohol, late meals, etc.)
- Redundancy guard for additive components (e.g., active_kcal/basal_kcal vs energy_score)
- ABAB explanation (what A/B mean, total days)
- Healthy-range note when baseline is already “good”
- Timestamped single Markdown output
"""

import json, math, os
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np, pandas as pd
import statsmodels.api as sm

# ---------- Normative helper (optional Phase 4 integration) ----------
def load_norm_bank(path="norms_param.csv"):
    import pandas as pd
    p = Path(path)
    if not p.exists(): return None
    return pd.read_csv(p)

def lookup_norm(metric, age=22, sex="f", norms=None):
    """Return (ref_mean, ref_sd, percentile, note) if available."""
    import numpy as np
    from math import erf, sqrt
    if norms is None or norms.empty: return None
    ref = norms[(norms.metric == metric) &
                (norms.age_min <= age) & (norms.age_max >= age) &
                (norms.sex.str.lower().isin([sex.lower(), "any", "all"]))]

    if ref.empty: return None
    ref = ref.iloc[0]
    mean, sd = float(ref["mean"]), float(ref["sd"])
    def pct(x):
        z = (x - mean) / sd
        return 0.5 * (1 + erf(z / sqrt(2))) * 100
    return mean, sd, pct, ref.get("source", "")


# ============================================================
#  🔍 Load results + shared helpers (from interpret_insights)
# ============================================================

RESULTS_DIR = sorted(Path("RESULTS").glob("results_*"))[-1]
print(f"📂 Using latest results: {RESULTS_DIR}")

effects = pd.read_csv(RESULTS_DIR / "all_effects.csv")
combined = json.load(open(RESULTS_DIR / "combined_models.json"))
sig_corrs = json.load(open(RESULTS_DIR / "significant_correlations.json"))
try:
    daily = pd.read_csv(RESULTS_DIR / "daily_features.csv", parse_dates=["date"])
except Exception:
    daily = None

# ---------- Helper functions ----------

def _base_name(name: str) -> str:
    for tok in ["_3d_ma", "_7d_ma", "_3d_ma_7d_ma", "_lag1", "_lag2", "_lag3"]:
        name = name.replace(tok, "")
    return name

def _latency_days(name: str) -> int:
    lags = [int(p[3:]) for p in name.split("_") if p.startswith("lag") and p[3:].isdigit()]
    return min(lags) if lags else 0

def _pretty(name: str) -> str:
    out = name.replace("_", " ")
    out = out.replace("vo2max ml kg min", "VO₂max")
    out = out.replace("hrv sdnn ms", "HRV (SDNN)")
    out = out.replace("resting hr bpm", "Resting HR")
    lat = _latency_days(name)
    if lat:
        out += f" (lag {lat}d)"
    return out

def is_controllable(base: str) -> bool:
    CONTROLLABLE = {
        "steps_sum", "sleep_hours", "fiber_g", "protein_g", "added_sugar_g",
        "sat_fat_g", "water_l", "eating_window_h", "alcohol_units",
        "outdoor_minutes", "meditation_min", "screen_time_h",
        "total_min", "core_min", "deep_min", "rem_min"
    }
    return base in CONTROLLABLE

def _suggest_magnitude(col: str) -> str:
    if daily is None or col not in daily.columns:
        return "by a **meaningful but sustainable** amount"
    s = daily[col].dropna()
    if s.empty:
        return "by a **meaningful but sustainable** amount"
    step = np.nanpercentile(s, 75) - np.nanpercentile(s, 25)
    if step <= 0 or not np.isfinite(step):
        return "by a **meaningful but sustainable** amount"
    if "steps" in col:
        step = int(round(step / 500.0) * 500) or 500
        return f"by **~{step} steps/day**"
    if "kcal" in col:
        step = int(round(step / 50.0) * 50) or 50
        return f"by **~{step} kcal/day**"
    if col.endswith("_min") or "min" in col:
        step = int(round(step / 10.0) * 10) or 10
        return f"by **~{step} min/day**"
    return "by **~15%**"

# ============================================================
#  🧠 Experiment generation core (your existing logic)
# ============================================================

DF_PATH = RESULTS_DIR / "daily_features.csv"
CONF_PATH = Path("experiments_config.json")

timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
OUT_DOC = RESULTS_DIR / f"experiment_plan_{timestamp}.md"

# ---------- Thresholds ----------
MIN_ABS_R = 0.25
MAX_Q = 0.05
MAX_EXPS_PER_TARGET = 2
DEFAULT_START_OFFSET_DAYS = 1

# ---------- Metadata ----------
BETTER_DIRECTION = {
    "glucose_mean": "lower", "glucose_auc": "lower", "glucose_cv": "lower",
    "resting_hr_bpm": "lower", "energy_score": "higher", "mood_score": "higher",
    "sleep_hours": "higher", "hrv_sdnn_ms": "higher", "rem_min": "higher",
    "deep_min": "higher", "core_min": "higher", "total_min": "higher",
}

LEVER_NAME = {
    "steps_sum": "daily steps", "sleep_hours": "sleep duration",
    "rem_min": "REM minutes", "deep_min": "deep sleep minutes",
    "bedtime_hour": "bedtime", "waketime_hour": "wake time",
    "vo2max_ml_kg_min": "VO₂max (cardio fitness)", "hrv_sdnn_ms": "HRV (SDNN)",
    "resting_hr_bpm": "resting heart rate", "fiber_g": "fiber",
    "protein_g": "protein", "added_sugar_g": "added sugar", "sat_fat_g": "saturated fat",
    "water_l": "water intake", "eating_window_h": "eating window",
    "late_meal_count": "late meals", "alcohol_units": "alcohol",
    "outdoor_minutes": "outdoor time", "meditation_min": "meditation",
    "screen_time_h": "evening screen time",
    "active_kcal": "active kcal", "basal_kcal": "basal kcal", "energy_score": "energy score",
    "glucose_mean": "glucose mean",
}

TARGET_INFO = {
    "rem_min": {
        "why": "REM sleep supports memory, emotional regulation, and learning. Low REM can indicate stress or circadian disruption.",
        "healthy_range": "Adults typically spend 20–25% of total sleep in REM (~90–120 min/night).",
        "external_levers": ["total sleep", "consistent bedtime", "exercise", "reduced alcohol"],
    },
    "glucose_mean": {
        "why": "Lower mean glucose indicates better insulin sensitivity and lower risk for metabolic and cognitive issues.",
        "healthy_range": "Fasting <100 mg/dL and daily mean <105 mg/dL are excellent.",
        "external_levers": ["steps", "fiber intake", "sleep", "meal timing", "alcohol"],
    },
    "resting_hr_bpm": {
        "why": "Lower resting HR generally reflects higher fitness and better autonomic balance.",
        "healthy_range": "Typical 60–80 bpm; trained individuals may be 45–60 bpm.",
        "external_levers": ["aerobic activity", "sleep quality", "stress reduction"],
    },
    "hrv_sdnn_ms": {
        "why": "Higher HRV reflects better parasympathetic tone and recovery.",
        "healthy_range": "Highly individual; aim for upward trend vs your baseline.",
        "external_levers": ["sleep, stress reduction, moderate cardio, alcohol moderation"],
    },
}

# ... [keep the rest of your code (filters, evaluation, write_markdown, main)] ...

# Actionable levers (we can instruct user to change these)
BEHAVIORAL_LEVERS = {
    "steps_sum", "sleep_hours", "bedtime_hour", "waketime_hour",
    "fiber_g", "protein_g", "added_sugar_g", "sat_fat_g",
    "water_l", "eating_window_h", "late_meal_count", "alcohol_units",
    "outdoor_minutes", "meditation_min", "screen_time_h", "vo2max_ml_kg_min"
}

# Suffixes marking derived/rolling features we should not treat as levers
DERIVED_SUFFIXES = ("_3d_ma", "_7d_ma", "_ma", "_ema", "_roll", "_rolling")

# Known additive/component redundancies to avoid (target -> lever to skip)
REDUNDANT_COMPONENTS = {
    ("energy_score", "active_kcal"),
    ("energy_score", "basal_kcal"),
}

# ---------- Utilities ----------
def _normalize_date(s): return pd.to_datetime(s, utc=True, errors="coerce").dt.tz_localize(None)
def _human(var): return LEVER_NAME.get(var, var.replace("_"," "))
def _base_name(v: str) -> str:
    for suf in DERIVED_SUFFIXES:
        if v.endswith(suf): return v[: -len(suf)]
    return v

def _recommend_direction(target, r):
    better = BETTER_DIRECTION.get(target)
    if better == "lower": return "decrease" if r > 0 else "increase"
    if better == "higher": return "increase" if r > 0 else "decrease"
    return "increase" if r > 0 else "decrease"
>>>>>>> ebf6a02

def load_daily():
    df = pd.read_csv(DF_PATH, parse_dates=["date"])
    df["date"] = _normalize_date(df["date"])
<<<<<<< HEAD
    # ensure helpers exist
    if "dow" not in df: df["dow"] = df["date"].dt.dayofweek
    if "is_weekend" not in df: df["is_weekend"] = (df["dow"]>=5).astype(int)
    return df

def iqr_nudge(df, col, multiplier=0.5):
    s = df[col].dropna()
    if s.empty: return None
    q1, q3 = np.nanpercentile(s, 25), np.nanpercentile(s, 75)
    iqr = q3 - q1
    if not np.isfinite(iqr) or iqr <= 0: return None
    return multiplier * iqr

def plan_schedule(exp, df):
    start = pd.Timestamp(exp["start_date"])
    # assume start date is local/naive → treat as UTC for alignment, then strip tz
    start = pd.to_datetime(start, utc=True).tz_localize(None)

    n0 = int(exp["days_baseline"]); n1 = int(exp["days_intervention"])
    days = [start + pd.Timedelta(days=i) for i in range(n0+n1)]

    sch = pd.DataFrame({"date": days})
    sch["phase"] = ["baseline"]*n0 + ["intervention"]*n1
    sch["intervention"] = (sch["phase"]=="intervention").astype(int)

    rule = exp.get("adherence_rule", {"type":"relative_iqr", "multiplier":0.5})
    sch.attrs["adherence_rule"] = f"relative_iqr × {rule.get('multiplier', 0.5)}"
    return sch


def export_templates(schedule, exp, df):
    cols = [c for c in [exp["lever"], exp["target"]] if c in df.columns]

    # Both sides are already UTC-naive (see load_daily + plan_schedule)
    merged = schedule.merge(df[["date"] + cols], on="date", how="left").sort_values("date")
    merged.to_csv(OUT_PLAN, index=False)

    log = merged[["date","phase","intervention"]].copy()
    log["adherence_manual"] = np.nan
    log["note"] = ""
    log.to_csv(OUT_LOG, index=False)


def compute_adherence(schedule, exp, df):
    rule = exp.get("adherence_rule", {"type":"relative_iqr","multiplier":0.5})
    lever = exp["lever"]

    merged = schedule.merge(df[["date", lever]], on="date", how="left")
    thr = None
    if rule["type"] == "relative_iqr" and lever in df:
        bump = iqr_nudge(df, lever, rule.get("multiplier", 0.5))
        base_med = df[lever].median()
        if bump is not None and base_med is not None and np.isfinite(base_med):
            thr = base_med + bump

    merged["adherence_auto"] = np.where(
        (merged["intervention"] == 1) & (thr is not None) & (merged[lever].notna()),
        (merged[lever] >= thr).astype(float),
        np.nan
    )
    return merged, thr



def hac_ttest(y, treat):
    t = pd.Series(treat, name="treat")
    X = sm.add_constant(t)
    y = pd.Series(y, name="y")

    # Align and drop missing across both
    dat = pd.concat([y, X], axis=1).dropna()
    if dat.empty or dat["treat"].nunique() <= 1:
        return {"coef": np.nan, "se": np.nan, "t": np.nan, "p": np.nan, "n": 0}

    model = sm.OLS(dat["y"], dat[["const","treat"]]).fit(
        cov_type="HAC", cov_kwds={"maxlags": 3}
    )
    co = model.params.get("treat", np.nan)
    se = model.bse.get("treat", np.nan)
    tval = float(co/se) if (se is not None and np.isfinite(se) and se != 0) else np.nan
    return {"coef": float(co), "se": float(se), "t": tval,
            "p": float(model.pvalues.get("treat", np.nan)),
            "n": int(model.nobs)}


def its_ols(df, target):
    # Interrupted time series:
    # y ~ const + time + post + time_after + DOW + weekend + AR(1)-lite (y_lag1 if exists)
    dfx = df.copy()
    dfx = dfx.sort_values("date").reset_index(drop=True)
    dfx["t"] = np.arange(len(dfx))
    if "intervention" not in dfx: return None

    # Post indicator and interaction
    first_post_idx = dfx.index[dfx["intervention"]==1].min()
    if not np.isfinite(first_post_idx):
        return None
    dfx["post"] = (dfx.index >= first_post_idx).astype(int)
    dfx["post_t"] = dfx["post"]*(dfx["t"] - dfx.loc[first_post_idx,"t"])

    # AR(1) baseline if we can
    if f"{target}_lag1" in dfx.columns:
        ar_cols = [f"{target}_lag1"]
    else:
        ar_cols = []

    # Covariates
    covs = ["t","post","post_t","is_weekend"]
    # Add DOW one-hot (avoid dummy trap)
    for d in range(1,7):
        dname = f"dow_{d}"
        dfx[dname] = (dfx["dow"]==d).astype(int)
        covs.append(dname)
    covs += ar_cols

    ok = dfx[[target,"intervention"]+covs].dropna()
    if ok.empty: return None
    y = ok[target]
    X = sm.add_constant(ok[covs])
    mod = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags":3})
    # key effects: level change (post), slope change (post_t)
    return {
        "n": int(mod.nobs),
        "level_change_coef": float(mod.params.get("post", np.nan)),
        "level_change_p": float(mod.pvalues.get("post", np.nan)),
        "slope_change_coef": float(mod.params.get("post_t", np.nan)),
        "slope_change_p": float(mod.pvalues.get("post_t", np.nan)),
        "r2": float(mod.rsquared),
        "adj_r2": float(mod.rsquared_adj)
    }

def evaluate(exp):
    df = load_daily()
    sch = plan_schedule(exp, df)
    export_templates(sch, exp, df)

    merged, thr = compute_adherence(sch, exp, df)
    target = exp["target"]; lever = exp["lever"]

    # Construct analysis frame
    ana = merged.merge(df[["date",target,lever,"dow","is_weekend"] + 
                        ([f"{target}_lag1"] if f"{target}_lag1" in df.columns else [])],
                       on="date", how="left").sort_values("date")

    # define treatment as "intervention & adherent (auto or manual later)"
    treat = ana["intervention"].copy()
    # if adherence_auto is defined, use that to mask treatment where 0
    if "adherence_auto" in ana.columns and ana["adherence_auto"].notna().any():
        treat = treat * ana["adherence_auto"].fillna(0)

    # A) diff-in-means (HAC)
    dm = hac_ttest(ana[target], treat)

    # B) ITS regression
    its = its_ols(ana.assign(intervention=treat), target)

    # Summarize
    lines = []
    lines.append(f"# N-of-1 Results — {exp['name']}\n")
    lines.append(f"- Target: `{target}`   Lever: `{lever}`")
    lines.append(f"- Baseline days: {exp['days_baseline']}   Intervention days: {exp['days_intervention']}")
    if thr is not None:
        lines.append(f"- Adherence threshold for lever: `{lever} >= {thr:.2f}` (auto)")
    lines.append("")
    # Means
    base = ana.loc[ana["intervention"] == 0, target]
    post = ana.loc[treat > 0, target]

    base_mean = float(base.mean()) if not base.empty else float("nan")
    post_mean = float(post.mean()) if not post.empty else float("nan")

    lines.append(f"**Baseline mean {target}:** {base_mean:.2f}")
    lines.append(f"**Intervention mean {target} (adherent days):** {post_mean:.2f}\n")

    lines.append("## A) Difference-in-means (HAC)")
    lines.append(f"- Effect (intervention vs baseline): **{dm['coef']:+.3f}** (p={dm['p']:.3f}, n={dm['n']})")

    lines.append("\n## B) Interrupted Time Series (ITS)")
    if its:
        lines.append(f"- Level change (post): **{its['level_change_coef']:+.3f}** (p={its['level_change_p']:.3f})")
        lines.append(f"- Slope change (post_t): **{its['slope_change_coef']:+.3f}** (p={its['slope_change_p']:.3f})")
        lines.append(f"- adjR²={its['adj_r2']:.3f} (n={its['n']})")
    else:
        lines.append("- Not enough data to fit ITS.")

    Path(OUT_SUMMARY).write_text("\n".join(lines))
    print(f"📄 Schedule: {OUT_PLAN}")
    print(f"📝 Log template: {OUT_LOG}")
    print(f"✅ Results summary: {OUT_SUMMARY}")

def main():
    cfg = json.load(open(CONF_PATH))
    for exp in cfg["experiments"]:
        evaluate(exp)

if __name__ == "__main__":
=======
    df["dow"] = df["date"].dt.dayofweek
    df["is_weekend"] = (df["dow"]>=5).astype(int)
    return df

# ---------- Stats ----------
def hac_ttest(y,treat):
    t = pd.Series(treat, name="treat")
    X = sm.add_constant(t)
    y = pd.Series(y, name="y")
    dat = pd.concat([y, X], axis=1).dropna()
    if dat.empty or dat["treat"].nunique() <= 1:
        return {"coef": np.nan, "p": np.nan, "n": 0}
    model = sm.OLS(dat["y"], dat[["const","treat"]]).fit(cov_type="HAC",cov_kwds={"maxlags":3})
    return {"coef":float(model.params.get("treat",np.nan)),
            "p":float(model.pvalues.get("treat",np.nan)),
            "n":int(model.nobs)}

def its_ols(df,target):
    if "intervention" not in df: return None
    dfx=df.copy().sort_values("date").reset_index(drop=True)
    first_post=dfx.index[dfx["intervention"]==1].min()
    if not np.isfinite(first_post): return None
    dfx["t"]=np.arange(len(dfx))
    dfx["post"]=(dfx.index>=first_post).astype(int)
    dfx["post_t"]=dfx["post"]*(dfx["t"]-dfx.loc[first_post,"t"])
    covs=["t","post","post_t","is_weekend"]
    for d in range(1,7): dfx[f"dow_{d}"]=(dfx["dow"]==d).astype(int); covs.append(f"dow_{d}")
    ok=dfx[[target,"intervention"]+covs].dropna()
    if ok.empty: return None
    y=ok[target]; X=sm.add_constant(ok[covs])
    mod=sm.OLS(y,X).fit(cov_type="HAC",cov_kwds={"maxlags":3})
    return {"level_change_coef":float(mod.params.get("post",np.nan)),
            "level_change_p":float(mod.pvalues.get("post",np.nan)),
            "slope_change_coef":float(mod.params.get("post_t",np.nan)),
            "slope_change_p":float(mod.pvalues.get("post_t",np.nan)),
            "adj_r2":float(mod.rsquared_adj)}

# ---------- Correlation mining ----------
def _load_json(p): 
    return json.loads(p.read_text()) if p.exists() else None

def _iter_pairs_from_models(models):
    for m in models:
        tgt=m.get("target")
        for side in ["top_pos","top_neg"]:
            for r in (m.get("significant_correlations",{}).get(side) or []):
                yield {"target":tgt,"lever":r.get("feature"),"r":float(r.get("r",np.nan)),"q":float(r.get("q",np.nan))}

def _iter_pairs_from_corr_csv(df):
    # expect columns: target, feature, r, q (or variants)
    tcol = "target" if "target" in df.columns else "y"
    fcol = "feature" if "feature" in df.columns else ("x" if "x" in df.columns else None)
    rcol = "r" if "r" in df.columns else ("pearson_r" if "pearson_r" in df.columns else None)
    qcol = "q" if "q" in df.columns else ("fdr_q" if "fdr_q" in df.columns else None)
    if not all([tcol,fcol,rcol,qcol]): return
    for _,row in df.iterrows():
        try: yield {"target":row[tcol],"lever":row[fcol],"r":float(row[rcol]),"q":float(row[qcol])}
        except: continue

def mine_significant_pairs(results_dir):
    pairs=[]
    m=_load_json(results_dir/"combined_models.json")
    if m: pairs+=list(_iter_pairs_from_models(m))
    p=results_dir/"correlation_matrix.csv"
    if p.exists(): pairs+=list(_iter_pairs_from_corr_csv(pd.read_csv(p)))
    good=[]
    for p in pairs:
        if np.isfinite(p["r"]) and np.isfinite(p["q"]) and abs(p["r"])>=MIN_ABS_R and p["q"]<MAX_Q:
            good.append(p)
    return good

# ---------- Post-mining filtering to keep only actionable, non-redundant pairs ----------
def _is_self_or_derived(target: str, lever: str) -> bool:
    """True if lever is the same base signal as target (e.g., glucose_mean vs glucose_mean_3d_ma)."""
    return _base_name(target) == _base_name(lever)

def _is_behavioral(lever: str) -> bool:
    return lever in BEHAVIORAL_LEVERS

def _is_redundant_component(target: str, lever: str) -> bool:
    return (target, lever) in REDUNDANT_COMPONENTS

def filter_valid_pairs(pairs: List[Dict[str,Any]]) -> List[Dict[str,Any]]:
    valid=[]
    seen=set()
    for p in pairs:
        tgt, lev = p["target"], p["lever"]
        # skip self / derived / rolling versions
        if _is_self_or_derived(tgt, lev): 
            continue
        # keep only behavioral levers (things user can change)
        if not _is_behavioral(lev):
            continue
        # skip known redundant component relations
        if _is_redundant_component(tgt, lev):
            continue
        key=(tgt,lev)
        if key in seen: 
            continue
        seen.add(key)
        valid.append(p)
    return valid

# ---------- Evaluation ----------
def _evaluate_if_possible(df,target,lever):
    if target not in df or lever not in df: return None
    dfx=df[[ "date",target,lever,"dow","is_weekend"]].dropna().sort_values("date")
    if dfx.empty: return None
    s=dfx[lever]
    if s.empty: return None
    q1,q3=np.nanpercentile(s,25),np.nanpercentile(s,75)
    thr=np.median(s)+0.5*(q3-q1)
    on=(s>=thr).astype(int)
    dm=hac_ttest(dfx[target],on)
    ana=dfx.copy(); ana["intervention"]=on
    its=its_ols(ana,target)
    return {"dm":dm,"its":its}

# ---------- Write Markdown ----------
def write_markdown(pairs, df):
    lines = ["# 🧪 Experiments To Run (with scientific justification)\n"]
    if not pairs:
        lines.append("_No significant, actionable levers found (after filtering out derived/self features)._")
        OUT_DOC.write_text("\n".join(lines))
        return

    # group by target
    grouped = {}
    for p in pairs:
        grouped.setdefault(p["target"], []).append(p)

    for tgt, items in grouped.items():
        if not items:
            continue
        info = TARGET_INFO.get(tgt, {})
        better = BETTER_DIRECTION.get(tgt, "better")
        arrow = "↓" if better == "lower" else ("↑" if better == "higher" else "→")
        lines.append(f"\n## Goal: {arrow} {tgt.replace('_', ' ')}")
        if info.get("why"):
            lines.append(f"**Why this goal matters:** {info['why']}")
        if info.get("healthy_range"):
            lines.append(f"**Healthy range:** {info['healthy_range']}")
        if info.get("external_levers"):
            lines.append(f"**Other influencing factors:** {', '.join(info['external_levers'])}.")

        kept = sorted(items, key=lambda p: (p["q"], -abs(p["r"])))[:MAX_EXPS_PER_TARGET]
        for i, p in enumerate(kept, 1):
            lev = p["lever"]
            levname = _human(lev)
            move = _recommend_direction(tgt, p["r"])
            lines.append(f"\n### Experiment {i} — {levname} ({'↑' if move=='increase' else '↓'})")
            lines.append(
                f"**Source of evidence:** Found in your data (r={p['r']:.2f}, q={p['q']:.3f}). "
                f"When your {levname} {move}s, your {tgt.replace('_',' ')} tends to "
                f"{'increase' if p['r']>0 else 'decrease'}."
            )

            # baseline + norms
            baseline = np.nanmedian(df[lev]) if lev in df else np.nan
            if np.isfinite(baseline):
                lines.append(f"**Your baseline:** {int(round(baseline)):,} {levname}.")

                # --- Normative comparison ---
                try:
                    ref = lookup_norm(lev, age, sex, norms)
                    if ref:
                        ref_mean, ref_sd, pct, src = ref
                        perc = pct(baseline)
                        if np.isfinite(perc):
                            lines.append(
                                f"_Population context:_ {levname} at {baseline:.1f} → "
                                f"≈ {perc:.0f}ᵗʰ percentile vs peers "
                                f"(ref μ {ref_mean:.1f}, σ {ref_sd:.1f}, {src})."
                            )
                            if perc < 25:
                                lines.append("_You’re below typical range — this is a corrective experiment._")
                            elif perc > 75:
                                lines.append("_Already above average — this is an optimization/maintenance experiment._")
                            else:
                                lines.append("_Within typical range — moderate improvement may still help._")
                except Exception as e:
                    lines.append(f"_Norm reference unavailable ({e})._")

                # optional healthy-range note
                if info.get("healthy_range") and tgt in df.columns:
                    tgt_med = float(np.nanmedian(df[tgt])) if tgt in df else np.nan
                    if np.isfinite(tgt_med):
                        lines.append(
                            f"_Note: your current median {tgt.replace('_',' ')} is ~{tgt_med:.1f}; "
                            "if this is already within the healthy range above, this is an optimization/maintenance experiment rather than corrective._"
                        )

                # explicit step targets
                if lev == "steps_sum":
                    lines.append(
                        f"**Targets (steps):** Week2 = {int(baseline)+2000:,}, "
                        f"Week3 = {int(baseline)+3000:,}, Week4 maintain."
                    )

            # === Design choice ===
            if lev in ("steps_sum", "outdoor_minutes", "sleep_hours", "vo2max_ml_kg_min"):
                lines.append("\n**Design:** Stepped multi-week program (gradual dose).")
                lines.append("**Why this design:** Adaptation accumulates over days/weeks; stepped dosing + segmented regression (ITS) captures level/slope changes better than on/off toggles.")
            elif lev in (
                "late_meal_count", "screen_time_h", "alcohol_units", "added_sugar_g",
                "sat_fat_g", "meditation_min", "eating_window_h", "bedtime_hour",
                "waketime_hour", "water_l", "fiber_g", "protein_g"
            ):
                blocks, block_len = 4, 2
                total_days = blocks * block_len
                lines.append("\n**Design:** ABAB with randomized 2-day blocks (A=OFF/control, B=ON/intervention).")
                lines.append(f"- **Total duration:** ~{total_days} days across {blocks} blocks of {block_len} days.")
                lines.append("- **A (OFF):** your usual pattern.")
                lines.append("- **B (ON):** apply the lever rule for that day/block (e.g., no late meals; no screens after 9 pm; 0 drinks; ≥10–15 min meditation).")
                lines.append("**Why this design:** Fast, reversible effects with minimal carryover; within-person replication; HAC accounts for autocorrelation.")
            else:
                blocks, block_len = 4, 2
                total_days = blocks * block_len
                lines.append("\n**Design:** ABAB 2-day blocks; A=usual, B=apply the lever.")
                lines.append(f"- **Total duration:** ~{total_days} days.")
                lines.append("**Why this design:** Replicated contrasts, reduced bias from weekday rhythms.")

            # === Expected direction ===
            lines.append(f"**Expected direction:** {move} {levname} → {('higher' if better=='higher' else 'lower')} {tgt.replace('_',' ')}.")

            # === Stats ===
            stats = _evaluate_if_possible(df, tgt, lev)
            if stats:
                dm, its = stats["dm"], stats["its"]
                lines.append("\n**What your data so far suggests:**")
                if dm and dm["n"] > 0 and np.isfinite(dm["coef"]):
                    eff = "increase" if dm["coef"] > 0 else "decrease"
                    lines.append(f"- Diff-in-means (HAC): {eff} of {abs(dm['coef']):.2f} (p={dm['p']:.3f}, n={dm['n']}).")
                if its:
                    if np.isfinite(its.get("level_change_p", np.nan)) and its["level_change_p"] < 0.05:
                        lines.append(f"- ITS: immediate {'increase' if its['level_change_coef']>0 else 'decrease'} after ON periods (p={its['level_change_p']:.3f}).")
                    elif np.isfinite(its.get("slope_change_p", np.nan)) and its["slope_change_p"] < 0.1:
                        lines.append(f"- ITS: gradual {'upward' if its['slope_change_coef']>0 else 'downward'} trend over time (p={its['slope_change_p']:.3f}).")
                    else:
                        lines.append("- ITS: no clear trend yet — likely needs more cycles or stronger contrast.")

            # === Next steps ===
            lines.append("\n**Next steps:**")
            lines.append("- Run the full design window. If effects move in the expected direction across ≥2 consecutive blocks/weeks, maintain for 2–4 more weeks and re-check.")
            lines.append("- If no change, pair this lever with another (e.g., earlier bedtime or reduced alcohol) and re-test.")

    OUT_DOC.write_text("\n".join(lines))
    print(f"📝 Wrote {OUT_DOC}")

# ---------- Main ----------
def main():
    df=load_daily()

    # Load all pairs then filter to actionable, non-redundant ones
    pairs = mine_significant_pairs(RESULTS_DIR)
    pairs = filter_valid_pairs(pairs)

    # Optional manual override
    if CONF_PATH.exists():
        try:
            cfg = json.loads(CONF_PATH.read_text())
            if isinstance(cfg, dict) and isinstance(cfg.get("experiments"), list) and cfg["experiments"]:
                # Merge manual experiments (assume reasonable r/q placeholders if not provided)
                for e in cfg["experiments"]:
                    p = {"target": e["target"], "lever": e["lever"], "r": e.get("r", 0.3), "q": e.get("q", 0.01)}
                    if p["lever"] in BEHAVIORAL_LEVERS and not _is_self_or_derived(p["target"], p["lever"]):
                        pairs.append(p)
        except:
            pass

    global norms, age, sex
    norms = load_norm_bank()
    age, sex = 22, "f"

    write_markdown(pairs, df)

if __name__=="__main__":
>>>>>>> ebf6a02
    main()
