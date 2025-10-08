#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, argparse
from pb_client import get_token, fetch_records, PB_URL
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
import statsmodels.api as sm


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
    """
    Robust daily aggregator that always returns ['date', <val_col>].
    It tolerates missing or unnamed index columns.
    """
    if ts_col not in df.columns:
        raise ValueError(f"Timestamp column '{ts_col}' not found in DataFrame.")
    df = df.dropna(subset=[ts_col, val_col])
    grouped = (
        df.groupby(df[ts_col].dt.floor("D"), as_index=False)[val_col]
        .agg(agg)
        .rename(columns={ts_col: "date", val_col: val_col})
    )
    # ensure 'date' exists even if pandas drops it
    grouped["date"] = grouped.iloc[:, 0]
    grouped["date"] = pd.to_datetime(grouped["date"], utc=True).dt.floor("D")
    return grouped


# ------------------------- AGGREGATORS -------------------------

def aggregate_steps(raw: List[Dict[str, Any]]) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame(columns=["date", "steps_sum"])
    df = pd.DataFrame(raw)
    ts_col = None
    for c in ["timestamp", "date", "created", "updated"]:
        if c in df.columns:
            ts_col = c
            break
    if ts_col is None:
        return pd.DataFrame(columns=["date", "steps_sum"])
    df["ts"] = to_datetime_utc(df[ts_col])
    df["steps_val"] = df.apply(lambda r: coalesce_number(r, ["steps", "count", "value"]), axis=1)
    grouped = safe_group_daily(df, "ts", "steps_val", agg="sum")
    grouped.rename(columns={"steps_val": "steps_sum"}, inplace=True)
    return grouped[["date", "steps_sum"]].sort_values("date")


def aggregate_glucose(raw: List[Dict[str, Any]]) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame(columns=["date", "glucose_mean"])
    df = pd.DataFrame(raw)

    # detect timestamp
    ts_col = None
    for c in ["timestamp", "date", "created", "updated", "time", "recorded_at"]:
        if c in df.columns:
            ts_col = c
            break

    # detect glucose value
    val_col = None
    for candidate in ["glucose", "value", "value_mgdl", "mgdl", "mg_dL", "mgdl_value", "glucose_mgdl", "reading"]:
        if candidate in df.columns:
            val_col = candidate
            break

    if ts_col is None or val_col is None:
        print("⚠️ Skipping glucose: missing timestamp or value column.")
        print("Available columns:", list(df.columns))
        return pd.DataFrame(columns=["date", "glucose_mean"])

    df["ts"] = to_datetime_utc(df[ts_col])
    df["g"] = pd.to_numeric(df[val_col], errors="coerce")

    grouped = safe_group_daily(df, "ts", "g", agg="mean")
    grouped.rename(columns={"g": "glucose_mean"}, inplace=True)
    return grouped[["date", "glucose_mean"]].sort_values("date")



def aggregate_daily_table(
    raw: List[Dict[str, Any]],
    date_col_candidates: List[str],
    numeric_map: Dict[str, List[str]],
) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame(columns=["date"] + list(numeric_map.keys()))
    df = pd.DataFrame(raw)
    date_col = None
    for c in date_col_candidates + ["date", "timestamp", "created", "updated"]:
        if c in df.columns:
            date_col = c
            break
    if date_col is None:
        return pd.DataFrame(columns=["date"] + list(numeric_map.keys()))
    df["date"] = pd.to_datetime(df[date_col], utc=True, errors="coerce").dt.floor("D")
    for out_col, candidates in numeric_map.items():
        df[out_col] = df.apply(lambda r: coalesce_number(r, candidates), axis=1)
    cols = ["date"] + list(numeric_map.keys())
    df = df[cols].dropna(subset=["date"])
    agg_map = {c: "mean" for c in numeric_map.keys()}
    out = df.groupby("date", as_index=False).agg(agg_map).sort_values("date")
    out["date"] = pd.to_datetime(out["date"], utc=True).dt.floor("D")
    return out


# ------------------------- PIPELINE -------------------------

