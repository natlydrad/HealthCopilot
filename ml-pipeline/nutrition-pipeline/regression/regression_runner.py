"""
Shared regression logic for the nutrition pipeline.
Exports parse_meal_text_to_ingredients and evaluate_expectations for use by
run_regression.py (CLI) and parse_api.py (HTTP endpoints).

Callers must ensure USE_PARSING_CACHE=false and REGRESSION_MODE=true before
importing this module, or the pipeline may behave non-deterministically.
"""

import os

from lookup_usda import (
    resolve_usda_for_ingredient,
    zero_calorie_nutrition_array,
    get_grams_for_scaling,
    get_piece_grams,
    use_piece_grams_for_portion,
)
from parser_gpt import parse_ingredients, gpt_estimate_nutrition
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


def _merge_micro_into_nutrition(
    nutrition: list,
    caffeine_mg=None,
    fiber_g=None,
    added_sugar_g=None,
    sodium_mg=None,
) -> list:
    """Add/update caffeine, fiber, added sugar, sodium in nutrition array."""
    overrides = {
        ("Caffeine", "MG"): caffeine_mg,
        ("Fiber, total dietary", "G"): fiber_g,
        ("Sugars, added", "G"): added_sugar_g,
        ("Sodium, Na", "MG"): sodium_mg,
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


def _correction_matches_ingredient(ing: dict, name_key: str) -> bool:
    """True if correction name_key matches this ingredient (exact or substring)."""
    ing_name = (ing.get("name") or "").strip().lower()
    if not ing_name or not name_key:
        return False
    if ing_name == name_key:
        return True
    if name_key in ing_name or ing_name in name_key:
        return True
    # Word overlap: all significant words in name_key appear in ing_name
    words = [w for w in name_key.split() if len(w) > 1]
    return len(words) > 0 and all(w in ing_name for w in words)


def _apply_corrections(ingredients: list[dict], corrections: list[dict]) -> None:
    """Apply corrections (from apply_deterministic_rules or common_sense_check) to ingredients in place."""
    for corr in corrections:
        name_key = (corr.get("name") or "").strip().lower()
        if not name_key:
            continue
        for ing in ingredients:
            if not _correction_matches_ingredient(ing, name_key):
                continue
            # Portion fix: quantity/unit/serving_size_g -> re-resolve USDA and scale
            if "quantity" in corr or "unit" in corr or "serving_size_g" in corr:
                new_qty = corr.get("quantity", ing.get("quantity", 1))
                new_unit = corr.get("unit", ing.get("unit", "serving"))
                ing["quantity"] = float(new_qty) if new_qty is not None else ing.get("quantity", 1)
                ing["unit"] = str(new_unit).strip() if new_unit else (ing.get("unit") or "serving")
                usda, scaled_nutrition, source_ing, usda_matched_name = resolve_usda_for_ingredient(
                    ing.get("name", ""), ing["quantity"], ing["unit"]
                )
                if scaled_nutrition:
                    ing["nutrition"] = scaled_nutrition
                    ing["source"] = source_ing or ing.get("source", "gpt")
                    if usda_matched_name:
                        ing["usda_matched_name"] = usda_matched_name
                    serving_size = usda.get("serving_size_g", 100.0) if usda else 100.0
                    if corr.get("serving_size_g") is not None:
                        serving_size = float(corr["serving_size_g"])
                    ing["portionGrams"] = round(
                        get_grams_for_scaling(
                            ing.get("name", ""), ing["quantity"], ing["unit"], serving_size
                        ),
                        1,
                    )
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
            if corr.get("added_sugar_g") is not None:
                ing["nutrition"] = _merge_micro_into_nutrition(
                    ing.get("nutrition") or [], added_sugar_g=corr["added_sugar_g"]
                )
            if corr.get("sodium_mg") is not None:
                ing["nutrition"] = _merge_micro_into_nutrition(
                    ing.get("nutrition") or [], sodium_mg=corr["sodium_mg"]
                )
            if corr.get("foodGroupServings") and isinstance(corr["foodGroupServings"], dict):
                ing["foodGroupServings"] = corr["foodGroupServings"]
            break


def parse_meal_text_to_ingredients(text: str, tier: str | None = None) -> list[dict]:
    """
    Run the core parse pipeline: parse -> merge -> USDA lookup (or GPT fallback) -> optional rules + common_sense.

    tier: "mvp" = parser + USDA/GPT only (no deterministic rules, no common_sense).
          "full" = add deterministic rules and GPT common_sense_check (matches production text->ingredients).
    Default tier from env PARSE_FLOW_TIER or "full".
    Returns list of dicts with name, quantity, unit, source, nutrition.
    """
    if tier is None:
        tier = (os.getenv("PARSE_FLOW_TIER") or "full").strip().lower()
    if tier not in ("mvp", "full"):
        tier = "full"

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

        usda, scaled_nutrition, source_ing, usda_matched_name = resolve_usda_for_ingredient(
            ing.get("name", ""), quantity, unit
        )

        if not scaled_nutrition:
            gpt_nutrition = gpt_estimate_nutrition(ing.get("name", ""), quantity, unit)
            if gpt_nutrition:
                scaled_nutrition = gpt_nutrition
                source_ing = "gpt"

        # portionGrams for production parity (servings / display)
        serving_size = 100.0
        if usda:
            serving_size = usda.get("serving_size_g", 100.0)
            piece_g = get_piece_grams(ing.get("name", ""))
            if use_piece_grams_for_portion(unit.lower(), name, quantity, piece_g):
                serving_size = piece_g
        portion_grams = round(
            get_grams_for_scaling(ing.get("name", ""), quantity, unit, serving_size), 1
        )

        fg = ing.get("foodGroupServings")
        if not isinstance(fg, dict):
            fg = None

        ing_dict = {
            "name": ing.get("name", ""),
            "quantity": quantity,
            "unit": unit,
            "source": source_ing,
            "nutrition": scaled_nutrition,
            "portionGrams": portion_grams,
            "foodGroupServings": fg,
        }
        if usda_matched_name:
            ing_dict["usda_matched_name"] = usda_matched_name
        ingredients.append(ing_dict)

    if tier == "full":
        # Apply deterministic rules (caffeine, foodGroupServings for meat, etc.)
        corrections = apply_deterministic_rules(ingredients)
        _apply_corrections(ingredients, corrections)

        # GPT common_sense_check (same as production)
        from common_sense import common_sense_check

        minimal = []
        for ing in ingredients:
            cal = None
            for n in ing.get("nutrition") or []:
                if isinstance(n, dict) and "energy" in (n.get("nutrientName") or "").lower() and "kj" not in (n.get("nutrientName") or "").lower():
                    cal = float(n.get("value", 0) or 0)
                    break
            minimal.append({
                "name": ing.get("name", ""),
                "quantity": ing.get("quantity", 1),
                "unit": ing.get("unit", "serving"),
                "nutrition": ing.get("nutrition"),
                "calories": cal,
                "foodGroupServings": ing.get("foodGroupServings"),
            })
        common_sense_corrections = common_sense_check(text, minimal)
        _apply_corrections(ingredients, common_sense_corrections)

    # Normalize to parsingMetadata shape expected by frontend / production checks
    for ing in ingredients:
        ing["parsingMetadata"] = {
            "portionGrams": ing.get("portionGrams"),
            "foodGroupServings": ing.get("foodGroupServings"),
        }

    return ingredients


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


def _get_macros(ing: dict) -> dict:
    """Return {calories, protein, carbs, fat} from ingredient nutrition array."""
    out = {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
    for n in ing.get("nutrition") or []:
        if not isinstance(n, dict):
            continue
        nn = (n.get("nutrientName") or "").lower()
        val = float(n.get("value", 0) or 0)
        if "energy" in nn and "kj" not in nn:
            out["calories"] = val
        elif nn == "protein":
            out["protein"] = val
        elif "carbohydrate" in nn:
            out["carbs"] = val
        elif "lipid" in nn or nn == "fat":
            out["fat"] = val
    return out


def _aggregate_servings(ingredients: list[dict]) -> dict:
    """Sum MyPlate-style foodGroupServings across ingredients. Returns {grains, vegetables, fruits, protein, dairy}."""
    agg = {"grains": 0.0, "vegetables": 0.0, "fruits": 0.0, "protein": 0.0, "dairy": 0.0}
    for ing in ingredients:
        fg = ing.get("foodGroupServings") or (ing.get("parsingMetadata") or {}).get("foodGroupServings")
        if not isinstance(fg, dict):
            continue
        for k in agg:
            v = fg.get(k)
            if v is not None:
                try:
                    agg[k] += float(v)
                except (TypeError, ValueError):
                    pass
    return agg


MEAT_TERMS = ("pork", "beef", "chicken", "turkey", "fish", "salmon", "tuna", "lamb", "steak", "ground", "bacon", "sausage", "ham", "meat")

# Stopwords to strip when comparing golden actual vs expected (same food, different display name)
_CANONICAL_STOPWORDS = ("organic", "quick", "cook", "canned", "mature", "red")


def _canonical_ingredient_name(name: str) -> str:
    """
    Normalize ingredient name for golden comparison: lowercase, hyphens to spaces,
    strip stopwords, collapse spaces. E.g. "STEEL-CUT ORGANIC QUICK COOK OATS" and
    "Steel cut oats" map to the same canonical form.
    """
    if not name or not isinstance(name, str):
        return ""
    s = name.lower().replace("-", " ").strip()
    words = s.split()
    kept = [w for w in words if w not in _CANONICAL_STOPWORDS]
    return " ".join(kept).strip() if kept else s.strip()


def evaluate_invariants(ingredients: list[dict]) -> tuple[bool, list[str]]:
    """
    Non-negotiable consistency rules. Returns (passed, list of failure messages).
    - Calories ≈ 4*P + 4*C + 9*F per ingredient (tolerance 5% of cal or 10 kcal).
    - Non-negative quantity, portionGrams, and macro values.
    - portionGrams in 0–2000 per ingredient when present.
    """
    failures = []
    for ing in ingredients:
        name = ing.get("name") or "?"
        macros = _get_macros(ing)
        cal, p, c, f = macros["calories"], macros["protein"], macros["carbs"], macros["fat"]
        if cal is None or (p == 0 and c == 0 and f == 0):
            continue
        computed = 4 * p + 4 * c + 9 * f
        if computed <= 0:
            continue
        tol_abs = max(10.0, 0.05 * cal)
        if abs(cal - computed) > tol_abs:
            failures.append(
                f"'{name}': calories {cal:.0f} inconsistent with 4P+4C+9F = {computed:.0f} (tolerance {tol_abs:.0f})"
            )
        if (ing.get("quantity") or 0) < 0:
            failures.append(f"'{name}': negative quantity")
        pg = ing.get("portionGrams") or ing.get("parsingMetadata") or {}
        if isinstance(pg, dict):
            pg = pg.get("portionGrams")
        if pg is not None:
            try:
                pg_f = float(pg)
                if pg_f < 0 or pg_f > 2000:
                    failures.append(f"'{name}': portionGrams {pg_f} outside 0–2000")
            except (TypeError, ValueError):
                pass
        if p < 0 or c < 0 or f < 0:
            failures.append(f"'{name}': negative macro (p={p:.0f} c={c:.0f} f={f:.0f})")
    return len(failures) == 0, failures


def compare_golden_actual_to_expected(
    actual_ingredients: list[dict],
    expected_ingredients: list[dict],
    expected_options: dict | None = None,
) -> tuple[bool, list[str]]:
    """
    Compare parsed actual output to golden expected. Returns (passed, failures).

    (1) len(actual) == len(expected); (2) set of canonical names matches.
    (3) Optional (from expected_options): quantity/unit per ingredient, acceptableRanges (calories),
        sourceExpectations (e.g. {"eggs": "usda"} by name substring).
    """
    failures = []
    if len(actual_ingredients) != len(expected_ingredients):
        failures.append(
            f"Ingredient count mismatch: actual={len(actual_ingredients)}, expected={len(expected_ingredients)}"
        )
    actual_names = {_canonical_ingredient_name(ing.get("name") or "") for ing in actual_ingredients}
    expected_names = {_canonical_ingredient_name(ing.get("name") or "") for ing in expected_ingredients}
    if actual_names != expected_names:
        only_actual = actual_names - expected_names
        only_expected = expected_names - actual_names
        if only_actual:
            failures.append(f"Only in actual: {only_actual}")
        if only_expected:
            failures.append(f"Only in expected: {only_expected}")

    opts = expected_options or {}
    acceptable_ranges = opts.get("acceptableRanges")
    if isinstance(acceptable_ranges, dict):
        calories_tolerance_pct = acceptable_ranges.get("caloriesTolerancePercent")
    else:
        calories_tolerance_pct = None
    source_expectations = opts.get("sourceExpectations") or {}

    # Build expected by canonical name for matching
    expected_by_canonical = {}
    for e in expected_ingredients:
        can = _canonical_ingredient_name(e.get("name") or "")
        if can:
            expected_by_canonical[can] = e

    for act in actual_ingredients:
        can = _canonical_ingredient_name(act.get("name") or "")
        exp = expected_by_canonical.get(can) if can else None
        if not exp:
            continue

        # Quantity/unit: if expected has quantity/unit, require actual within tolerance
        if exp.get("quantity") is not None:
            act_q = float(act.get("quantity", 1) or 1)
            exp_q = float(exp.get("quantity", 0))
            if abs(act_q - exp_q) > 0.01:
                failures.append(
                    f"'{act.get('name')}': expected quantity {exp_q}, got {act_q}"
                )
        if exp.get("unit"):
            act_u = (act.get("unit") or "").strip().lower()
            exp_u = (exp.get("unit") or "").strip().lower()
            if act_u != exp_u:
                failures.append(
                    f"'{act.get('name')}': expected unit '{exp.get('unit')}', got '{act.get('unit')}'"
                )

        # Calories: optional tolerance from acceptableRanges or per-ingredient caloriesMin/Max
        act_cal = _get_macros(act)["calories"]
        exp_cal = None
        for n in exp.get("nutrition") or []:
            if isinstance(n, dict) and "energy" in (n.get("nutrientName") or "").lower() and "kj" not in (n.get("nutrientName") or "").lower():
                exp_cal = float(n.get("value", 0) or 0)
                break
        if exp_cal is not None and act_cal is not None:
            if isinstance(calories_tolerance_pct, (int, float)) and calories_tolerance_pct >= 0:
                tol = (calories_tolerance_pct / 100.0) * exp_cal
                if abs(act_cal - exp_cal) > max(tol, 1.0):
                    failures.append(
                        f"'{act.get('name')}': expected calories ~{exp_cal:.0f} (±{calories_tolerance_pct}%), got {act_cal:.0f}"
                    )
            elif exp.get("caloriesMin") is not None or exp.get("caloriesMax") is not None:
                lo = float(exp["caloriesMin"]) if exp.get("caloriesMin") is not None else 0
                hi = float(exp["caloriesMax"]) if exp.get("caloriesMax") is not None else 9999
                if not (lo <= act_cal <= hi):
                    failures.append(
                        f"'{act.get('name')}': expected calories in [{lo}, {hi}], got {act_cal:.0f}"
                    )

        # Source: if sourceExpectations has a key matching this ingredient (substring), assert source
        act_name_lower = (act.get("name") or "").lower()
        for substr, want_source in source_expectations.items():
            if (substr or "").lower() in act_name_lower:
                act_src = (act.get("source") or "").strip().lower()
                want = (want_source or "").strip().lower()
                if act_src != want:
                    failures.append(
                        f"'{act.get('name')}': expected source={want}, got {act_src}"
                    )
                break

    return len(failures) == 0, failures


def evaluate_production_checks(ingredients: list[dict]) -> tuple[bool, list[str]]:
    """
    Production-parity checks: servings sanity and nutrient sanity.
    Returns (passed, list of failure messages).
    """
    failures = []

    # Duplicate ingredient names
    names = [(ing.get("name") or "").strip().lower() for ing in ingredients]
    if len(names) != len(set(names)):
        dupes = [n for n in names if names.count(n) > 1]
        failures.append(f"Duplicate ingredients: {set(dupes)}")

    # Servings: foodGroupServings non-negative, no NaN; aggregate non-negative
    for i, ing in enumerate(ingredients):
        fg = ing.get("foodGroupServings") or (ing.get("parsingMetadata") or {}).get("foodGroupServings")
        if not isinstance(fg, dict):
            continue
        for k, v in fg.items():
            if v is None:
                continue
            try:
                f = float(v)
                if f != f:  # NaN
                    failures.append(f"'{ing.get('name')}': foodGroupServings.{k} is NaN")
                elif f < 0:
                    failures.append(f"'{ing.get('name')}': foodGroupServings.{k} is negative ({f})")
            except (TypeError, ValueError):
                failures.append(f"'{ing.get('name')}': foodGroupServings.{k} is not a number")

    agg = _aggregate_servings(ingredients)
    for k, v in agg.items():
        if v != v or v < 0:
            failures.append(f"Aggregate servings {k} invalid: {v}")

    # Meat/poultry/fish must contribute to protein (foodGroupServings.protein > 0)
    for ing in ingredients:
        name_lower = (ing.get("name") or "").strip().lower()
        if not any(term in name_lower for term in MEAT_TERMS):
            continue
        fg = ing.get("foodGroupServings") or (ing.get("parsingMetadata") or {}).get("foodGroupServings")
        if not isinstance(fg, dict) or float(fg.get("protein") or 0) <= 0:
            failures.append(
                f"'{ing.get('name')}' should contribute to protein (meat/poultry/fish must have foodGroupServings.protein > 0)"
            )

    # Nutrient sanity: per-ingredient calories 0–5000, macros non-negative
    for ing in ingredients:
        macros = _get_macros(ing)
        if not (0 <= macros["calories"] <= 5000):
            failures.append(
                f"'{ing.get('name')}': calories {macros['calories']:.0f} outside 0–5000"
            )
        if macros["protein"] < 0 or macros["carbs"] < 0 or macros["fat"] < 0:
            failures.append(
                f"'{ing.get('name')}': negative macro (p={macros['protein']:.0f} c={macros['carbs']:.0f} f={macros['fat']:.0f})"
            )

    # Meal total calories 0–5000 (per meal)
    total_cal = sum(_get_macros(ing)["calories"] for ing in ingredients)
    if not (0 <= total_cal <= 5000):
        failures.append(f"Meal total calories {total_cal:.0f} outside 0–5000 (per meal)")

    return len(failures) == 0, failures


def _run_signature(ingredients: list[dict]) -> frozenset:
    """Signature for exact-structure comparison: set of (canonical_name, quantity, unit)."""
    out = set()
    for ing in ingredients:
        can = _canonical_ingredient_name(ing.get("name") or "")
        q = round(float(ing.get("quantity", 1) or 1), 2)
        u = (ing.get("unit") or "serving").strip().lower()
        out.add((can, q, u))
    return frozenset(out)


def run_stability_check(
    entries: list[dict],
    n: int = 5,
    tier: str | None = None,
) -> dict:
    """
    Run each entry n times and compare outputs for stability (temp=0 should be deterministic).
    entries: list of { "id", "input": { "text" } }.
    Returns report with per_entry (exact_match, field_stability, calorie_stds) and aggregate stats.
    """
    import statistics

    if tier is None:
        tier = (os.getenv("PARSE_FLOW_TIER") or "full").strip().lower()
    if tier not in ("mvp", "full"):
        tier = "full"

    per_entry = []
    exact_match_count = 0
    all_calorie_stds = []
    all_field_stabilities = []

    for entry in entries:
        entry_id = entry.get("id") or "?"
        text = (entry.get("input") or {}).get("text") or ""
        runs = []
        for _ in range(n):
            try:
                out = parse_meal_text_to_ingredients(text, tier=tier)
                runs.append(out)
            except Exception:
                runs.append([])

        # Exact-structure: same count and same set of (name, qty, unit)
        signatures = [_run_signature(r) for r in runs]
        exact = all(s == signatures[0] for s in signatures) and len(signatures[0]) == len(runs[0]) if runs and runs[0] else False
        if exact:
            exact_match_count += 1

        # Per-ingredient across runs: match by canonical name
        name_to_calories = {}
        name_to_source = {}
        for r in runs:
            for ing in r:
                can = _canonical_ingredient_name(ing.get("name") or "")
                if not can:
                    continue
                cal = _get_macros(ing)["calories"]
                src = (ing.get("source") or "").strip().lower()
                name_to_calories.setdefault(can, []).append(cal)
                name_to_source.setdefault(can, []).append(src)

        calorie_stds = []
        for can, cals in name_to_calories.items():
            if len(cals) > 1:
                try:
                    calorie_stds.append(statistics.stdev(cals))
                except statistics.StatisticsError:
                    pass
            else:
                calorie_stds.append(0.0)
        all_calorie_stds.extend(calorie_stds)
        max_std = max(calorie_stds) if calorie_stds else 0.0

        # Field stability: fraction of runs with same value (per field, per name)
        field_stability_pcts = []
        for can, sources in name_to_source.items():
            if not sources:
                continue
            majority = max(set(sources), key=sources.count)
            same = sum(1 for s in sources if s == majority)
            field_stability_pcts.append(same / len(sources) * 100)
        for can, cals in name_to_calories.items():
            if len(cals) < 2:
                field_stability_pcts.append(100.0)
                continue
            # Same calories within 0.01
            rounded = [round(c, 2) for c in cals]
            majority = max(set(rounded), key=rounded.count)
            same = sum(1 for r in rounded if r == majority)
            field_stability_pcts.append(same / len(rounded) * 100)
        entry_field_stability = statistics.mean(field_stability_pcts) if field_stability_pcts else 100.0
        all_field_stabilities.append(entry_field_stability)

        per_entry.append({
            "id": entry_id,
            "exact_match": exact,
            "field_stability_pct": round(entry_field_stability, 1),
            "max_calorie_std": round(max_std, 2),
            "n_runs": n,
        })

    total_entries = len(entries)
    aggregate = {
        "exact_match_rate_pct": round(exact_match_count / total_entries * 100, 1) if total_entries else 0,
        "mean_field_stability_pct": round(statistics.mean(all_field_stabilities), 1) if all_field_stabilities else 100,
        "calorie_std_95th": round(
            sorted(all_calorie_stds)[min(int(len(all_calorie_stds) * 0.95), len(all_calorie_stds) - 1)]
            if all_calorie_stds else 0,
            2,
        ),
        "n_entries": total_entries,
        "n_runs_per_entry": n,
        "tier": tier,
    }
    return {"per_entry": per_entry, "aggregate": aggregate}
