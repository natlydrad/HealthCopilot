#!/usr/bin/env python3
"""
Stability judge: run each golden entry N times (default 5) and report variance.
Use to distinguish prompt ambiguity (high variance at temp=0) from systematic errors.

Usage:
  cd ml-pipeline/nutrition-pipeline
  USE_PARSING_CACHE=false REGRESSION_MODE=true python regression/run_stability.py
  python regression/run_stability.py --n 3
"""

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("USE_PARSING_CACHE", "false")
os.environ.setdefault("REGRESSION_MODE", "true")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from regression.regression_runner import run_stability_check


def _load_golden_entries():
    """Load golden set from PARSE_API_URL/regression/golden-set or from golden_set.json file."""
    api_url = (os.getenv("PARSE_API_URL") or os.getenv("PARSE_API_BASE") or "").strip().rstrip("/")
    if api_url:
        try:
            import urllib.request
            req = urllib.request.Request(f"{api_url}/regression/golden-set")
            with urllib.request.urlopen(req, timeout=30) as resp:
                golden = json.loads(resp.read().decode())
            return golden.get("entries") or []
        except Exception as e:
            print(f"WARNING: Could not fetch golden set from API: {e}")
    golden_path = Path(__file__).parent / "golden_set.json"
    if golden_path.exists():
        with open(golden_path) as f:
            golden = json.load(f)
        return golden.get("entries") or []
    return None


def main():
    p = argparse.ArgumentParser(description="Run golden set N times per entry and report stability")
    p.add_argument("--n", type=int, default=5, help="Runs per entry (default 5)")
    p.add_argument("--tier", choices=("mvp", "full"), default=None, help="Parse flow tier (default from env or full)")
    p.add_argument("--limit", type=int, default=None, help="Limit to first N entries (default all)")
    args = p.parse_args()

    if args.tier:
        os.environ["PARSE_FLOW_TIER"] = args.tier

    entries = _load_golden_entries()
    if entries is None:
        print("ERROR: Set PARSE_API_URL to fetch golden set from API, or provide regression/golden_set.json")
        sys.exit(1)
    if args.limit:
        entries = entries[: args.limit]
    if not entries:
        print("No entries in golden set")
        sys.exit(0)
    if not entries:
        print("No entries in golden set")
        sys.exit(0)

    print(f"Running stability check: {len(entries)} entries x {args.n} runs...")
    report = run_stability_check(entries, n=args.n, tier=args.tier)

    agg = report["aggregate"]
    print()
    print("Aggregate:")
    print(f"  Exact-structure match rate: {agg['exact_match_rate_pct']}%")
    print(f"  Mean field stability:       {agg['mean_field_stability_pct']}%")
    print(f"  95th percentile calorie std: {agg['calorie_std_95th']}")
    print(f"  Tier: {agg['tier']}, n_runs_per_entry: {agg['n_runs_per_entry']}")

    failures = [e for e in report["per_entry"] if not e["exact_match"]]
    if failures:
        print()
        print(f"Entries with structure variance ({len(failures)}):")
        for e in failures[:10]:
            print(f"  {e['id']}: field_stability={e['field_stability_pct']}% max_cal_std={e['max_calorie_std']}")
        if len(failures) > 10:
            print(f"  ... and {len(failures) - 10} more")

    sys.exit(0)


if __name__ == "__main__":
    main()
