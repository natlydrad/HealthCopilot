#!/usr/bin/env python3
"""
One-time backfill: (1) Add Caffeine to all ingredients that have nutrition but no Caffeine entry,
using USDA lookup and merge; (2) Optionally run GPT common-sense check per meal and apply
zero-calorie and portion corrections.

Usage:
  python backfill_caffeine_and_common_sense.py [--dry-run] [--limit N] [--since YYYY-MM-DD]
  python backfill_caffeine_and_common_sense.py --caffeine-only   # skip common-sense
  python backfill_caffeine_and_common_sense.py --common-sense-only   # only common-sense, no caffeine
"""

import os
import requests
import argparse
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

from pb_client import get_token, PB_URL, fetch_ingredients_by_meal_id, fetch_meal_by_id
from lookup_usda import (
    usda_lookup,
    usda_lookup_by_fdc_id,
    scale_nutrition,
    get_piece_grams,
    convert_to_grams,
    zero_calorie_nutrition_array,
    extract_caffeine_mg_per_100g,
    normalize_usda_food_nutrients,
)
from common_sense import common_sense_check


def _has_valid_nutrition(ing) -> bool:
    """True if ingredient has non-empty nutrition with at least Energy."""
    raw = ing.get("nutrition") or ing.get("scaled_nutrition")
    if raw is None:
        return False
    if isinstance(raw, str):
        try:
            import json
            raw = json.loads(raw) if raw.strip() else []
        except Exception:
            return False
    if not isinstance(raw, list) or len(raw) == 0:
        return False
    return any(
        (n.get("nutrientName") or "").lower().startswith("energy")
        for n in raw if isinstance(n, dict)
    )


def _has_caffeine(nutrition: list) -> bool:
    """True if nutrition list already has a Caffeine entry."""
    if not nutrition or not isinstance(nutrition, list):
        return False
    for n in nutrition:
        if isinstance(n, dict) and (n.get("nutrientName") or "").strip().lower() == "caffeine":
            return True
    return False


def _parse_nutrition(ing) -> list:
    """Return ingredient nutrition as a list of dicts."""
    raw = ing.get("nutrition") or ing.get("scaled_nutrition")
    if isinstance(raw, str):
        try:
            import json
            raw = json.loads(raw) if raw.strip() else []
        except Exception:
            return []
    return list(raw) if isinstance(raw, list) else []


def fetch_ingredients_missing_caffeine(since_date=None, limit=None, caffeine_only_filter=False):
    """
    Fetch ingredients that have valid nutrition but no Caffeine entry.
    If caffeine_only_filter, only include names that might have caffeine (coffee, tea, matcha, etc.).
    """
    return _fetch_ingredients(
        since_date=since_date, limit=limit, require_missing_caffeine=True, caffeine_only_filter=caffeine_only_filter
    )


def fetch_ingredients_with_nutrition(since_date=None, limit=None):
    """Fetch ingredients that have valid nutrition (for --common-sense-only when we don't require missing caffeine)."""
    return _fetch_ingredients(since_date=since_date, limit=limit, require_missing_caffeine=False)


def _fetch_ingredients(since_date=None, limit=None, require_missing_caffeine=True, caffeine_only_filter=False):
    headers = {"Authorization": f"Bearer {get_token()}"}
    all_items = []
    page = 1
    per_page = 200
    CAFFEINE_KEYWORDS = ("coffee", "tea", "matcha", "espresso", "energy drink", "coke", "cola", "caffeine", "yerba", "guarana")

    while True:
        url = f"{PB_URL}/api/collections/ingredients/records?page={page}&perPage={per_page}&sort=-created"
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        items = data.get("items", [])

        for item in items:
            if not _has_valid_nutrition(item):
                continue
            if require_missing_caffeine:
                nut = _parse_nutrition(item)
                if _has_caffeine(nut):
                    continue
            if since_date:
                item_date = (item.get("timestamp") or item.get("created") or "")[:10]
                if item_date and item_date < since_date:
                    continue
            if caffeine_only_filter:
                name_lower = (item.get("name") or "").lower()
                if not any(kw in name_lower for kw in CAFFEINE_KEYWORDS):
                    continue
            all_items.append(item)
            if limit and len(all_items) >= limit:
                return all_items

        if len(items) < per_page:
            break
        page += 1

    return all_items


def _calories_from_nutrition(nutrition: list) -> float | None:
    """Extract calories from nutrition array."""
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


