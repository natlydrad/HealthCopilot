#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, argparse, json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

import pandas as pd
import numpy as np
import statsmodels.api as sm
from statsmodels.stats.outliers_influence import variance_inflation_factor
from sklearn.linear_model import LassoCV
from sklearn.preprocessing import StandardScaler
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import re

from pb_client import get_token, fetch_records


# =========================
# -------- UTIL --------
# =========================

RESULTS_ROOT = Path("/Users/natalieradu/Desktop/HealthCopilot/RESULTS")

def env(name: str, default: Optional[str] = None) -> Optional[str]:
    return os.environ.get(name, default)

def coalesce_number(d: Dict[str, Any], keys: List[str]) -> Optional[float]:
    for k in keys:
        if k in d and d[k] is not None:
            try:
                return float(d[k])
            except Exception:
                continue
    return None

def to_datetime_utc(s) -> pd.Timestamp:
    return pd.to_datetime(s, utc=True, errors="coerce")

def ensure_daily_continuity(df: pd.DataFrame, date_col: str = "date") -> pd.DataFrame:
    """Guarantee one row per day between min/max date; collapses duplicate days safely."""
    if df is None or df.empty or date_col not in df.columns:
        return df

    out = df.copy()
    out[date_col] = pd.to_datetime(out[date_col], utc=True, errors="coerce").dt.floor("D")
    out = out.dropna(subset=[date_col])

    # Collapse duplicate days: numeric -> mean, non-numeric -> first
    num_cols = out.select_dtypes(include=[np.number]).columns.tolist()
    agg = {c: "first" for c in out.columns if c not in num_cols + [date_col]}
    for c in num_cols:
        agg[c] = "mean"

    out = (
        out.groupby(date_col, as_index=False)
           .agg(agg)
           .sort_values(date_col)
    )

    start, end = out[date_col].min(), out[date_col].max()
    idx = pd.date_range(start, end, freq="D", tz="UTC")

    out = (
        out.set_index(date_col)
           .reindex(idx)
           .rename_axis("date")
           .reset_index()
    )
    out["date"] = pd.to_datetime(out["date"], utc=True).dt.floor("D")
    return out


def safe_group_daily(df: pd.DataFrame, ts_col: str, val_col: str, agg: str = "mean") -> pd.DataFrame:
    if ts_col not in df.columns:
        raise ValueError(f"Timestamp column '{ts_col}' not found in DataFrame.")
    df = df.dropna(subset=[ts_col, val_col]).copy()
    df["date"] = pd.to_datetime(df[ts_col], utc=True, errors="coerce").dt.floor("D")
    grouped = df.groupby("date", as_index=False)[val_col].agg(agg)
    grouped["date"] = pd.to_datetime(grouped["date"], utc=True).dt.floor("D")
    return grouped



# =========================
# ----- AGGREGATORS -----
# =========================

def aggregate_steps(raw: List[Dict[str, Any]]) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame(columns=["date", "steps_sum"])
    df = pd.DataFrame(raw)

    ts_col = next((c for c in ["timestamp","date","created","updated"] if c in df.columns), None)
    if not ts_col:
        return pd.DataFrame(columns=["date", "steps_sum"])

    df["ts"] = to_datetime_utc(df[ts_col])
    df["steps_val"] = df.apply(lambda r: coalesce_number(r, ["steps","count","value"]), axis=1)
    df = df.dropna(subset=["ts","steps_val"])
    df = df[df["steps_val"] > 0]  # drop spurious zeros

    g = safe_group_daily(df, "ts", "steps_val", agg="sum")
    g.rename(columns={"steps_val":"steps_sum"}, inplace=True)
    g = g[["date","steps_sum"]].sort_values("date")
    return ensure_daily_continuity(g, "date")

def aggregate_glucose(raw: List[Dict[str, Any]]) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame(columns=["date","glucose_mean"])
    df = pd.DataFrame(raw)

    ts_col = next((c for c in ["timestamp","date","created","updated","time","recorded_at"] if c in df.columns), None)
    val_col = next((c for c in ["glucose","value","value_mgdl","mgdl","mg_dL","mgdl_value","glucose_mgdl","reading","value_mgdl"] if c in df.columns), None)
    if not ts_col or not val_col:
        print("⚠️ Skipping glucose: missing timestamp or value col.", list(df.columns))
        return pd.DataFrame(columns=["date","glucose_mean"])

    df["ts"] = to_datetime_utc(df[ts_col])
    df["g"]  = pd.to_numeric(df[val_col], errors="coerce")
    df = df.dropna(subset=["ts","g"])
    df = df[df["g"].between(40, 400)]  # sanity window

    g = safe_group_daily(df, "ts", "g", agg="mean")
    g.rename(columns={"g":"glucose_mean"}, inplace=True)
    g = g[["date","glucose_mean"]].sort_values("date")
    return ensure_daily_continuity(g, "date")

