#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
n1_experiments.py — Coach-style N-of-1 planner + (optional) evaluator

What this version does:
- Mines significant, actionable lever→target pairs from the latest RESULTS folder
- Chooses an N-of-1 design per lever (ABAB / randomized daily / stepped / crossover+washout)
  based on expected onset and carryover
- Writes ONE Markdown file (experiment_plan.md) with:
    * Goal (target)
    * Concrete "how to do it" steps (specific doses, durations, rules)
    * Design justification (why ABAB vs stepped, washout reasoning, replication)
    * (If you already have data spanning the plan window) HAC diff-in-means + ITS stats appended
- No schedule/log CSVs are produced

Keeps: Your HAC t-test and ITS code paths to show results if data exists.
"""

import json, math, os
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from datetime import timedelta
import numpy as np, pandas as pd
import statsmodels.api as sm

# ---------- Paths ----------
RESULTS_DIR = sorted(Path("RESULTS").glob("results_*"))[-1]
DF_PATH      = RESULTS_DIR / "daily_features.csv"
CONF_PATH    = Path("experiments_config.json")

from datetime import datetime
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
OUT_DOC = RESULTS_DIR / f"experiment_plan_{timestamp}.md"


# ---------- Thresholds & defaults ----------
MIN_ABS_R = 0.25
MAX_Q     = 0.05
MAX_EXPS_PER_TARGET = 2
DEFAULT_START_OFFSET_DAYS = 1  # start tomorrow by default

# Which direction is "better" for common targets
BETTER_DIRECTION = {
    "glucose_mean": "lower",
    "glucose_auc": "lower",
    "glucose_cv": "lower",
    "resting_hr_bpm": "lower",
    "energy_score": "higher",
    "mood_score": "higher",
    "sleep_hours": "higher",
    "hrv_sdnn_ms": "higher",
    "rem_min": "higher",
    "deep_min": "higher",
    "core_min": "higher",
    "total_min": "higher",
}

# Human names for levers
LEVER_NAME = {
    "steps_sum": "daily steps",
    "sleep_hours": "sleep duration",
    "rem_min": "REM minutes",
    "deep_min": "deep sleep minutes",
    "bedtime_hour": "bedtime",
    "waketime_hour": "wake time",
    "vo2max_ml_kg_min": "VO₂max (cardio fitness)",
    "hrv_sdnn_ms": "HRV (SDNN)",
    "resting_hr_bpm": "resting heart rate",
    "fiber_g": "fiber",
    "protein_g": "protein",
    "added_sugar_g": "added sugar",
    "sat_fat_g": "saturated fat",
    "water_l": "water intake",
    "eating_window_h": "eating window",
    "late_meal_count": "late meals",
    "alcohol_units": "alcohol",
    "outdoor_minutes": "outdoor time",
    "meditation_min": "meditation",
    "screen_time_h": "evening screen time",
}

# === Utility ===
def _normalize_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, utc=True, errors="coerce").dt.tz_localize(None)

def load_daily() -> pd.DataFrame:
    df = pd.read_csv(DF_PATH, parse_dates=["date"])
    df["date"] = _normalize_date(df["date"])
    if "dow" not in df: df["dow"] = df["date"].dt.dayofweek
    if "is_weekend" not in df: df["is_weekend"] = (df["dow"]>=5).astype(int)
    return df

# ---------- Stats (kept) ----------
def hac_ttest(y, treat):
    t = pd.Series(treat, name="treat")
    X = sm.add_constant(t)
    y = pd.Series(y, name="y")
    dat = pd.concat([y, X], axis=1).dropna()
    if dat.empty or dat["treat"].nunique() <= 1:
        return {"coef": np.nan, "se": np.nan, "t": np.nan, "p": np.nan, "n": 0}
    model = sm.OLS(dat["y"], dat[["const","treat"]]).fit(cov_type="HAC", cov_kwds={"maxlags": 3})
    co = model.params.get("treat", np.nan)
    se = model.bse.get("treat", np.nan)
    tval = float(co/se) if (se is not None and np.isfinite(se) and se != 0) else np.nan
    return {"coef": float(co), "se": float(se), "t": tval,
            "p": float(model.pvalues.get("treat", np.nan)),
            "n": int(model.nobs)}

def its_ols(df, target):
    dfx = df.copy().sort_values("date").reset_index(drop=True)
    dfx["t"] = np.arange(len(dfx))
    if "intervention" not in dfx: return None
    first_post_idx = dfx.index[dfx["intervention"]==1].min()
    if not np.isfinite(first_post_idx): return None
    dfx["post"] = (dfx.index >= first_post_idx).astype(int)
    dfx["post_t"] = dfx["post"]*(dfx["t"] - dfx.loc[first_post_idx,"t"])
    ar_cols = [f"{target}_lag1"] if f"{target}_lag1" in dfx.columns else []
    covs = ["t","post","post_t","is_weekend"]
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
    return {
        "n": int(mod.nobs),
        "level_change_coef": float(mod.params.get("post", np.nan)),
        "level_change_p": float(mod.pvalues.get("post", np.nan)),
        "slope_change_coef": float(mod.params.get("post_t", np.nan)),
        "slope_change_p": float(mod.pvalues.get("post_t", np.nan)),
        "r2": float(mod.rsquared),
        "adj_r2": float(mod.rsquared_adj)
    }

# ---------- Correlation mining ----------
def _load_combined_models_json(results_dir: Path) -> Optional[List[Dict[str, Any]]]:
    p = results_dir / "combined_models.json"
    if p.exists():
        try: return json.loads(p.read_text())
        except: pass
    return None

def _load_correlation_matrix_csv(results_dir: Path) -> Optional[pd.DataFrame]:
    p = results_dir / "correlation_matrix.csv"
    if p.exists():
        try: return pd.read_csv(p)
        except: pass
    return None

def _iter_pairs_from_combined_models(models: List[Dict[str, Any]]):
    for m in models:
        tgt = m.get("target")
        sig = (m.get("significant_correlations") or {})
        for arr in [sig.get("top_pos") or [], sig.get("top_neg") or []]:
            for row in arr:
                yield {"target": tgt, "lever": row.get("feature"),
                       "r": float(row.get("r", np.nan)),
                       "q": float(row.get("q", np.nan))}

def _iter_pairs_from_corr_csv(df: pd.DataFrame):
    tcol = "target" if "target" in df.columns else "y"
    fcol = "feature" if "feature" in df.columns else ("x" if "x" in df.columns else None)
    rcol = "r" if "r" in df.columns else ("pearson_r" if "pearson_r" in df.columns else None)
    qcol = "q" if "q" in df.columns else ("fdr_q" if "fdr_q" in df.columns else None)
    if not all([tcol, fcol, rcol, qcol]): return
    for _, row in df.iterrows():
        try:
            yield {"target": row[tcol], "lever": row[fcol],
                   "r": float(row[rcol]), "q": float(row[qcol])}
        except: continue

def mine_significant_pairs(results_dir: Path, min_abs_r=MIN_ABS_R, max_q=MAX_Q) -> List[Dict[str,Any]]:
    pairs = []
    m = _load_combined_models_json(results_dir)
    if m: pairs += list(_iter_pairs_from_combined_models(m))
    c = _load_correlation_matrix_csv(results_dir)
    if c is not None: pairs += list(_iter_pairs_from_corr_csv(c))
    if not pairs: return []
    out, seen = [], set()
    for p in pairs:
        tgt, lev, r, q = p["target"], p["lever"], p["r"], p["q"]
        if not (isinstance(tgt,str) and isinstance(lev,str)): continue
        if not (np.isfinite(r) and np.isfinite(q)): continue
        if abs(r) < min_abs_r or q >= max_q: continue
        key = (tgt, lev)
        if key in seen: continue
        seen.add(key)
        out.append(p)
    return out

# ---------- Design selection (physiology-aware) ----------
def _lever_design(lever: str) -> Dict[str, Any]:
    """
    returns a dict with:
      type: 'ABAB' | 'RANDOM_DAILY' | 'STEPPED' | 'CROSSOVER'
      blocks / weeks / days
      washout_days
      adherence_text
      instructions (concrete how-to)
      justification (why this design fits: onset/carryover/replication)
    """
    # defaults (safe)
    d = dict(type="ABAB", blocks=4, block_len_days=2, washout_days=0,
             adherence_text="Follow the ON/OFF rule exactly on ON days.",
             instructions="Follow ON vs OFF blocks as written.",
             justification="Fast, reversible effect expected; ABAB provides within-person replication.")
    if lever in ("late_meal_count",):
        d.update(type="ABAB", blocks=4, block_len_days=2, washout_days=1,
                 adherence_text="OFF = no food after 8:30pm; ON = at least one late meal (≥9pm).",
                 instructions="Pre-randomize 8 blocks of 2 days. Follow the ON/OFF rule each block.",
                 justification="Meal timing affects glucose/sleep within 24h; small 1–2 day carryover; ABAB gives replications.")
    elif lever in ("screen_time_h",):
        d.update(type="ABAB", blocks=4, block_len_days=2, washout_days=1,
                 adherence_text="OFF = no screens after 9pm; ON = usual behavior.",
                 instructions="Alternate ON/OFF in randomized 2-day blocks.",
                 justification="Blue light/salience impact is immediate, minimal carryover; short ABAB isolates effect.")
    elif lever in ("alcohol_units",):
        d.update(type="ABAB", blocks=4, block_len_days=2, washout_days=1,
                 adherence_text="OFF = 0 drinks; ON = exactly 1 drink.",
                 instructions="Randomized 2-day blocks. Avoid consecutive ON>2.",
                 justification="Alcohol has 1–2 day residual effects on sleep/glucose; ABAB with short washout captures it.")
    elif lever in ("steps_sum","outdoor_minutes"):
        d.update(type="STEPPED", weeks=[1,1,1,1], step_plan=[0,+2000,+3000,"maintain"],
                 adherence_text="Daily steps must exceed baseline by the step goal (+2k or +3k).",
                 instructions="Week1 baseline; Week2 +2k/day; Week3 +3k/day; Week4 maintain.",
                 justification="Behavior changes/fitness adaptation need gradual dosing; segmented regression captures level/slope.")
    elif lever in ("meditation_min",):
        d.update(type="RANDOM_DAILY", total_days=28, washout_days=0,
                 adherence_text="ON = ≥10–15 min meditation; OFF = 0.",
                 instructions="Flip a coin each morning (cap 3 same in a row). Log ON/OFF and do the rule.",
                 justification="Acute effects on mood/HRV mostly same-day; randomization neutralizes weekday trends.")
    elif lever in ("sleep_hours","bedtime_hour","waketime_hour"):
        d.update(type="STEPPED", weeks=[1,1,1], step_plan=[0,"+45–60min","+45–60min"],
                 adherence_text="Time in bed must increase by ~45–60 min above baseline on step weeks.",
                 instructions="Week1 baseline; Weeks2–3 go to bed earlier to add 45–60 min.",
                 justification="Sleep system adapts over days; stepped dosing avoids whiplash and models trend.")
    elif lever in ("eating_window_h",):
        d.update(type="CROSSOVER", a_days=10, washout_days=4, b_days=10,
                 adherence_text="A: eating window ≤10h. B: usual schedule.",
                 instructions="Phase A 10d (≤10h), washout 4d, Phase B 10d usual (or reverse).",
                 justification="Metabolic inertia & weight/appetite setpoint; avoid on/off toggling; include washout.")
    elif lever in ("added_sugar_g","sat_fat_g"):
        d.update(type="ABAB", blocks=4, block_len_days=2, washout_days=1,
                 adherence_text="OFF = ≤5g added sugar (or ≤10g sat fat); ON = allow one item.",
                 instructions="Randomized 2-day ON/OFF blocks with 1-day washout if needed.",
                 justification="Diet composition has 1–2 day carryover; short blocks with replications fit well.")
    elif lever in ("vo2max_ml_kg_min",):
        d.update(type="STEPPED", weeks=[2,2,2], step_plan=["start 3×/wk 30–40min @60–70% HRmax",
                                                           "add 1 day of intervals @70–80% HRmax",
                                                           "maintain & reassess"],
                 adherence_text="Complete the prescribed sessions each week.",
                 instructions="6-week fitness block as above; analyze trends (ITS).",
                 justification="Cardiorespiratory fitness changes over weeks, not days; stepped program is appropriate.")
    return d

def _recommend_direction(target: str, r: float) -> str:
    better = BETTER_DIRECTION.get(target)
    if better == "lower":
        return "decrease" if r > 0 else "increase"
    if better == "higher":
        return "increase" if r > 0 else "decrease"
    return "increase" if r > 0 else "decrease"

def _human(var: str) -> str:
    return LEVER_NAME.get(var, var.replace("_"," "))

# ---------- Build experiments (grouped by goal) ----------
def build_experiments(doc_df: pd.DataFrame, pairs: List[Dict[str,Any]]) -> List[Dict[str,Any]]:
    if not pairs: return []
    start_date = (doc_df["date"].max() + pd.Timedelta(days=DEFAULT_START_OFFSET_DAYS)).strftime("%Y-%m-%d")
    grouped: Dict[str, List[Dict[str,Any]]] = {}
    for p in pairs:
        tgt, lev, r, q = p["target"], p["lever"], float(p["r"]), float(p["q"])
        move = _recommend_direction(tgt, r)
        design = _lever_design(lev)
        exp = {
            "target": tgt,
            "lever": lev,
            "lever_name": _human(lev),
            "direction": move,
            "r": round(r,3),
            "q": round(q,5),
            "design": design,
            "start_date": start_date
        }
        grouped.setdefault(tgt, []).append(exp)
    # Trim per target
    for tgt in list(grouped.keys()):
        grouped[tgt] = sorted(grouped[tgt], key=lambda e: (e["q"], -abs(e["r"])))[:MAX_EXPS_PER_TARGET]
    # Flatten with goal blocks preserved
    blocks = []
    for tgt, items in grouped.items():
        blocks.append({"goal": tgt, "experiments": items})
    return blocks

# ---------- Optional evaluation if user already ran the plan window ----------
def _evaluate_if_possible(df: pd.DataFrame, target: str, lever: str, design: Dict[str,Any]) -> Optional[Dict[str,Any]]:
    # We don't generate schedules; we try to infer ON/OFF from simple rules to show stats if exists.
    dfx = df[["date", target, lever, "dow", "is_weekend"]].dropna().sort_values("date").copy()
    if dfx.empty: return None
    # naive rule: define ON days by a threshold relative to baseline median (IQR nudge)
    s = dfx[lever].dropna()
    if s.empty: return None
    q1, q3 = np.nanpercentile(s,25), np.nanpercentile(s,75)
    thr = np.median(s) + 0.5*(q3-q1)
    on = (dfx[lever] >= thr).astype(int)

    # HAC diff-in-means
    dm = hac_ttest(dfx[target], on)

    # ITS: construct minimal frame
    ana = dfx.copy()
    ana["intervention"] = on
    its = its_ols(ana, target)
    return {"dm": dm, "its": its}

# ---------- Write Markdown ----------
def write_markdown(blocks: List[Dict[str,Any]], df: pd.DataFrame):
    lines = ["# 🧪 Experiments To Run (with scientific justification)\n"]
    if not blocks:
        lines.append("_No significant, actionable pairs found with current thresholds._")
        OUT_DOC.write_text("\n".join(lines)); return

    for blk in blocks:
        tgt = blk["goal"]
        better = BETTER_DIRECTION.get(tgt, "better")
        arrow = "↓" if better=="lower" else ("↑" if better=="higher" else "→")
        lines += [f"\n## Goal: {arrow} {tgt.replace('_',' ')}\n"]

        for i, e in enumerate(blk["experiments"], 1):
            d = e["design"]; move = "↑" if e["direction"]=="increase" else "↓"
            lines.append(f"### Experiment {i} — {(_human(e['lever']))} ({move})")
            lines.append(f"**Why this?** Strong association with {tgt.replace('_',' ')} (r={e['r']}, q={e['q']}).")

            # Concrete “how to do it”
            lines.append("\n**How to run it:**")
            if d["type"] == "ABAB":
                total_days = d["blocks"] * d["block_len_days"]
                lines.append(f"- **Design:** ABAB with randomized **{d['blocks']}× {d['block_len_days']}-day blocks** "
                             f"(~{total_days} days total).")
                if d.get("washout_days",0)>0:
                    lines.append(f"- **Washout:** {d['washout_days']} day between blocks if sleep is disrupted.")
                lines.append(f"- **ON rule:** {d['adherence_text']}")
                lines.append(f"- **Instructions:** {d['instructions']}")
            elif d["type"] == "RANDOM_DAILY":
                td = d.get("total_days", 28)
                lines.append(f"- **Design:** randomized daily A/B for **{td} days** "
                             f"(cap >3 same-condition streak).")
                lines.append(f"- **ON rule:** {d['adherence_text']}")
                lines.append(f"- **Instructions:** {d['instructions']}")
            elif d["type"] == "STEPPED":
                weeks = d.get("weeks",[1,1,1,1])
                plan  = d.get("step_plan",[0,"+25%","+50%","maintain"])
                lines.append(f"- **Design:** stepped dose across **{sum(weeks)} weeks** "
                             f"({', '.join([str(w)+'wk' for w in weeks])}).")
                lines.append(f"- **Step plan:** {', '.join(map(str, plan))}.")
                lines.append(f"- **Adherence:** {d['adherence_text']}")
                lines.append(f"- **Instructions:** {d['instructions']}")
            elif d["type"] == "CROSSOVER":
                lines.append(f"- **Design:** crossover A→washout→B "
                             f"(**{d['a_days']}d**, washout **{d['washout_days']}d**, **{d['b_days']}d**).")
                lines.append(f"- **Adherence:** {d['adherence_text']}")
                lines.append(f"- **Instructions:** {d['instructions']}")

            # Direction & expected outcome
            dir_txt = "increase" if e["direction"]=="increase" else "decrease"
            lines.append(f"- **Expected direction:** {dir_txt} **{_human(e['lever'])}** → "
                         f"{'lower' if better=='lower' else 'higher'} **{tgt.replace('_',' ')}**.")

            # Justification box
            lines.append("\n**Design justification (real-science vibe):**")
            lines.append(f"- **Onset & carryover:** {d['justification']}")
            lines.append("- **Replication & bias control:** design provides repeated contrasts within you; "
                         "randomization/blocks reduce weekday trends; HAC/ITS handle autocorrelation.")
            lines.append("- **Minimum duration:** aim for ≥20–30 observation days overall to detect moderate effects.")

            # Optional quick stats if data exists
            stats = _evaluate_if_possible(df, tgt, e["lever"], d)
            if stats:
                dm, its = stats["dm"], stats["its"]
                lines.append("\n**What your data so far says (informal):**")
                if dm and dm["n"]>0:
                    lines.append(f"- Diff-in-means (HAC): effect {dm['coef']:+.3f} (p={dm['p']:.3f}, n={dm['n']})")
                if its:
                    lines.append(f"- ITS: level {its['level_change_coef']:+.3f} (p={its['level_change_p']:.3f}), "
                                 f"slope {its['slope_change_coef']:+.3f} (p={its['slope_change_p']:.3f}), "
                                 f"adjR²={its['adj_r2']:.3f}.")
            lines.append("")

    OUT_DOC.write_text("\n".join(lines))

# ---------- Manual config (optional) ----------
def _load_manual_config() -> Optional[Dict[str,Any]]:
    if not CONF_PATH.exists(): return None
    try:
        cfg = json.loads(CONF_PATH.read_text())
        if isinstance(cfg, dict) and isinstance(cfg.get("experiments"), list) and cfg["experiments"]:
            return cfg
    except: pass
    return None

# ---------- Main ----------
def main():
    df = load_daily()
    cfg = _load_manual_config()

    if cfg:
        # Manual config: treat each item as a lever test for a target
        pairs = [{"target": e["target"], "lever": e["lever"], "r": 0.3, "q": 0.01} for e in cfg["experiments"]]
    else:
        pairs = mine_significant_pairs(RESULTS_DIR, MIN_ABS_R, MAX_Q)

    if not pairs:
        write_markdown([], df); return

    blocks = build_experiments(df, pairs)
    write_markdown(blocks, df)
    print(f"📝 Wrote {OUT_DOC}")

if __name__ == "__main__":
    main()
