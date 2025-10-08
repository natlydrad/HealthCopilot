#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, argparse, json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

import pandas as pd
import numpy as np
import statsmodels.api as sm
from statsmodels.stats.outliers_influence import variance_inflation_factor
from sklearn.linear_model import LassoCV
from sklearn.preprocessing import StandardScaler
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from pb_client import get_token, fetch_records, PB_URL


# ------------------------- UTILITIES -------------------------

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

def safe_group_daily(df: pd.DataFrame, ts_col: str, val_col: str, agg: str = "mean") -> pd.DataFrame:
    if ts_col not in df.columns:
        raise ValueError(f"Timestamp column '{ts_col}' not found in DataFrame.")
    df = df.dropna(subset=[ts_col, val_col])
    grouped = (
        df.groupby(df[ts_col].dt.floor("D"), as_index=False)[val_col]
        .agg(agg)
        .rename(columns={ts_col: "date", val_col: val_col})
    )
    grouped["date"] = pd.to_datetime(grouped.iloc[:, 0], utc=True).dt.floor("D")
    return grouped


# ------------------------- AGGREGATORS -------------------------

def aggregate_steps(raw: List[Dict[str, Any]]) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame(columns=["date", "steps_sum"])
    df = pd.DataFrame(raw)
    ts_col = next((c for c in ["timestamp","date","created","updated"] if c in df.columns), None)
    if not ts_col:
        return pd.DataFrame(columns=["date", "steps_sum"])
    df["ts"] = to_datetime_utc(df[ts_col])
    df["steps_val"] = df.apply(lambda r: coalesce_number(r, ["steps","count","value"]), axis=1)
    g = safe_group_daily(df, "ts", "steps_val", agg="sum")
    g.rename(columns={"steps_val":"steps_sum"}, inplace=True)
    return g[["date","steps_sum"]].sort_values("date")


def aggregate_glucose(raw: List[Dict[str, Any]]) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame(columns=["date","glucose_mean"])
    df = pd.DataFrame(raw)
    ts_col = next((c for c in ["timestamp","date","created","updated","time","recorded_at"] if c in df.columns), None)
    val_col = next((c for c in ["glucose","value","value_mgdl","mgdl","mg_dL","mgdl_value","glucose_mgdl","reading"] if c in df.columns), None)
    if not ts_col or not val_col:
        print("⚠️ Skipping glucose: missing timestamp or value col.")
        return pd.DataFrame(columns=["date","glucose_mean"])
    df["ts"] = to_datetime_utc(df[ts_col])
    df["g"] = pd.to_numeric(df[val_col], errors="coerce")
    g = safe_group_daily(df, "ts", "g", agg="mean")
    g.rename(columns={"g":"glucose_mean"}, inplace=True)
    return g[["date","glucose_mean"]].sort_values("date")


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
    return out


# ------------------------- FEATURE BUILDER -------------------------

