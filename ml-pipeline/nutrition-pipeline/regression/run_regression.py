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

from parser_gpt import parse_ingredients, gpt_estimate_nutrition
from lookup_usda import (
    usda_lookup,
    usda_lookup_valid_for_portion,
    scale_nutrition,
    get_piece_grams,
    validate_scaled_calories,
    validate_scaled_protein,
    zero_calorie_nutrition_array,
)
from enrich_common_sense import apply_deterministic_rules


def _merge_ingredients_by_name(parsed: list) -> list:
    """Merge ingredients with same normalized name; sum quantities when same unit."""
    from collections import defaultdict

    groups = defaultdict(list)
    for ing in parsed:
        name = (ing.get("name") or "").strip()
        if not name:
            continue
        key = name.lower()
        groups[key].append(ing)
    merged = []
    for _key, group in groups.items():
        first = dict(group[0]) if isinstance(group[0], dict) else dict(group[0])
        if len(group) == 1:
            merged.append(first)
            continue
        units = [
            (float(ing.get("quantity", 1) or 1), (ing.get("unit") or "serving").strip().lower())
            for ing in group
        ]
        u0 = units[0][1]
        if all(u == u0 for _, u in units):
            first["quantity"] = sum(q for q, _ in units)
            first["unit"] = group[0].get("unit") or "serving"
        merged.append(first)
    return merged


def _normalize_quantity(ing: dict) -> dict:
    if not ing.get("quantity") or ing["quantity"] == 0:
        ing["quantity"] = 1
        ing["unit"] = ing.get("unit") or "serving"
    return ing


def _merge_micro_into_nutrition(nutrition: list, caffeine_mg=None, fiber_g=None) -> list:
    """Add/update caffeine, fiber in nutrition array."""
    overrides = {
        ("Caffeine", "MG"): caffeine_mg,
        ("Fiber, total dietary", "G"): fiber_g,
    }
    by_key = {}
    for n in nutrition or []:
        if isinstance(n, dict):
            key = (n.get("nutrientName"), n.get("unitName"))
            by_key[key] = {**n, "value": n.get("value")}
    for (nn, un), val in overrides.items():
        if val is not None and isinstance(val, (int, float)) and val >= 0:
            by_key[(nn, un)] = {"nutrientName": nn, "unitName": un, "value": round(float(val), 2)}
    return list(by_key.values())


def _apply_corrections(ingredients: list[dict], corrections: list[dict]) -> None:
    """Apply corrections (from apply_deterministic_rules) to ingredients in place."""
    for corr in corrections:
        name_key = (corr.get("name") or "").strip().lower()
        if not name_key:
            continue
        for ing in ingredients:
            if (ing.get("name") or "").strip().lower() != name_key:
                continue
            if corr.get("zero_calories"):
                ing["nutrition"] = zero_calorie_nutrition_array()
                if any(
                    t in name_key
                    for t in ("tea", "coffee", "matcha", "espresso", "cola", "soda")
                ):
                    caf = corr.get("caffeine_mg")
                    if caf is not None:
                        ing["nutrition"] = _merge_micro_into_nutrition(
                            ing.get("nutrition") or [], caffeine_mg=caf
                        )
            if corr.get("caffeine_mg") is not None and not corr.get("zero_calories"):
                ing["nutrition"] = _merge_micro_into_nutrition(
                    ing.get("nutrition") or [], caffeine_mg=corr["caffeine_mg"]
                )
            if corr.get("fiber_g") is not None:
                ing["nutrition"] = _merge_micro_into_nutrition(
                    ing.get("nutrition") or [], fiber_g=corr["fiber_g"]
                )
            break


