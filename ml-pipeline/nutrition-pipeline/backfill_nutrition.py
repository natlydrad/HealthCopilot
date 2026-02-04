#!/usr/bin/env python3
"""
Backfill nutrition for existing ingredients that have empty/missing nutrition.
Uses the same logic as parse_api: USDA lookup → scale by quantity/unit → validate →
usda_lookup_valid_for_portion if needed → GPT estimate fallback.
Stores the scaled nutrition array (not per-100g) so the dashboard displays correctly.
"""

import os
import requests
import argparse
from dotenv import load_dotenv

load_dotenv()

from pb_client import get_token, PB_URL
from lookup_usda import (
    usda_lookup,
    usda_lookup_valid_for_portion,
    scale_nutrition,
    get_piece_grams,
    validate_scaled_calories,
)
from parser_gpt import gpt_estimate_nutrition


def _has_valid_nutrition(ing) -> bool:
    """Check if ingredient has non-empty nutrition suitable for display."""
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
    # Must have at least Energy/calories
    has_energy = any(
        (n.get("nutrientName") or "").lower().startswith("energy")
        for n in raw if isinstance(n, dict)
    )
    return has_energy


def fetch_ingredients_without_nutrition(since_date=None, limit=None, debug=False):
    """Fetch ingredients that lack valid nutrition data."""
    headers = {"Authorization": f"Bearer {get_token()}"}
    all_items = []
    total_seen = 0
    page = 1
    per_page = 200

    while True:
        url = f"{PB_URL}/api/collections/ingredients/records?page={page}&perPage={per_page}&sort=-created"
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        items = data.get("items", [])

        for item in items:
            total_seen += 1
            if not _has_valid_nutrition(item):
                if since_date:
                    item_date = (item.get("timestamp") or item.get("created") or "")[:10]
                    if item_date and item_date < since_date:
                        continue
                all_items.append(item)
                if limit and len(all_items) >= limit:
                    if debug:
                        print(f"   [debug] total fetched: {total_seen}, without nutrition: {len(all_items)}")
                    return all_items

        if len(items) < per_page:
            break
        page += 1

    if debug:
        print(f"   [debug] total fetched: {total_seen}, without nutrition: {len(all_items)}")
    return all_items


def _lookup_and_scale_nutrition(name: str, quantity: float, unit: str):
    """
    Same logic as parse_api: USDA → validate → fallback → GPT.
    Returns (scaled_nutrition, source, usda_code).
    """
    name = (name or "").strip()
    if not name or len(name) < 2:
        return None, None, None

    quantity = quantity or 1
    unit = (unit or "serving").strip()
    unit_lower = unit.lower()

    usda = usda_lookup(name)
    scaled_nutrition = []
    source = "gpt"
    usda_code = None

    if usda:
        serving_size = usda.get("serving_size_g", 100.0)
        if unit_lower in ("piece", "pieces"):
            piece_g = get_piece_grams(name)
            if piece_g is not None:
                serving_size = piece_g
        scaled_nutrition = scale_nutrition(usda.get("nutrition", []), quantity, unit, serving_size)
        cal_val = next((n.get("value", 0) for n in scaled_nutrition if n.get("nutrientName") == "Energy"), 0)
        is_valid, _ = validate_scaled_calories(name, quantity, unit, cal_val)
        if not is_valid:
            usda = None
            scaled_nutrition = []
            usda = usda_lookup_valid_for_portion(name, quantity, unit)
            if usda:
                serving_size = usda.get("serving_size_g", 100.0)
                if unit_lower in ("piece", "pieces"):
                    piece_g = get_piece_grams(name)
                    if piece_g is not None:
                        serving_size = piece_g
                scaled_nutrition = scale_nutrition(usda.get("nutrition", []), quantity, unit, serving_size)
                source = "usda"
                usda_code = usda.get("usdaCode")
        else:
            source = "usda"
            usda_code = usda.get("usdaCode")

    if not scaled_nutrition:
        gpt_nut = gpt_estimate_nutrition(name, quantity, unit)
        if gpt_nut:
            scaled_nutrition = gpt_nut
            source = "gpt"

    return scaled_nutrition, source, usda_code


def update_ingredient(ing_id: str, nutrition: list, source: str, usda_code: str | None) -> bool:
    """PATCH ingredient with nutrition, source, usdaCode."""
    headers = {"Authorization": f"Bearer {get_token()}"}
    url = f"{PB_URL}/api/collections/ingredients/records/{ing_id}"
    payload = {"nutrition": nutrition, "source": source}
    if usda_code is not None:
        payload["usdaCode"] = usda_code
    r = requests.patch(url, headers=headers, json=payload)
    return r.status_code in (200, 204)


def backfill_nutrition(limit=None, dry_run=False, since_date=None, verbose=True):
    print("📊 Backfilling nutrition for ingredients with empty/missing nutrition...")
    print(f"   PB_URL: {PB_URL}")

    if since_date:
        print(f"   Filtering to ingredients since {since_date}")
    if limit:
        print(f"   Limit: {limit}")

    ingredients = fetch_ingredients_without_nutrition(since_date=since_date, limit=limit)
    print(f"   Found {len(ingredients)} ingredients to process\n")

    updated = 0
    skipped = 0
    errors = 0

    for i, ing in enumerate(ingredients):
        name = ing.get("name") or ""
        qty = ing.get("quantity", 1)
        unit = ing.get("unit") or "serving"
        category = ing.get("category", "food")

        if category == "supplement":
            if verbose:
                print(f"[{i + 1}/{len(ingredients)}] {name}: skipping supplement")
            skipped += 1
            continue

        if verbose:
            print(f"[{i + 1}/{len(ingredients)}] {name} ({qty} {unit})")

        try:
            scaled_nutrition, source, usda_code = _lookup_and_scale_nutrition(name, qty, unit)
            if not scaled_nutrition:
                if verbose:
                    print(f"   ⏭️ No nutrition found (USDA + GPT failed)")
                skipped += 1
                continue

            cal = next((n.get("value") for n in scaled_nutrition if n.get("nutrientName") == "Energy"), 0)
            if verbose:
                print(f"   ✅ {source}: {cal:.0f} cal")

            if not dry_run:
                if update_ingredient(ing["id"], scaled_nutrition, source, usda_code):
                    updated += 1
                else:
                    errors += 1
                    if verbose:
                        print(f"   ❌ PATCH failed")
            else:
                updated += 1

        except Exception as e:
            errors += 1
            if verbose:
                print(f"   ❌ Error: {e}")

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Done! Updated {updated}, skipped {skipped}, errors {errors}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill nutrition for ingredients with empty nutrition")
    parser.add_argument("--limit", type=int, help="Max ingredients to process")
    parser.add_argument("--dry-run", action="store_true", help="Don't update, just show what would happen")
    parser.add_argument("--since", type=str, help="Only process ingredients since this date (YYYY-MM-DD)")
    parser.add_argument("-q", "--quiet", action="store_true", help="Less verbose output")
    parser.add_argument("--debug", action="store_true", help="Show fetch stats (total vs without nutrition)")
    args = parser.parse_args()

    backfill_nutrition(
        limit=args.limit,
        dry_run=args.dry_run,
        since_date=args.since,
        verbose=not args.quiet or args.debug,
    )