def make_daily_features(
    base_url: str,
    email: Optional[str],
    password: Optional[str],
    user_id: Optional[str],
    start: Optional[str],
    end: Optional[str],
    map_steps: str,
    map_glucose: str,
    map_energy: str,
    map_heart: str,
    map_sleep: str,
) -> pd.DataFrame:
    token = get_token()
    print("🔑 PocketBase token acquired.")
    filt = f'user="{user_id}"' if user_id else None

    def add_window(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return df
        if start:
            df = df[df["date"] >= pd.to_datetime(start, utc=True)]
        if end:
            df = df[df["date"] <= pd.to_datetime(end, utc=True)]
        return df

    steps_raw = fetch_records(map_steps)
    glucose_raw = fetch_records(map_glucose)
    energy_raw = fetch_records(map_energy)
    heart_raw  = fetch_records(map_heart)
    sleep_raw  = fetch_records(map_sleep)

    steps = add_window(aggregate_steps(steps_raw))
    glucose = add_window(aggregate_glucose(glucose_raw))

    energy = add_window(aggregate_daily_table(
    energy_raw, ["date", "timestamp"], {
        "active_kcal": ["active_kcal"],
        "basal_kcal": ["basal_kcal"],
    }))

    heart = add_window(aggregate_daily_table(
        heart_raw, ["date", "timestamp"], {
            "resting_hr_bpm": ["resting_hr_bpm", "rhr", "resting_hr", "restingHeartRate"],
            "hrv_sdnn_ms": ["hrv_sdnn_ms", "hrv", "rmssd"],
            "vo2max_ml_kg_min": ["vo2max_ml_kg_min", "vo2max"],
        }))

    sleep = add_window(aggregate_daily_table(
        sleep_raw, ["date", "timestamp"], {
            "total_min": ["total_min", "sleep_duration_min", "duration_min", "minutes"],
            "core_min": ["core_min"],
            "deep_min": ["deep_min"],
            "rem_min": ["rem_min"],
            "inbed_min": ["inbed_min"],
        }))

    dfs = [steps, glucose, energy, heart, sleep]
    base = None
    for d in dfs:
        if d is None or d.empty:
            continue
        base = d if base is None else pd.merge(base, d, on="date", how="outer")

    if base is None:
        return pd.DataFrame(columns=["date"])

    base = base.sort_values("date").reset_index(drop=True)

    for c in base.select_dtypes(include=[np.number]).columns:
        if c != "glucose_mean":
            base[f"{c}_lag1"] = base[c].shift(1)


    if "glucose_mean" in base.columns:
        base["glucose_mean_3d_ma"] = base["glucose_mean"].rolling(3, min_periods=2).mean()
        base["glucose_mean_7d_ma"] = base["glucose_mean"].rolling(7, min_periods=3).mean()

    # synthetic daily energy target
    if "active_kcal" in base.columns and "basal_kcal" in base.columns:
        base["energy_score"] = base["active_kcal"] + base["basal_kcal"]


    return base


# ------------------------- MODELING -------------------------

def fit_models(feat: pd.DataFrame, preferred_target: Optional[str] = None):
    feat = feat.copy()
    y_name = preferred_target or ("glucose_mean" if "glucose_mean" in feat else "energy_score")
    if y_name not in feat:
        raise RuntimeError("No suitable target found (need 'glucose_mean' or 'energy_score').")
    X_cols = [c for c in feat.columns if c.endswith("_lag1") or c in ["steps_sum"]]
    X_cols = [c for c in X_cols if c in feat]
    data = feat[["date"] + X_cols + [y_name]].dropna().copy()
    if data.empty:
        raise RuntimeError("No rows after dropna; check your fields/collections.")
    X = sm.add_constant(data[X_cols])
    y = data[y_name]
    ols = sm.OLS(y, X).fit(cov_type="HC3")
    hac = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": 3})
    return {"target": y_name, "X_cols": X_cols, "n_obs": len(data), "ols": ols, "hac": hac, "data": data}


def write_summaries(res, outdir: Path) -> None:
    (outdir / "model_ols.txt").write_text(str(res["ols"].summary()), encoding="utf-8")
    (outdir / "model_hac.txt").write_text(str(res["hac"].summary()), encoding="utf-8")
    coefs = res["ols"].params.drop("const", errors="ignore")
    pvals = res["ols"].pvalues.drop("const", errors="ignore")
    effects = pd.DataFrame({"coef": coefs, "p": pvals}).sort_values("p")
    lines = []
    lines.append(f"Target: {res['target']}")
    lines.append(f"Observations used: {res['n_obs']}")
    lines.append("")
    lines.append("Top associations (by significance, OLS HC3):")
    for idx, row in effects.head(10).iterrows():
        lines.append(f"  {idx:24s}  coef={row['coef']:+.4f}  p={row['p']:.4f}")
    lines.append("")
    lines.append("Heuristic N-of-1 ideas (non-causal):")
    for idx, row in effects.head(5).iterrows():
        direction = "increase" if row["coef"] > 0 else "decrease"
        pretty = idx.replace("_lag1", " (yesterday)")
        lines.append(f"- If you {direction} {pretty}, the model predicts target shifts {row['coef']:+.3f} (p={row['p']:.3f}).")
    (outdir / "phase3_report.txt").write_text("\n".join(lines), encoding="utf-8")

from datetime import datetime
import json
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


RESULTS_ROOT = Path("/Users/natalieradu/Desktop/HealthCopilot/RESULTS")


def create_results_dir() -> tuple[Path, str]:
    """Create timestamped results folder inside fixed /RESULTS directory."""
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    results_dir = RESULTS_ROOT / f"results_{ts}"
    results_dir.mkdir(parents=True, exist_ok=True)
    return results_dir, ts


def save_metrics(res: dict, results_dir: Path, timestamp: str):
    """Save metrics JSON for reporting."""
    metrics = {
        res["target"]: {
            "n_obs": res["n_obs"],
            "r2_ols": float(res["ols"].rsquared),
            "r2_adj": float(res["ols"].rsquared_adj),
            "aic": float(res["ols"].aic),
            "bic": float(res["ols"].bic),
        }
    }
    path = results_dir / "metrics.json"
    with open(path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"📊 Saved metrics to {path}")
    return path


def make_pdf_report(results_dir: Path, timestamp: str, metrics_path: Path):
    """Create a summary PDF like your old make_report.py."""
    pdf_path = results_dir / f"model_report_{timestamp}.pdf"
    with open(metrics_path) as f:
        metrics = json.load(f)

    with PdfPages(pdf_path) as pdf:
        fig, ax = plt.subplots(figsize=(8.5, 11))
        ax.axis("off")
        ax.text(0.05, 0.95, f"HealthCopilot Phase 3 Report {timestamp}", fontsize=18, weight="bold", va="top")

        y = 0.9
        for target, vals in metrics.items():
            txt = f"{target}: " + ", ".join(
                f"{k}={v:.3f}" if isinstance(v, (int, float)) else f"{k}={v}" for k, v in vals.items()
            )
            ax.text(0.05, y, txt, fontsize=12, va="top")
            y -= 0.05

        pdf.savefig(fig)
        plt.close(fig)

    print(f"📄 PDF summary saved at {pdf_path}")



# ------------------------- MAIN -------------------------

def main():
    parser = argparse.ArgumentParser(description="Phase 3 PocketBase → Analytics")
    parser.add_argument("--pb-url", default=env("PB_URL", "http://127.0.0.1:8090"))
    parser.add_argument("--pb-email", default=env("PB_EMAIL"))
    parser.add_argument("--pb-password", default=env("PB_PASSWORD"))
    parser.add_argument("--pb-user-id", default=env("PB_USER_ID"))
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--map-steps", default="steps")
    parser.add_argument("--map-glucose", default="glucose")
    parser.add_argument("--map-energy", default="energy_daily")
    parser.add_argument("--map-heart", default="heart_daily")
    parser.add_argument("--map-sleep", default="sleep_daily")
    parser.add_argument("--outdir", default=".")
    parser.add_argument("--target", default=None, help="Override target column (e.g., glucose_mean)")
    args = parser.parse_args()

    outdir, timestamp = create_results_dir()
    print(f"📁 Created results folder: {outdir}")



    feat = make_daily_features(
        base_url=args.pb_url,
        email=args.pb_email,
        password=args.pb_password,
        user_id=args.pb_user_id,
        start=args.start,
        end=args.end,
        map_steps=args.map_steps,
        map_glucose=args.map_glucose,
        map_energy=args.map_energy,
        map_heart=args.map_heart,
        map_sleep=args.map_sleep,
    )

    feat.to_csv(outdir / "daily_features.csv", index=False)

    if feat.dropna(how="all", axis=1).shape[0] < 7:
        print("⚠️ Not enough rows to fit models. Saved daily_features.csv for inspection.")
        return

    res = fit_models(feat, preferred_target=args.target)
    write_summaries(res, outdir)
    metrics_path = save_metrics(res, outdir, timestamp)
    make_pdf_report(outdir, timestamp, metrics_path)


    print(f"✅ Target: {res['target']}  n={res['n_obs']}")
    print("Artifacts written:")
    for p in ["daily_features.csv", "model_ols.txt", "model_hac.txt", "phase3_report.txt"]:
        print(" -", str((outdir / p).resolve()))


if __name__ == "__main__":
    main()