def aggregate_daily_table(raw, date_candidates, numeric_map):
    if not raw:
        return pd.DataFrame(columns=["date"]+list(numeric_map.keys()))
    df = pd.DataFrame(raw)

    date_col = next((c for c in date_candidates+["date","timestamp","created","updated"] if c in df.columns), None)
    if not date_col:
        return pd.DataFrame(columns=["date"]+list(numeric_map.keys()))

    df["date"] = pd.to_datetime(df[date_col], utc=True, errors="coerce").dt.floor("D")
    for out_col, cand in numeric_map.items():
        df[out_col] = df.apply(lambda r: coalesce_number(r, cand), axis=1)

    out = df.groupby("date",as_index=False)[list(numeric_map.keys())].mean().sort_values("date")
    out["date"] = pd.to_datetime(out["date"], utc=True).dt.floor("D")
    out = ensure_daily_continuity(out, "date")
    return out.sort_values("date")


# =========================
# ---- FEATURE BUILDER ----
# =========================

def make_daily_features(base_url, email, password, user_id, start, end,
                        map_steps, map_glucose, map_energy, map_heart, map_sleep):

    _ = get_token()
    print("🔑 PocketBase token acquired.")
    filt = f'user="{user_id}"' if user_id else None  # not used by fetch_records, but keeping for future

    def win(df):
        if df is None or df.empty: return df
        if start: df = df[df["date"]>=pd.to_datetime(start,utc=True)]
        if end:   df = df[df["date"]<=pd.to_datetime(end,utc=True)]
        return df

    # fetch raw
    steps_raw   = fetch_records(map_steps)
    glucose_raw = fetch_records(map_glucose)
    energy_raw  = fetch_records(map_energy)
    heart_raw   = fetch_records(map_heart)
    sleep_raw   = fetch_records(map_sleep)

    # aggregate
    steps   = win(aggregate_steps(steps_raw))
    glucose = win(aggregate_glucose(glucose_raw))
    energy  = win(aggregate_daily_table(energy_raw,["date","timestamp"],{
        "active_kcal":["active_kcal"],
        "basal_kcal":["basal_kcal"],
    }))
    heart   = win(aggregate_daily_table(heart_raw,["date","timestamp"],{
        "resting_hr_bpm":["resting_hr_bpm","rhr","resting_hr","restingHeartRate"],
        "hrv_sdnn_ms":["hrv_sdnn_ms","hrv","rmssd"],
        "vo2max_ml_kg_min":["vo2max_ml_kg_min","vo2max"],
    }))
    sleep   = win(aggregate_daily_table(sleep_raw,["date","timestamp"],{
        "total_min":["total_min","sleep_duration_min","duration_min","minutes"],
        "core_min":["core_min"],
        "deep_min":["deep_min"],
        "rem_min":["rem_min"],
        "inbed_min":["inbed_min"],
    }))

    # mini data-quality printout
    def contrib(name, df):
        if df is None or df.empty:
            print(f"📦 {name}: 0 days")
            return
        days = int(df['date'].notna().sum())
        start = str(df['date'].min())
        end   = str(df['date'].max())
        cols  = [c for c in df.columns if c!='date']
        print(f"📦 {name}: {days} days, {start} → {end}, cols={cols}")

    contrib("steps", steps)
    contrib("glucose", glucose)
    contrib("energy", energy)
    contrib("heart", heart)
    contrib("sleep", sleep)

    # merge all
    dfs=[steps,glucose,energy,heart,sleep]
    base=None
    for d in dfs:
        if d is not None and not d.empty:
            base=d if base is None else pd.merge(base,d,on="date",how="outer")

    if base is None:
        return pd.DataFrame(columns=["date"])

    base = base.sort_values("date").reset_index(drop=True)

        # 🔹 Drop columns that are entirely empty (all NaNs)
    base = base.dropna(axis=1, how="all")

    # 🔹 Remove any duplicated column names that might appear after merges
    base = base.loc[:, ~base.columns.duplicated()]

    # lags 1..3 for numeric columns (but not for glucose_mean itself)
    for lag in [1,2,3]:
        for c in base.select_dtypes(include=[np.number]).columns:
            if c!="glucose_mean":
                base[f"{c}_lag{lag}"]=base[c].shift(lag)

    # moving averages (glucose)
    if "glucose_mean" in base.columns:
        base["glucose_mean_3d_ma"]=base["glucose_mean"].rolling(3,min_periods=2).mean()
        base["glucose_mean_7d_ma"]=base["glucose_mean"].rolling(7,min_periods=3).mean()

    # synthetic energy_score as total burn
    if {"active_kcal","basal_kcal"} <= set(base.columns):
        base["energy_score"]=base["active_kcal"]+base["basal_kcal"]

    # calendar context
    base["dow"]=pd.to_datetime(base["date"]).dt.dayofweek
    base["is_weekend"]=(base["dow"]>=5).astype(int)
    base["month"]=pd.to_datetime(base["date"]).dt.month
    base["dow_sin"]=np.sin(2*np.pi*base["dow"]/7)
    base["dow_cos"]=np.cos(2*np.pi*base["dow"]/7)

    return base