def get_caffeine_mg_for_ingredient(ing: dict, verbose: bool = False) -> float:
    """
    Get caffeine (mg) for this ingredient's portion via USDA.
    Returns 0 if no USDA match or no caffeine data.
    """
    name = (ing.get("name") or "").strip()
    quantity = float(ing.get("quantity") or 1)
    unit = (ing.get("unit") or "serving").strip().lower()
    usda_code = ing.get("usdaCode")

    serving_size_g = 100.0
    caffeine_per_100g = None

    if usda_code:
        usda = usda_lookup_by_fdc_id(usda_code)
        if usda:
            serving_size_g = usda.get("serving_size_g", 100.0)
            if unit in ("piece", "pieces"):
                piece_g = get_piece_grams(name)
                if piece_g is not None:
                    serving_size_g = piece_g
            raw_nut = usda.get("nutrition") or []
            caffeine_per_100g = extract_caffeine_mg_per_100g(raw_nut)
    if caffeine_per_100g is None:
        usda = usda_lookup(name)
        if usda:
            serving_size_g = usda.get("serving_size_g", 100.0)
            if unit in ("piece", "pieces"):
                piece_g = get_piece_grams(name)
                if piece_g is not None:
                    serving_size_g = piece_g
            raw_nut = usda.get("nutrition") or []
            caffeine_per_100g = extract_caffeine_mg_per_100g(raw_nut)

    if caffeine_per_100g is None:
        return 0.0

    grams = convert_to_grams(quantity, unit, serving_size_g)
    scaled_mg = round(caffeine_per_100g * grams / 100.0, 2)
    if verbose:
        print(f"      Caffeine: {caffeine_per_100g:.0f} mg/100g -> {scaled_mg:.0f} mg for portion")
    return scaled_mg


def merge_caffeine_into_nutrition(nutrition: list, caffeine_mg: float) -> list:
    """Return a new nutrition list with Caffeine set or appended (match by nutrientName + unitName)."""
    out = []
    found = False
    for n in nutrition or []:
        if not isinstance(n, dict):
            continue
        key = (n.get("nutrientName"), n.get("unitName"))
        if (n.get("nutrientName") or "").strip().lower() == "caffeine":
            out.append({"nutrientName": "Caffeine", "unitName": "MG", "value": round(caffeine_mg, 2)})
            found = True
        else:
            out.append(dict(n))
    if not found:
        out.append({"nutrientName": "Caffeine", "unitName": "MG", "value": round(caffeine_mg, 2)})
    return out


def patch_ingredient_nutrition(ing_id: str, nutrition: list, quantity=None, unit=None) -> bool:
    """PATCH ingredient with nutrition and optionally quantity/unit only (no source/usdaCode)."""
    headers = {"Authorization": f"Bearer {get_token()}"}
    url = f"{PB_URL}/api/collections/ingredients/records/{ing_id}"
    payload = {"nutrition": nutrition}
    if quantity is not None:
        payload["quantity"] = quantity
    if unit is not None:
        payload["unit"] = unit
    try:
        r = requests.patch(url, headers=headers, json=payload)
        return r.status_code in (200, 204)
    except Exception:
        return False


def run_common_sense_and_caffeine(
    ingredients: list,
    meal_text: str,
    do_common_sense: bool,
    do_caffeine: bool,
    dry_run: bool,
    verbose: bool,
):
    """
    Apply common-sense corrections then add caffeine. Modifies ingredients in place for nutrition/qty/unit.
    Returns list of (ing, updated_nutrition, updated_quantity, updated_unit) to PATCH.
    """
    # Build minimal list for common_sense_check
    minimal = []
    for ing in ingredients:
        nut = _parse_nutrition(ing)
        cal = _calories_from_nutrition(nut)
        minimal.append({
            "name": ing.get("name", "?"),
            "quantity": ing.get("quantity", 1),
            "unit": ing.get("unit", "serving"),
            "nutrition": nut,
            "calories": cal,
        })

    portion_updated_ids = set()
    if do_common_sense and meal_text and minimal:
        corrections = common_sense_check(meal_text, minimal)
        for corr in corrections:
            name_key = (corr.get("name") or "").strip().lower()
            if not name_key:
                continue
            for i, ing in enumerate(ingredients):
                if (ing.get("name") or "").strip().lower() != name_key:
                    continue
                if corr.get("zero_calories"):
                    minimal[i]["nutrition"] = zero_calorie_nutrition_array()
                    if verbose:
                        print(f"   🧠 Common sense: {ing.get('name')} -> 0 cal")
                if "quantity" in corr or "unit" in corr or "serving_size_g" in corr:
                    new_qty = corr.get("quantity", minimal[i]["quantity"])
                    new_unit = corr.get("unit", minimal[i]["unit"])
                    new_serving_g = corr.get("serving_size_g")
                    minimal[i]["quantity"] = new_qty
                    minimal[i]["unit"] = new_unit
                    ing["quantity"] = new_qty
                    ing["unit"] = new_unit
                    portion_updated_ids.add(ing.get("id"))
                    if new_serving_g is not None and ing.get("usdaCode"):
                        usda = usda_lookup_by_fdc_id(ing["usdaCode"])
                        if usda and usda.get("nutrition"):
                            norm = normalize_usda_food_nutrients(usda["nutrition"])
                            if norm:
                                scaled = scale_nutrition(norm, new_qty, new_unit, new_serving_g, quiet=True)
                                minimal[i]["nutrition"] = scaled
                            if verbose:
                                print(f"   🧠 Common sense: {ing.get('name')} -> {new_qty} {new_unit} ({new_serving_g}g)")
                    else:
                        if verbose:
                            print(f"   🧠 Common sense: {ing.get('name')} -> {new_qty} {new_unit}")
                break

    # Now each ingredient has minimal[i].nutrition (possibly updated by common-sense). Add caffeine.
    to_patch = []
    for i, ing in enumerate(ingredients):
        nut = minimal[i]["nutrition"]
        if do_caffeine:
            caffeine_mg = get_caffeine_mg_for_ingredient(ing, verbose=verbose)
            nut = merge_caffeine_into_nutrition(nut, caffeine_mg)
        patch_qty = ing.get("quantity") if ing.get("id") in portion_updated_ids else None
        patch_unit = ing.get("unit") if ing.get("id") in portion_updated_ids else None
        to_patch.append((ing, nut, patch_qty, patch_unit))
    return to_patch


