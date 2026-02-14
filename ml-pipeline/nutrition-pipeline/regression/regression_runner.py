"""
Shared regression logic for the nutrition pipeline.
Exports parse_meal_text_to_ingredients and evaluate_expectations for use by
run_regression.py (CLI) and parse_api.py (HTTP endpoints).

Callers must ensure USE_PARSING_CACHE=false and REGRESSION_MODE=true before
importing this module, or the pipeline may behave non-deterministically.
"""

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
            if corr.get("foodGroupServings") and isinstance(corr["foodGroupServings"], dict):
                ing["foodGroupServings"] = corr["foodGroupServings"]
            break


def parse_meal_text_to_ingredients(text: str) -> list[dict]:
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

    # Apply deterministic rules (caffeine, foodGroupServings for meat, etc.)
    corrections = apply_deterministic_rules(ingredients)
    _apply_corrections(ingredients, corrections)

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


def compare_golden_actual_to_expected(
    actual_ingredients: list[dict], expected_ingredients: list[dict]
) -> tuple[bool, list[str]]:
    """
    Compare parsed actual output to golden expected. Returns (passed, failures).
    (1) len(actual) == len(expected); (2) set of canonical names in actual equals set in expected.
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
