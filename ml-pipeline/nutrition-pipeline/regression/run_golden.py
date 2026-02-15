#!/usr/bin/env python3
"""
Run golden set: parse each entry, compare to expected, run production checks and invariants.
Appends one JSONL row to golden_results.jsonl with timestamp, version, tier, pass_count, fail_count, total, pass_rate, optional by_category.

Usage:
  cd ml-pipeline/nutrition-pipeline
  USE_PARSING_CACHE=false REGRESSION_MODE=true python regression/run_golden.py
  PARSE_FLOW_TIER=mvp PARSE_PROMPT_VERSION=v0-mvp python regression/run_golden.py
"""

import json
import os
import sys
from datetime import timezone
from pathlib import Path

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


def main():
    golden_path = Path(__file__).parent / "golden_set.json"
    if not golden_path.exists():
        print(f"ERROR: {golden_path} not found")
        sys.exit(1)

    with open(golden_path) as f:
        golden = json.load(f)

    entries = golden.get("entries") or []
    tier = (os.getenv("PARSE_FLOW_TIER") or "full").strip().lower()
    if tier not in ("mvp", "full"):
        tier = "full"
    version = (os.getenv("PARSE_PROMPT_VERSION") or "unknown").strip()

    print(f"Running golden set: {len(entries)} entries (tier={tier}, version={version})")
    print()

    results = []
    by_category = {}
    for entry in entries:
        entry_id = entry.get("id") or ""
        text = (entry.get("input") or {}).get("text") or ""
        expected_dict = entry.get("expected") or {}
        expected_ingredients = expected_dict.get("ingredients") or []
        expected_options = {k: v for k, v in expected_dict.items() if k != "ingredients"}
        category = (entry.get("category") or "normal").strip().lower()
        if category not in ("easy", "normal", "evil"):
            category = "normal"

        try:
            actual = parse_meal_text_to_ingredients(text, tier=tier)
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

            compare_ok, compare_failures = compare_golden_actual_to_expected(
                actual, expected_ingredients, expected_options
            )
            prod_ok, prod_failures = evaluate_production_checks(actual)
            inv_ok, inv_failures = evaluate_invariants(actual)
            passed = compare_ok and prod_ok and inv_ok
            failures = list(compare_failures) + list(prod_failures) + list(inv_failures)
        except Exception as e:
            passed = False
            failures = [str(e)]

        results.append({"id": entry_id, "passed": passed, "category": category})
        if category not in by_category:
            by_category[category] = {"pass": 0, "fail": 0}
        if passed:
            by_category[category]["pass"] += 1
        else:
            by_category[category]["fail"] += 1
            print(f"FAIL {entry_id} ({category}): {text[:60]}...")
            for f in failures[:3]:
                print(f"     - {f}")

    pass_count = sum(1 for r in results if r["passed"])
    fail_count = len(results) - pass_count
    total = len(results)
    pass_rate = (pass_count / total * 100) if total else 0

    log_row = {
        "timestamp": __import__("datetime").datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "version": version,
        "tier": tier,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "total": total,
        "pass_rate": round(pass_rate, 2),
        "by_category": by_category,
    }
    log_path = Path(__file__).parent / "golden_results.jsonl"
    with open(log_path, "a") as f:
        f.write(json.dumps(log_row) + "\n")

    print()
    print(f"Summary: {pass_count} passed, {fail_count} failed, {total} total ({pass_rate:.1f}%)")
    print(f"By category: {by_category}")
    print(f"Logged to {log_path}")
    sys.exit(1 if fail_count > 0 else 0)


if __name__ == "__main__":
    main()
