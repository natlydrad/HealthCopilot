#!/usr/bin/env python3
"""
Regression runner for the nutrition pipeline.
Parses meal texts through the core pipeline (parser -> USDA -> common sense)
and evaluates expectations defined in regression_meals.json.

Run with:
  cd ml-pipeline/nutrition-pipeline
  USE_PARSING_CACHE=false REGRESSION_MODE=true python regression/run_regression.py
"""

import json
import os
import sys
from pathlib import Path

# Set determinism env BEFORE importing pipeline modules
os.environ.setdefault("USE_PARSING_CACHE", "false")
os.environ.setdefault("REGRESSION_MODE", "true")

# Add parent so we can import from nutrition-pipeline
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from regression.regression_runner import (
    parse_meal_text_to_ingredients,
    evaluate_expectations,
    evaluate_production_checks,
    evaluate_invariants,
)


def main():
    suite_path = Path(__file__).parent / "regression_meals.json"
    if not suite_path.exists():
        print(f"ERROR: {suite_path} not found")
        sys.exit(1)

    with open(suite_path) as f:
        suite = json.load(f)

    meals = suite.get("meals", [])
    tier = os.getenv("PARSE_FLOW_TIER", "full").strip().lower() or "full"
    if tier not in ("mvp", "full"):
        tier = "full"
    print(f"Running {len(meals)} regression meals (tier={tier})...")
    print()

    passed = 0
    failed = 0
    for meal in meals:
        mid = meal.get("id", "?")
        text = meal.get("text", "")
        expectations = meal.get("expectations", {})

        try:
            actual = parse_meal_text_to_ingredients(text, tier=tier)
        except Exception as e:
            print(f"FAIL {mid}: Exception during parse: {e}")
            failed += 1
            continue

        ok, failures = evaluate_expectations(actual, expectations)
        prod_ok, prod_failures = evaluate_production_checks(actual)
        inv_ok, inv_failures = evaluate_invariants(actual)
        if not prod_ok:
            failures = list(failures) + prod_failures
            ok = False
        if not inv_ok:
            failures = list(failures) + inv_failures
            ok = False
        if ok:
            print(f"PASS {mid}: {text[:50]}...")
            passed += 1
        else:
            print(f"FAIL {mid}: {text[:50]}...")
            for f in failures:
                print(f"     - {f}")
            failed += 1

    print()
    print(f"Summary: {passed} passed, {failed} failed, {len(meals)} total")
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