def make_daily_features(base_url, email, password, user_id, start, end,
                        map_steps, map_glucose, map_energy, map_heart, map_sleep):

    token = get_token()
    print("🔑 PocketBase token acquired.")
    filt = f'user="{user_id}"' if user_id else None

    def win(df):
        if df is None or df.empty: return df
        if start: df = df[df["date"]>=pd.to_datetime(start,utc=True)]
        if end: df = df[df["date"]<=pd.to_datetime(end,utc=True)]
        return df

    steps_raw, glucose_raw = fetch_records(map_steps), fetch_records(map_glucose)
    energy_raw, heart_raw, sleep_raw = fetch_records(map_energy), fetch_records(map_heart), fetch_records(map_sleep)

    steps = win(aggregate_steps(steps_raw))
    glucose = win(aggregate_glucose(glucose_raw))
    energy = win(aggregate_daily_table(energy_raw,["date","timestamp"],{"active_kcal":["active_kcal"],"basal_kcal":["basal_kcal"]}))
    heart  = win(aggregate_daily_table(heart_raw,["date","timestamp"],{
        "resting_hr_bpm":["resting_hr_bpm","rhr","resting_hr","restingHeartRate"],
        "hrv_sdnn_ms":["hrv_sdnn_ms","hrv","rmssd"],
        "vo2max_ml_kg_min":["vo2max_ml_kg_min","vo2max"]
    }))
    sleep = win(aggregate_daily_table(sleep_raw,["date","timestamp"],{
        "total_min":["total_min","sleep_duration_min","duration_min","minutes"],
        "core_min":["core_min"],"deep_min":["deep_min"],
        "rem_min":["rem_min"],"inbed_min":["inbed_min"]
    }))

    dfs=[steps,glucose,energy,heart,sleep]
    base=None
    for d in dfs:
        if d is not None and not d.empty:
            base=d if base is None else pd.merge(base,d,on="date",how="outer")

    if base is None: return pd.DataFrame(columns=["date"])
    base=base.sort_values("date").reset_index(drop=True)

    # lags
    for lag in [1,2,3]:
        for c in base.select_dtypes(include=[np.number]).columns:
            if c!="glucose_mean":
                base[f"{c}_lag{lag}"]=base[c].shift(lag)

    # moving averages
    if "glucose_mean" in base.columns:
        base["glucose_mean_3d_ma"]=base["glucose_mean"].rolling(3,min_periods=2).mean()
        base["glucose_mean_7d_ma"]=base["glucose_mean"].rolling(7,min_periods=3).mean()

    if {"active_kcal","basal_kcal"}<=set(base.columns):
        base["energy_score"]=base["active_kcal"]+base["basal_kcal"]

    # calendar context
    base["dow"]=pd.to_datetime(base["date"]).dt.dayofweek
    base["is_weekend"]=(base["dow"]>=5).astype(int)
    base["month"]=pd.to_datetime(base["date"]).dt.month
    base["dow_sin"]=np.sin(2*np.pi*base["dow"]/7)
    base["dow_cos"]=np.cos(2*np.pi*base["dow"]/7)

    return base


# ------------------------- MODEL HELPERS -------------------------

def drop_high_vif(data, X_cols, thresh=10.0):
    X=data[X_cols].copy().dropna()
    keep=list(X.columns)
    while True:
        vifs=pd.Series([variance_inflation_factor(X[keep].values,i)
                        for i in range(len(keep))],index=keep)
        worst=vifs.idxmax()
        if vifs.max()<=thresh or len(keep)<=2:
            break
        keep.remove(worst)
    return keep

def lasso_screen(data, X_cols, y_name):
    scaler=StandardScaler()
    Xs=scaler.fit_transform(data[X_cols])
    y=data[y_name].values
    lcv=LassoCV(cv=5,random_state=0).fit(Xs,y)
    nonzero=[c for c,w in zip(X_cols,lcv.coef_) if abs(w)>1e-8]
    return nonzero,lcv.alpha_,lcv.score(Xs,y)

def best_lag_set(feat, base_cols, y_name, max_lag=3):
    candidates=[]
    for lag in range(1,max_lag+1):
        cols=[]
        for c in base_cols:
            lagc=f"{c}_lag{lag}"
            if lagc in feat.columns: cols.append(lagc)
        for c in ["is_weekend","dow_sin","dow_cos","month"]:
            if c in feat.columns: cols.append(c)
        df=feat[["date",y_name]+cols].dropna()
        if df.empty: continue
        X=sm.add_constant(df[cols])
        y=df[y_name]
        res=sm.OLS(y,X).fit(cov_type="HAC",cov_kwds={"maxlags":3})
        candidates.append((lag,res.aic,cols))
    return min(candidates,key=lambda x:x[1]) if candidates else (1,None,[])


# ------------------------- MODEL FIT -------------------------

def fit_models(feat: pd.DataFrame, preferred_target=None):
    y_name=preferred_target or ("glucose_mean" if "glucose_mean" in feat else "energy_score")
    if y_name not in feat: raise RuntimeError("No suitable target found.")
    base_cols=[c for c in feat.columns if c not in ["date",y_name] and not c.endswith(("_ma","_lag2","_lag3"))]
    best_lag,_,X_cols=best_lag_set(feat,base_cols,y_name,3)
    print(f"ℹ️ Using lag={best_lag}")
    data=feat[["date"]+X_cols+[y_name]].dropna()
    if data.empty: raise RuntimeError("No data rows after dropna")

    keep_cols=drop_high_vif(data,X_cols,10.0)
    if set(keep_cols)!=set(X_cols):
        print("ℹ️ Dropped high-VIF:",set(X_cols)-set(keep_cols))
        X_cols=keep_cols
    nz,alpha,r2cv=lasso_screen(data,X_cols,y_name)
    if nz:
        print(f"ℹ️ LASSO kept {len(nz)}/{len(X_cols)} (alpha={alpha:.3f},cvR²={r2cv:.3f})")
        X_cols=nz

    X=sm.add_constant(data[X_cols])
    y=data[y_name]
    ols=sm.OLS(y,X).fit(cov_type="HC3")
    hac=sm.OLS(y,X).fit(cov_type="HAC",cov_kwds={"maxlags":3})
    return {"target":y_name,"X_cols":X_cols,"n_obs":len(data),"ols":ols,"hac":hac,"data":data}