def backfill(limit=None, dry_run=False, since_date=None, caffeine_only=False, common_sense_only=False, verbose=True):
    do_caffeine = not common_sense_only
    do_common_sense = not caffeine_only

    print("📊 Backfill: Caffeine + common-sense")
    print(f"   Caffeine: {do_caffeine}, Common-sense: {do_common_sense}")
    print(f"   PB_URL: {PB_URL}")
    if since_date:
        print(f"   Since: {since_date}")
    if limit:
        print(f"   Limit: {limit}")

    if common_sense_only:
        ingredients = fetch_ingredients_with_nutrition(since_date=since_date, limit=limit)
        print(f"   Found {len(ingredients)} ingredients with nutrition (common-sense only)\n")
    else:
        ingredients = fetch_ingredients_missing_caffeine(since_date=since_date, limit=limit)
        print(f"   Found {len(ingredients)} ingredients missing Caffeine\n")

    if not ingredients:
        print("   Nothing to do.")
        return

    by_meal = defaultdict(list)
    for ing in ingredients:
        mid = ing.get("mealId")
        if mid:
            by_meal[mid].append(ing)

    updated = 0
    errors = 0

    for meal_id, meal_ings in by_meal.items():
        meal = fetch_meal_by_id(meal_id) if do_common_sense else None
        meal_text = (meal.get("text") or "").strip() if meal else ""

        to_patch = run_common_sense_and_caffeine(
            meal_ings, meal_text, do_common_sense, do_caffeine, dry_run, verbose
        )

        for ing, new_nutrition, qty, unit in to_patch:
            if verbose:
                print(f"   PATCH {ing.get('name')} (id={ing.get('id')})")
            if not dry_run:
                if patch_ingredient_nutrition(ing["id"], new_nutrition, quantity=qty, unit=unit):
                    updated += 1
                else:
                    errors += 1
                    if verbose:
                        print(f"      ❌ PATCH failed")
            else:
                updated += 1

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Done! Updated {updated}, errors {errors}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill Caffeine and optionally common-sense corrections")
    parser.add_argument("--limit", type=int, help="Max ingredients to process")
    parser.add_argument("--dry-run", action="store_true", help="Don't update, just show what would happen")
    parser.add_argument("--since", type=str, help="Only process ingredients since this date (YYYY-MM-DD)")
    parser.add_argument("--caffeine-only", action="store_true", help="Only add Caffeine, skip common-sense")
    parser.add_argument("--common-sense-only", action="store_true", help="Only run common-sense, do not add Caffeine")
    parser.add_argument("-q", "--quiet", action="store_true", help="Less verbose output")
    args = parser.parse_args()

    if args.caffeine_only and args.common_sense_only:
        print("Cannot use both --caffeine-only and --common-sense-only")
        exit(1)

    backfill(
        limit=args.limit,
        dry_run=args.dry_run,
        since_date=args.since,
        caffeine_only=args.caffeine_only,
        common_sense_only=args.common_sense_only,
        verbose=not args.quiet,
    )