# =========================
# ---- MODEL HELPERS ----
# =========================

def drop_high_vif(data: pd.DataFrame, X_cols: List[str], thresh: float = 10.0) -> List[str]:
    """Greedy VIF pruning; safe for tiny or empty sets."""
    if not X_cols:
        return []
    X = data[X_cols].copy().dropna()
    keep = list(X.columns)
    # If < 2 columns, VIF not meaningful; just return as is
    if len(keep) < 2:
        return keep
    # loop with guards
    while True:
        if len(keep) < 2:
            break
        vifs = pd.Series([variance_inflation_factor(X[keep].values, i)
                          for i in range(len(keep))], index=keep)
        if vifs.empty:
            break
        worst = vifs.idxmax()
        if vifs.max() <= thresh:
            break
        keep.remove(worst)
    return keep

def lasso_screen(data: pd.DataFrame, X_cols: List[str], y_name: str) -> Tuple[List[str], Optional[float], Optional[float]]:
    """LASSO feature screen; safe if <2 features."""
    if not X_cols:
        return [], None, None
    if len(X_cols) < 2:
        return X_cols, None, None
    scaler = StandardScaler()
    Xs = scaler.fit_transform(data[X_cols])
    y = data[y_name].values
    try:
        lcv = LassoCV(cv=5, random_state=0).fit(Xs, y)
        nonzero = [c for c,w in zip(X_cols,lcv.coef_) if abs(w)>1e-8]
        return (nonzero if nonzero else X_cols), float(lcv.alpha_), float(lcv.score(Xs,y))
    except Exception:
        # fallback if LASSO fails due to degeneracy
        return X_cols, None, None

def best_lag_set(feat: pd.DataFrame, base_cols: List[str], y_name: str, max_lag: int = 3):
    """Pick lag (1..max_lag) by best AIC; returns (lag, aic, cols)."""
    # Filter out already-lagged columns so we don't double-lag
    base_cols = [c for c in base_cols if "_lag" not in c]
    candidates = []

    for lag in range(1, max_lag + 1):
        cols = []
        for c in base_cols:
            lagc = f"{c}_lag{lag}"
            if lagc in feat.columns:
                cols.append(lagc)

        # Always include stable calendar covariates
        for c in ["is_weekend", "dow_sin", "dow_cos", "month"]:
            if c in feat.columns:
                cols.append(c)

        df = feat[["date", y_name] + cols].dropna()
        if df.empty or not cols:
            continue
        try:
            X = sm.add_constant(df[cols])
            y = df[y_name]
            res = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": 3})
            candidates.append((lag, res.aic, cols))
        except Exception:
            continue

    return min(candidates, key=lambda x: x[1]) if candidates else (1, None, [])


# =========================
# ------ MODEL FIT -------
# =========================

def fit_models(feat: pd.DataFrame, preferred_target: Optional[str] = None):
    y_name = preferred_target or ("glucose_mean" if "glucose_mean" in feat else "energy_score")
    if y_name not in feat:
        raise RuntimeError("No suitable target found.")

    # base_cols: numeric non-target, not pre-averages or later lags
    base_cols = [c for c in feat.columns
                 if c not in ["date", y_name]
                 and feat[c].dtype.kind in "fi"
                 and not any(s in c for s in ["_ma","_lag2","_lag3"])]

    best_lag,_,X_cols = best_lag_set(feat, base_cols, y_name, 3)
    print(f"ℹ️ Using lag={best_lag}")
    if not X_cols:
        raise RuntimeError("No candidate predictors after lag selection.")

    data = feat[["date"]+X_cols+[y_name]].dropna()
    if data.empty:
        raise RuntimeError("No data rows after dropna.")

    keep_cols = drop_high_vif(data, X_cols, 10.0)
    if not keep_cols:
        raise RuntimeError("No predictors remain after VIF pruning.")
    if set(keep_cols)!=set(X_cols):
        dropped = set(X_cols)-set(keep_cols)
        print(f"ℹ️ Dropped high-VIF: {dropped}")
        X_cols=keep_cols

    nz, alpha, r2cv = lasso_screen(data, X_cols, y_name)
    if nz and set(nz)!=set(X_cols):
        print(f"ℹ️ LASSO kept {len(nz)}/{len(X_cols)}" + (f" (alpha={alpha:.3f}, cvR²={r2cv:.3f})" if alpha is not None else ""))
        X_cols = nz

    X = sm.add_constant(data[X_cols])
    y = data[y_name]
    ols = sm.OLS(y, X).fit(cov_type="HC3")
    hac = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags":3})
    return {"target":y_name,"X_cols":X_cols,"n_obs":len(data),"ols":ols,"hac":hac,"data":data}


