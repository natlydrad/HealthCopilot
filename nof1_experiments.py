#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
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

def load_daily():
    df = pd.read_csv(DF_PATH, parse_dates=["date"])
    df["date"] = _normalize_date(df["date"])
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
    main()