def _parse_meal_to_ingredients(text: str) -> list[dict]:
    """
    Run the core parse pipeline: parse -> merge -> USDA lookup (or GPT fallback) -> common sense.
    Returns list of dicts with name, quantity, unit, source, nutrition.
    """
    parsed = parse_ingredients(text, user_context="")
    if not parsed:
        return []

    parsed = _merge_ingredients_by_name(parsed)

    # Dedupe by (name, quantity, unit)
    def _ing_key(ing):
        n = (ing.get("name") or "").strip().lower()
        q = float(ing.get("quantity", 1) or 1)
        u = (ing.get("unit") or "serving").strip().lower()
        return (n, q, u)

    seen = set()
    deduped = []
    for ing in parsed:
        k = _ing_key(ing)
        if k in seen:
            continue
        seen.add(k)
        deduped.append(ing)

    ingredients = []
    for ing in deduped:
        ing = _normalize_quantity(dict(ing))
        name = (ing.get("name") or "").lower().strip()
        if len(name) < 2:
            continue
        quantity = float(ing.get("quantity", 1) or 1)
        unit = (ing.get("unit") or "serving").strip()

        scaled_nutrition = []
        source_ing = "gpt"
        usda_matched_name = None

        usda = usda_lookup(ing.get("name", ""))
        if not usda and _is_common_whole_food(name):
            usda = usda_lookup_valid_for_portion(ing.get("name", ""), quantity, unit)

        if usda:
            usda_matched_name = usda.get("name")
            serving_size = usda.get("serving_size_g", 100.0)
            unit_lower = unit.lower()
            piece_g = get_piece_grams(name)
            if unit_lower in ("piece", "pieces", "count") and piece_g is not None:
                serving_size = piece_g
            elif (
                unit_lower in ("serving", "servings")
                and 1 <= quantity <= 30
                and piece_g is not None
            ):
                serving_size = piece_g

            scaled_nutrition = scale_nutrition(
                usda.get("nutrition", []), quantity, unit, serving_size
            )
            cal_val = next(
                (n.get("value", 0) for n in scaled_nutrition if n.get("nutrientName") == "Energy"),
                0,
            )
            is_valid, _ = validate_scaled_calories(name, quantity, unit, cal_val)
            if not is_valid:
                usda = usda_lookup_valid_for_portion(ing.get("name", ""), quantity, unit)
                if usda:
                    usda_matched_name = usda.get("name")
                    serving_size = usda.get("serving_size_g", 100.0)
                    scaled_nutrition = scale_nutrition(
                        usda.get("nutrition", []), quantity, unit, serving_size
                    )
                    source_ing = "usda"
            else:
                ok, _ = validate_scaled_protein(name, scaled_nutrition)
                if not ok:
                    usda = usda_lookup_valid_for_portion(ing.get("name", ""), quantity, unit)
                    if usda:
                        usda_matched_name = usda.get("name")
                        serving_size = usda.get("serving_size_g", 100.0)
                        scaled_nutrition = scale_nutrition(
                            usda.get("nutrition", []), quantity, unit, serving_size
                        )
                        source_ing = "usda"
                else:
                    source_ing = "usda"

        if not scaled_nutrition:
            gpt_nutrition = gpt_estimate_nutrition(ing.get("name", ""), quantity, unit)
            if gpt_nutrition:
                scaled_nutrition = gpt_nutrition
                source_ing = "gpt"

        ing_dict = {
            "name": ing.get("name", ""),
            "quantity": quantity,
            "unit": unit,
            "source": source_ing,
            "nutrition": scaled_nutrition,
        }
        if usda_matched_name:
            ing_dict["usda_matched_name"] = usda_matched_name
        ingredients.append(ing_dict)

    # Apply deterministic rules (caffeine, etc.)
    corrections = apply_deterministic_rules(ingredients)
    _apply_corrections(ingredients, corrections)

    return ingredients


def _is_common_whole_food(name: str) -> bool:
    """True if name looks like a common whole food (kiwi, apple, etc.)."""
    whole = {"kiwi", "strawberry", "strawberries", "apple", "banana", "orange", "pear", "plum"}
    return name.lower().strip() in whole or name.lower().strip().rstrip("s") in whole


def _get_caffeine(ing: dict) -> float | None:
    for n in ing.get("nutrition") or []:
        if isinstance(n, dict) and "caffeine" in (n.get("nutrientName") or "").lower():
            return float(n.get("value", 0))
    return None


def _find_ingredient(ingredients: list[dict], substring: str) -> dict | None:
    """Find first ingredient whose name contains substring (case-insensitive)."""
    sub = substring.lower()
    for ing in ingredients:
        if sub in (ing.get("name") or "").lower():
            return ing
    return None


