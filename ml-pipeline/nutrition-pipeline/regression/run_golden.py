#!/usr/bin/env python3
"""
Run golden set: parse each entry, compare to expected, run production checks and invariants.
Appends one JSONL row to golden_results.jsonl with timestamp, version, tier, pass_count, fail_count, total, pass_rate, by_category, by_tag.

Usage:
  cd ml-pipeline/nutrition-pipeline
  USE_PARSING_CACHE=false REGRESSION_MODE=true python regression/run_golden.py
  PARSE_FLOW_TIER=mvp PARSE_PROMPT_VERSION=v0-mvp python regression/run_golden.py
  GOLDEN_TAGS=text_only,image_only python regression/run_golden.py   # only entries with these tags
  python regression/run_golden.py --tags text_only,image_and_text
"""

import argparse
import json
import os
import sys
from datetime import timezone
from pathlib import Path

GOLDEN_TAG_VALUES = frozenset({"text_only", "image_only", "image_and_text", "memory_pantry", "unique_inputs"})

os.environ.setdefault("USE_PARSING_CACHE", "false")
os.environ.setdefault("REGRESSION_MODE", "true")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from regression.regression_runner import (
    parse_meal_text_to_ingredients,
    compare_golden_actual_to_expected,
    evaluate_production_checks,
    evaluate_invariants,
)


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
    parser = argparse.ArgumentParser(description="Run golden set regression")
    parser.add_argument("--tags", type=str, default=None, help="Comma-separated tags to run only entries with at least one (e.g. text_only,image_only)")
    args = parser.parse_args()

    entries = _load_golden_entries()
    if entries is None:
        print("ERROR: Set PARSE_API_URL to fetch golden set from API, or provide regression/golden_set.json")
        sys.exit(1)
    if not entries:
        print("No golden entries (empty set or API returned none). Exiting.")
        sys.exit(0)

    filter_tags = None
    tags_env = (os.getenv("GOLDEN_TAGS") or "").strip()
    tags_arg = (args.tags or "").strip()
    if tags_arg:
        filter_tags = [t.strip().lower() for t in tags_arg.split(",") if t.strip()]
    elif tags_env:
        filter_tags = [t.strip().lower() for t in tags_env.split(",") if t.strip()]
    if filter_tags:
        entries = [e for e in entries if any(t in (e.get("tags") or []) for t in filter_tags)]
        if not entries:
            print("No entries match the given tags filter. Exiting.")
            sys.exit(0)

    tier = (os.getenv("PARSE_FLOW_TIER") or "full").strip().lower()
    if tier not in ("mvp", "full"):
        tier = "full"
    flow = (os.getenv("PARSE_FLOW") or "name_first").strip().lower()
    if flow not in ("name_first", "gpt_first"):
        flow = "name_first"
    version = (os.getenv("PARSE_PROMPT_VERSION") or "unknown").strip()

    print(f"Running golden set: {len(entries)} entries (tier={tier}, flow={flow}, version={version})")
    if filter_tags:
        print(f"Filter: tags in {filter_tags}")
    print()

    results = []
    by_category = {}
    by_tag = {t: {"pass": 0, "fail": 0} for t in GOLDEN_TAG_VALUES}
    for entry in entries:
        entry_id = entry.get("id") or ""
        text = (entry.get("input") or {}).get("text") or ""
        expected_dict = entry.get("expected") or {}
        expected_ingredients = expected_dict.get("ingredients") or []
        expected_options = {k: v for k, v in expected_dict.items() if k != "ingredients"}
        category = (entry.get("category") or "normal").strip().lower()
        if category not in ("easy", "normal", "evil"):
            category = "normal"
        entry_tags = entry.get("tags") or []

        try:
            actual = parse_meal_text_to_ingredients(text, tier=tier, flow=flow)
            normalized = []
            for ing in actual:
                ing_copy = dict(ing) if isinstance(ing, dict) else {}
                nut = ing_copy.get("nutrition")
                if isinstance(nut, str):
                    try:
                        ing_copy["nutrition"] = json.loads(nut)
                    except (TypeError, ValueError):
                        pass
                normalized.append(ing_copy)
            actual = normalized

            compare_ok, compare_failures, _nutrient_details = compare_golden_actual_to_expected(
                actual, expected_ingredients, expected_options
            )
            prod_ok, prod_failures = evaluate_production_checks(actual)
            inv_ok, inv_failures = evaluate_invariants(actual)
            passed = compare_ok and prod_ok and inv_ok
            failures = list(compare_failures) + list(prod_failures) + list(inv_failures)
        except Exception as e:
            passed = False
            failures = [str(e)]

        results.append({"id": entry_id, "passed": passed, "category": category, "tags": entry_tags})
        if category not in by_category:
            by_category[category] = {"pass": 0, "fail": 0}
        if passed:
            by_category[category]["pass"] += 1
        else:
            by_category[category]["fail"] += 1
            print(f"FAIL {entry_id} ({category}): {text[:60]}...")
            for f in failures[:3]:
                print(f"     - {f}")
        for tag in entry_tags:
            if tag in by_tag:
                if passed:
                    by_tag[tag]["pass"] += 1
                else:
                    by_tag[tag]["fail"] += 1

    pass_count = sum(1 for r in results if r["passed"])
    fail_count = len(results) - pass_count
    total = len(results)
    pass_rate = (pass_count / total * 100) if total else 0

    log_row = {
        "timestamp": __import__("datetime").datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "version": version,
        "tier": tier,
        "flow": flow,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "total": total,
        "pass_rate": round(pass_rate, 2),
        "by_category": by_category,
        "by_tag": by_tag,
    }
    log_path = Path(__file__).parent / "golden_results.jsonl"
    with open(log_path, "a") as f:
        f.write(json.dumps(log_row) + "\n")

    print()
    print(f"Summary: {pass_count} passed, {fail_count} failed, {total} total ({pass_rate:.1f}%)")
    print(f"By category: {by_category}")
    print(f"By tag: {by_tag}")
    print(f"Logged to {log_path}")
    sys.exit(1 if fail_count > 0 else 0)


if __name__ == "__main__":
    main()