# =========================
# -------- OUTPUT --------
# =========================

def create_results_dir() -> Tuple[Path, str]:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    d = RESULTS_ROOT / f"results_{ts}"
    d.mkdir(parents=True, exist_ok=True)
    return d, ts

def save_metrics(res: dict, d: Path, ts: str) -> Path:
    m = {res["target"]:{
        "n_obs":res["n_obs"],
        "r2_ols":float(res["ols"].rsquared),
        "r2_adj":float(res["ols"].rsquared_adj),
        "aic":float(res["ols"].aic),
        "bic":float(res["ols"].bic)
    }}
    p = d/"metrics.json"
    p.write_text(json.dumps(m,indent=2))
    print(f"📊 Saved metrics to {p}")
    return p

def write_human_summary(res: dict, outdir: Path) -> None:
    model = res["hac"]
    coefs = model.params.drop("const",errors="ignore")
    pvals = model.pvalues.drop("const",errors="ignore")
    eff = (pd.DataFrame({"coef":coefs,"p":pvals}).sort_values("p").head(5))
    lines = [
        f"Target: {res['target']}",
        f"n={res['n_obs']}  R²={model.rsquared:.3f}  adjR²={model.rsquared_adj:.3f}",
        "Top effects (HAC):"
    ]
    for i,r in eff.iterrows():
        direction = "↑" if r["coef"]>0 else "↓"
        lines.append(f"- {i}: {direction}{abs(r['coef']):.3f} (p={r['p']:.3f})")
    (outdir/"summary_readable.txt").write_text("\n".join(lines))

def make_pdf_report(d: Path, ts: str, metrics_path: Path) -> None:
    pdfp = d / f"model_report_{ts}.pdf"
    metrics = json.load(open(metrics_path))
    with PdfPages(pdfp) as pdf:
        fig,ax = plt.subplots(figsize=(8.5,11))
        ax.axis("off")
        ax.text(0.05,0.95,f"HealthCopilot Phase 3 Report {ts}",fontsize=18,weight="bold",va="top")
        y=0.9
        for t,vals in metrics.items():
            txt=f"{t}: "+", ".join(f"{k}={v:.3f}" if isinstance(v,(int,float)) else f"{k}={v}" for k,v in vals.items())
            ax.text(0.05,y,txt,fontsize=12,va="top"); y-=0.05
        pdf.savefig(fig); plt.close(fig)
    print(f"📄 PDF saved to {pdfp}")

def write_summaries(res,outdir):
    (outdir/"model_ols.txt").write_text(str(res["ols"].summary()))
    (outdir/"model_hac.txt").write_text(str(res["hac"].summary()))
    coefs=res["ols"].params.drop("const",errors="ignore")
    pvals=res["ols"].pvalues.drop("const",errors="ignore")
    effects=pd.DataFrame({"coef":coefs,"p":pvals}).sort_values("p")
    lines=[f"Target: {res['target']}",f"Observations used: {res['n_obs']}","","Top associations (by significance, OLS HC3):"]
    for idx,row in effects.head(10).iterrows():
        lines.append(f"  {idx:24s}  coef={row['coef']:+.4f}  p={row['p']:.4f}")
    lines.append("\nHeuristic N-of-1 ideas (non-causal):")
    for idx,row in effects.head(5).iterrows():
        direction="increase" if row["coef"]>0 else "decrease"
        pretty=idx.replace("_lag1"," (yesterday)")
        lines.append(f"- If you {direction} {pretty}, target shifts {row['coef']:+.3f} (p={row['p']:.3f}).")
    (outdir/"phase3_report.txt").write_text("\n".join(lines))
    write_human_summary(res,outdir)


# =========================
# --------- MAIN ---------
# =========================