def evaluate_expectations(actual: list[dict], expected: dict) -> tuple[bool, list[str]]:
    """
    Evaluate expectations against actual ingredients.
    Returns (passed, list of failure messages).
    """
    failures = []

    if expected.get("noOolong"):
        for ing in actual:
            if "oolong" in (ing.get("name") or "").lower():
                failures.append(f"Expected no Oolong, but got: {ing.get('name')}")
                break
            usda_name = ing.get("usda_matched_name") or ""
            if usda_name and "oolong" in usda_name.lower():
                failures.append(
                    f"Expected no Oolong USDA match, but got: {usda_name}"
                )
                break

    if expected.get("hasCaffeine"):
        found = False
        for ing in actual:
            caf = _get_caffeine(ing)
            if caf is not None and caf > 0:
                found = True
                break
        if not found:
            failures.append("Expected at least one ingredient with caffeine > 0")

    if "ingredientCount" in expected:
        want = expected["ingredientCount"]
        if len(actual) != want:
            failures.append(f"Expected {want} ingredients, got {len(actual)}")

    if expected.get("noDuplicates"):
        names = [(ing.get("name") or "").strip().lower() for ing in actual]
        if len(names) != len(set(names)):
            dupes = [n for n in names if names.count(n) > 1]
            failures.append(f"Duplicate ingredients: {set(dupes)}")

    if "quantityMatches" in expected:
        for substr, want in expected["quantityMatches"].items():
            ing = _find_ingredient(actual, substr)
            if not ing:
                failures.append(f"Expected ingredient matching '{substr}', not found")
            else:
                q = float(ing.get("quantity", 1) or 1)
                u = (ing.get("unit") or "serving").strip().lower()
                want_q = want.get("quantity")
                want_u = (want.get("unit") or "").strip().lower()
                if want_q is not None and abs(q - want_q) > 0.01:
                    failures.append(
                        f"'{ing.get('name')}': expected quantity {want_q}, got {q}"
                    )
                if want_u and u != want_u:
                    failures.append(
                        f"'{ing.get('name')}': expected unit '{want_u}', got '{u}'"
                    )

    if "sourceIsUsda" in expected:
        for substr in expected["sourceIsUsda"]:
            ing = _find_ingredient(actual, substr)
            if not ing:
                failures.append(f"Expected ingredient matching '{substr}', not found")
            elif (ing.get("source") or "").lower() != "usda":
                failures.append(
                    f"'{ing.get('name')}' expected source=usda, got {ing.get('source')}"
                )

    if "noGptFor" in expected:
        for substr in expected["noGptFor"]:
            ing = _find_ingredient(actual, substr)
            if ing and (ing.get("source") or "").lower() == "gpt":
                failures.append(
                    f"'{ing.get('name')}' should not be GPT source (common whole food)"
                )

    if "usdaMatchNameExcludes" in expected:
        entries = expected["usdaMatchNameExcludes"]
        if isinstance(entries, dict):
            entries = [entries]
        for entry in entries:
            if isinstance(entry, dict):
                substr = entry.get("substr", "")
                exclude = entry.get("exclude", "")
            else:
                continue
            ing = _find_ingredient(actual, substr)
            if not ing:
                failures.append(f"Expected ingredient matching '{substr}', not found")
            else:
                usda_name = (ing.get("usda_matched_name") or "").lower()
                if usda_name and exclude.lower() in usda_name:
                    failures.append(
                        f"'{ing.get('name')}': USDA match '{ing.get('usda_matched_name')}' contains '{exclude}'"
                    )

    if "caloriesInRange" in expected:
        entries = expected["caloriesInRange"]
        if isinstance(entries, dict):
            entries = [entries]
        for entry in entries:
            if isinstance(entry, dict):
                substr = entry.get("substr", "")
                min_cal = entry.get("min", 0)
                max_cal = entry.get("max", 9999)
            else:
                continue
            ing = _find_ingredient(actual, substr)
            if not ing:
                failures.append(f"Expected ingredient matching '{substr}', not found")
            else:
                cal_val = 0
                for n in (ing.get("nutrition") or []):
                    if isinstance(n, dict):
                        nn = (n.get("nutrientName") or "").lower()
                        if "energy" in nn and "kj" not in nn:
                            cal_val = float(n.get("value", 0) or 0)
                            break
                if not (min_cal <= cal_val <= max_cal):
                    failures.append(
                        f"'{ing.get('name')}': expected {min_cal}-{max_cal} cal, got {cal_val}"
                    )

    return len(failures) == 0, failures


def main():
    suite_path = Path(__file__).parent / "regression_meals.json"
    if not suite_path.exists():
        print(f"ERROR: {suite_path} not found")
        sys.exit(1)

    with open(suite_path) as f:
        suite = json.load(f)

    meals = suite.get("meals", [])
    print(f"Running {len(meals)} regression meals...")
    print()

    passed = 0
    failed = 0
    for meal in meals:
        mid = meal.get("id", "?")
        text = meal.get("text", "")
        expectations = meal.get("expectations", {})

        try:
            actual = _parse_meal_to_ingredients(text)
        except Exception as e:
            print(f"FAIL {mid}: Exception during parse: {e}")
            failed += 1
            continue

        ok, failures = evaluate_expectations(actual, expectations)
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
