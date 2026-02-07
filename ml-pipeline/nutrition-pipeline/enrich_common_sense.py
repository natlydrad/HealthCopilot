"""
Deterministic common-sense enrichment. Applies rules from common_sense_rules.yaml
BEFORE the GPT-based common_sense_check. Returns corrections in the same format.
"""

import yaml
from pathlib import Path

RULES_PATH = Path(__file__).parent / "common_sense_rules.yaml"

# Cache rules
_rules_cache = None


def _load_rules() -> dict:
    global _rules_cache
    if _rules_cache is not None:
        return _rules_cache
    if not RULES_PATH.exists():
        _rules_cache = {}
        return _rules_cache
    with open(RULES_PATH) as f:
        _rules_cache = yaml.safe_load(f) or {}
    return _rules_cache


def _name_contains(name: str, pattern: str) -> bool:
    return pattern.lower() in (name or "").lower()


def _find_best_pattern_match(name: str, patterns: list) -> str | None:
    """Return the longest matching pattern, or None."""
    name_lower = (name or "").lower()
    best = None
    best_len = 0
    for p in patterns:
        if p and p.lower() in name_lower and len(p) > best_len:
            best = p
            best_len = len(p)
    return best


def _find_best_dict_match(name: str, d: dict) -> tuple:
    """Return (matched_key, value) for longest matching key, or (None, None)."""
    if not d:
        return None, None
    name_lower = (name or "").lower()
    best_key = None
    best_len = 0
    best_val = None
    for k, v in d.items():
        if k and k.lower() in name_lower and len(k) > best_len:
            best_key = k
            best_len = len(k)
            best_val = v
    return best_key, best_val


def _has_nutrient(nutrition: list, nutrient_name: str) -> bool:
    """True if nutrition already has this nutrient."""
    if not nutrition or not isinstance(nutrition, list):
        return False
    target = (nutrient_name or "").strip().lower()
    for n in nutrition:
        if isinstance(n, dict):
            nn = (n.get("nutrientName") or "").strip().lower()
            if nn == target or target in nn:
                return True
    return False


def _calories_from_nutrition(nutrition: list) -> float | None:
    if not nutrition:
        return None
    for n in nutrition:
        if not isinstance(n, dict):
            continue
        name = (n.get("nutrientName") or "").lower()
        if "energy" in name or name == "calories":
            try:
                return float(n.get("value", 0))
            except (TypeError, ValueError):
                return None
    return None


def _servings_from_quantity_unit(quantity: float, unit: str) -> float:
    """Estimate number of 'servings' (cups for drinks) for scaling caffeine/fiber."""
    qty = float(quantity or 1)
    u = (unit or "serving").lower().strip()
    if u in ("cup", "cups", "serving", "servings"):
        return qty
    if u in ("oz", "fl oz", "fluid ounce"):
        return qty / 8.0  # 8 oz = 1 cup
    if u in ("shot", "shots"):
        return qty * 0.25  # 1 shot ~ 0.25 cup
    if u in ("g", "gram", "grams"):
        return qty / 240.0  # ~240g per cup for beverages
    if u in ("ml", "milliliter"):
        return qty / 240.0
    return qty  # fallback: assume quantity = servings


def apply_deterministic_rules(ingredients: list[dict]) -> list[dict]:
    """
    Apply deterministic common-sense rules. Returns list of corrections
    in same format as common_sense_check: [{ "name": "...", "zero_calories": true }, ...]
    """
    rules = _load_rules()
    if not rules:
        return []

    corrections = []

    for ing in ingredients:
        name = (ing.get("name") or "").strip()
        if not name:
            continue
        name_lower = name.lower()
        quantity = float(ing.get("quantity") or 1)
        unit = (ing.get("unit") or "serving").strip()
        nutrition = ing.get("nutrition") or []
        if isinstance(nutrition, str):
            try:
                import json
                nutrition = json.loads(nutrition) if nutrition.strip() else []
            except Exception:
                nutrition = []
        calories = _calories_from_nutrition(nutrition)

        corr = {"name": name}

        # Zero-calorie
        zero_pats = rules.get("zero_calorie", {}).get("patterns", [])
        if zero_pats and _find_best_pattern_match(name, zero_pats):
            if calories is not None and calories > 5:
                corr["zero_calories"] = True

        # Caffeine (only if missing)
        if not _has_nutrient(nutrition, "caffeine"):
            caffeine_rules = rules.get("caffeine_mg_per_serving", {})
            # Exclude zero-caffeine patterns from triggering an "add"
            zero_caff = {"decaf", "decaffeinated", "herbal", "peppermint", "chamomile", "rooibos"}
            if not any(z in name_lower for z in zero_caff):
                _, mg_per_serv = _find_best_dict_match(name, caffeine_rules)
                if mg_per_serv is not None:
                    servings = _servings_from_quantity_unit(quantity, unit)
                    total_mg = round(mg_per_serv * servings, 1)
                    if total_mg > 0:
                        corr["caffeine_mg"] = total_mg

        # Portion fixes
        portion_rules = rules.get("portion_fixes", {})
        _, portion_fix = _find_best_dict_match(name, portion_rules)
        if portion_fix and isinstance(portion_fix, dict):
            # Only suggest if current unit is suspicious (e.g. matcha in oz)
            u = unit.lower()
            if u in ("oz", "fl oz") and "matcha" in name_lower:
                corr["quantity"] = portion_fix.get("quantity", quantity)
                corr["unit"] = portion_fix.get("unit", unit)
                if portion_fix.get("serving_size_g"):
                    corr["serving_size_g"] = portion_fix["serving_size_g"]

        # Fiber (only if missing)
        if not _has_nutrient(nutrition, "fiber"):
            _, fiber_per_serv = _find_best_dict_match(name, rules.get("fiber_g_per_serving", {}))
            if fiber_per_serv is not None:
                servings = _servings_from_quantity_unit(quantity, unit)
                total = round(fiber_per_serv * servings, 1)
                if total > 0:
                    corr["fiber_g"] = total

        # Added sugar (only if missing) - use sparingly
        if not _has_nutrient(nutrition, "sugars, added") and not _has_nutrient(nutrition, "added"):
            _, sugar_per_serv = _find_best_dict_match(name, rules.get("added_sugar_g_per_serving", {}))
            if sugar_per_serv is not None:
                servings = _servings_from_quantity_unit(quantity, unit)
                total = round(sugar_per_serv * servings, 1)
                if total > 0:
                    corr["added_sugar_g"] = total

        # Only add if we actually have corrections (more than just "name")
        if len(corr) > 1:
            corrections.append(corr)

    return corrections
