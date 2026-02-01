#!/usr/bin/env python3
"""
Backfill macros for existing ingredients that don't have them.
Looks up each ingredient in USDA and calculates macros based on quantity.
"""

import os
import requests
import argparse
from dotenv import load_dotenv
load_dotenv()

from lookup_usda import usda_lookup
from enrich_meals import estimate_grams, calculate_macros

PB_URL = os.getenv("PB_URL", "http://127.0.0.1:8090")
PB_EMAIL = os.getenv("PB_EMAIL")
PB_PASSWORD = os.getenv("PB_PASSWORD")

_token = None

def get_token():
    global _token
    if _token:
        return _token
    r = requests.post(f"{PB_URL}/api/collections/users/auth-with-password",
                      json={"identity": PB_EMAIL, "password": PB_PASSWORD})
    r.raise_for_status()
    _token = r.json()["token"]
    return _token


def fetch_ingredients_without_nutrition(since_date=None):
    """Fetch ingredients that have no USDA nutrition data."""
    headers = {"Authorization": f"Bearer {get_token()}"}
    all_items = []
    page = 1
    
    while True:
        url = f"{PB_URL}/api/collections/ingredients/records?page={page}&perPage=200&sort=-created"
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        items = data.get("items", [])
        
        # Filter to those without nutrition data and within date range
        for item in items:
            nutrition = item.get("nutrition")
            has_nutrition = isinstance(nutrition, list) and len(nutrition) > 0
            
            if not has_nutrition:
                # Check date filter
                if since_date:
                    item_date = (item.get("timestamp") or item.get("created") or "")[:10]
                    if item_date < since_date:
                        continue
                all_items.append(item)
        
        if len(items) < 200:
            break
        page += 1
    
    return all_items


def update_ingredient(ing_id: str, usda_data: dict):
    """Update an ingredient with USDA nutrition data."""
    headers = {"Authorization": f"Bearer {get_token()}"}
    url = f"{PB_URL}/api/collections/ingredients/records/{ing_id}"
    
    update = {
        "nutrition": usda_data.get("nutrition", []),
        "source": "usda",
        "usdaCode": usda_data.get("usdaCode"),
    }
    
    r = requests.patch(url, headers=headers, json=update)
    return r.status_code == 200


def backfill_macros(limit=None, dry_run=False, since_date=None):
    print("📊 Backfilling macros for existing ingredients...")
    if since_date:
        print(f"   Filtering to ingredients since {since_date}")
    
    ingredients = fetch_ingredients_without_nutrition(since_date=since_date)
    print(f"Found {len(ingredients)} ingredients without macros")
    
    if limit:
        ingredients = ingredients[:limit]
        print(f"Limited to {limit}")
    
    updated = 0
    skipped = 0
    errors = 0
    
    for ing in ingredients:
        name = ing["name"]
        qty = ing.get("quantity", 1)
        unit = ing.get("unit", "serving")
        
        # Skip supplements (no macros)
        category = ing.get("category", "food")
        if category == "supplement":
            skipped += 1
            continue
        
        try:
            usda = usda_lookup(name)
            if usda and usda.get("nutrition"):
                grams = estimate_grams(qty, unit)
                macros = calculate_macros(usda.get("macros_per_100g", {}), grams)
                
                print(f"  {name} ({qty} {unit}): {macros['calories']:.0f} cal, {macros['protein']:.0f}g protein")
                
                if not dry_run:
                    if update_ingredient(ing["id"], usda):
                        updated += 1
                    else:
                        errors += 1
                else:
                    updated += 1
            else:
                print(f"  {name}: no USDA data found")
                skipped += 1
        except Exception as e:
            print(f"  {name}: error - {e}")
            errors += 1
    
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Done! Updated {updated}, skipped {skipped}, errors {errors}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill macros for existing ingredients")
    parser.add_argument("--limit", type=int, help="Max ingredients to process")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually update, just show what would happen")
    parser.add_argument("--last-week", action="store_true", help="Only process ingredients from the last 7 days")
    parser.add_argument("--since", type=str, help="Only process ingredients since this date (YYYY-MM-DD)")
    args = parser.parse_args()
    
    since_date = args.since
    if args.last_week:
        from datetime import datetime, timedelta
        since_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    
    backfill_macros(limit=args.limit, dry_run=args.dry_run, since_date=since_date)