# ------------------------- OUTPUT -------------------------

RESULTS_ROOT=Path("/Users/natalieradu/Desktop/HealthCopilot/RESULTS")

def create_results_dir():
    ts=datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    d=RESULTS_ROOT/f"results_{ts}"
    d.mkdir(parents=True,exist_ok=True)
    return d,ts

def save_metrics(res,d,ts):
    m={res["target"]:{
        "n_obs":res["n_obs"],
        "r2_ols":float(res["ols"].rsquared),
        "r2_adj":float(res["ols"].rsquared_adj),
        "aic":float(res["ols"].aic),
        "bic":float(res["ols"].bic)
    }}
    p=d/"metrics.json"
    p.write_text(json.dumps(m,indent=2))
    print(f"📊 Saved metrics to {p}")
    return p

def write_human_summary(res,outdir):
    ols=res["hac"]
    coefs=ols.params.drop("const",errors="ignore")
    pvals=ols.pvalues.drop("const",errors="ignore")
    eff=(pd.DataFrame({"coef":coefs,"p":pvals}).sort_values("p").head(5))
    lines=[f"Target: {res['target']}",f"n={res['n_obs']} R²={ols.rsquared:.3f} adjR²={ols.rsquared_adj:.3f}","Top effects (HAC):"]
    for i,r in eff.iterrows():
        direction="↑" if r["coef"]>0 else "↓"
        lines.append(f"- {i}: {direction}{abs(r['coef']):.3f} (p={r['p']:.3f})")
    (outdir/"summary_readable.txt").write_text("\n".join(lines))

def make_pdf_report(d,ts,metrics_path):
    pdfp=d/f"model_report_{ts}.pdf"
    metrics=json.load(open(metrics_path))
    with PdfPages(pdfp) as pdf:
        fig,ax=plt.subplots(figsize=(8.5,11))
        ax.axis("off")
        ax.text(0.05,0.95,f"HealthCopilot Phase3 Report {ts}",fontsize=18,weight="bold",va="top")
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


# ------------------------- MAIN -------------------------

def main():
    p=argparse.ArgumentParser(description="Phase3 analytics")
    p.add_argument("--pb-url",default=env("PB_URL","http://127.0.0.1:8090"))
    p.add_argument("--pb-email",default=env("PB_EMAIL"))
    p.add_argument("--pb-password",default=env("PB_PASSWORD"))
    p.add_argument("--pb-user-id",default=env("PB_USER_ID"))
    p.add_argument("--start",default=None); p.add_argument("--end",default=None)
    p.add_argument("--map-steps",default="steps"); p.add_argument("--map-glucose",default="glucose")
    p.add_argument("--map-energy",default="energy_daily"); p.add_argument("--map-heart",default="heart_daily")
    p.add_argument("--map-sleep",default="sleep_daily")
    p.add_argument("--target",default=None)
    args=p.parse_args()

    outdir,ts=create_results_dir()
    print(f"📁 Created results folder: {outdir}")

    feat=make_daily_features(args.pb_url,args.pb_email,args.pb_password,args.pb_user_id,
                             args.start,args.end,args.map_steps,args.map_glucose,
                             args.map_energy,args.map_heart,args.map_sleep)
    feat.to_csv(outdir/"daily_features.csv",index=False)
    if feat.dropna(how="all",axis=1).shape[0]<7:
        print("⚠️ Not enough rows to fit model."); return
    res=fit_models(feat,args.target)
    write_summaries(res,outdir)
    mp=save_metrics(res,outdir,ts)
    make_pdf_report(outdir,ts,mp)
    print(f"✅ Target: {res['target']} n={res['n_obs']}")

if __name__=="__main__":
    main()