def main():
    p = argparse.ArgumentParser(description="Phase 3 analytics for multiple targets")
    p.add_argument("--pb-url", default=env("PB_URL", "http://127.0.0.1:8090"))
    p.add_argument("--pb-email", default=env("PB_EMAIL"))
    p.add_argument("--pb-password", default=env("PB_PASSWORD"))
    p.add_argument("--pb-user-id", default=env("PB_USER_ID"))
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    p.add_argument("--map-steps", default="steps")
    p.add_argument("--map-glucose", default="glucose")
    p.add_argument("--map-energy", default="energy_daily")
    p.add_argument("--map-heart", default="heart_daily")
    p.add_argument("--map-sleep", default="sleep_daily")
    p.add_argument("--targets", default=None, help="Comma-separated list of target columns (optional)")
    args = p.parse_args()

    outdir, ts = create_results_dir()
    print(f"📁 Created results folder: {outdir}")

    # build features
    feat = make_daily_features(
        args.pb_url, args.pb_email, args.pb_password, args.pb_user_id,
        args.start, args.end,
        args.map_steps, args.map_glucose, args.map_energy,
        args.map_heart, args.map_sleep
    )
    feat.to_csv(outdir / "daily_features.csv", index=False)

    # choose targets
    if args.targets:
        targets = [t.strip() for t in args.targets.split(",") if t.strip()]
    else:
        exclude_keywords = ["lag", "ma", "sin", "cos"]
        exclude_exact = {"dow", "month", "is_weekend"}
        targets = [
            c for c in feat.select_dtypes(include=[np.number]).columns
            if not any(k in c for k in exclude_keywords)
            and c not in exclude_exact
            and not c.startswith("timestamp")
        ]
        print(f"🎯 Cleaned target list: {targets}")

    print(f"🎯 Targets to model: {targets}")

    all_metrics = {}

    for tgt in targets:
        try:
            print(f"\n🚀 Running model for target: {tgt}")
            res = fit_models(feat, tgt)

            subdir = outdir / tgt
            subdir.mkdir(exist_ok=True)

            # write per-target artifacts
            (subdir/"daily_features.columns.txt").write_text("\n".join(feat.columns))
            write_summaries(res, subdir)
            metrics_path = save_metrics(res, subdir, ts)
            make_pdf_report(subdir, ts, metrics_path)

            all_metrics[tgt] = {
                "n_obs": res["n_obs"],
                "r2": float(res["ols"].rsquared),
                "adj_r2": float(res["ols"].rsquared_adj),
                "aic": float(res["ols"].aic),
                "bic": float(res["ols"].bic),
            }
            print(f"✅ Done: {tgt} (n={res['n_obs']})")

        except Exception as e:
            print(f"❌ Failed {tgt}: {e}")

    # combined summary
    dashboard_path = outdir / "summary_dashboard.txt"
    with open(dashboard_path, "w") as f:
        f.write(f"📊 HealthCopilot Phase 3 Dashboard {ts}\n")
        f.write("=" * 60 + "\n\n")
        if not all_metrics:
            f.write("No successful models. Check data coverage and logs.\n")
        else:
            for tgt, vals in all_metrics.items():
                f.write(f"{tgt:24s} | n={vals['n_obs']:3d} | R²={vals['r2']:.3f} | adjR²={vals['adj_r2']:.3f} | AIC={vals['aic']:.1f}\n")
    print(f"\n📄 Combined dashboard saved: {dashboard_path}")

        # === Extended readable summary across models ===
    extended = outdir / "summary_top_effects.txt"
    with open(extended, "w") as f:
        f.write(f"📊 HealthCopilot Phase 3 — Top Predictors per Model ({ts})\n")
        f.write("="*70 + "\n\n")
        for tgt in all_metrics.keys():
            summ_path = outdir / tgt / "model_ols.txt"
            if not summ_path.exists():
                continue
            lines = [ln.strip() for ln in open(summ_path) if ln.strip()]
            header = f"[{tgt}] — n={all_metrics[tgt]['n_obs']}, R²={all_metrics[tgt]['r2']:.3f}\n"
            f.write(header)
            # extract top 5 coef lines quickly
            found = False
            for ln in lines:
                if re.match(r"^[A-Za-z_].*\s+[-+]?\d", ln):
                    f.write("  " + ln + "\n")
                    found = True
                    if lines.index(ln) > 5:
                        break
            if not found:
                f.write("  (no predictors found)\n")
            f.write("\n")
    print(f"📄 Extended summary saved: {extended}")


    print("\n✅ ALL DONE")
    print(f"📦 Results folder: {outdir}")


if __name__=="__main__":
    main()
