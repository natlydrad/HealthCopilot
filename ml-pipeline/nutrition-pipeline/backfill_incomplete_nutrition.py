#!/usr/bin/env python3
"""
Refresh nutrition for ingredients that have incomplete macros (e.g. only Energy).
Uses USDA lookup + GPT fallback, same as parse flow. Dry-run by default.

Usage:
  python backfill_incomplete_nutrition.py --dry-run   # preview what would be updated
  python backfill_incomplete_nutrition.py             # actually update
  python backfill_incomplete_nutrition.py --date 2026-01-27  # limit to one day
"""
import os
import sys
import json
import urllib.parse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

import requests
from lookup_usda import usda_lookup, scale_nutrition, get_piece_grams, validate_scaled_calories
from parser_gpt import gpt_estimate_nutrition

PB_URL = os.getenv("PB_URL", "https://pocketbase-1j2x.onrender.com")
PB_EMAIL = os.getenv("PB_EMAIL")
PB_PASSWORD = os.getenv("PB_PASSWORD")
SERVICE_TOKEN = os.getenv("PB_SERVICE_TOKEN") or os.getenv("SERVICE_TOKEN")


def get_token():
    if SERVICE_TOKEN:
        return SERVICE_TOKEN
    r = requests.post(f"{PB_URL}/api/collections/users/auth-with-password",
                      json={"identity": PB_EMAIL, "password": PB_PASSWORD})
    r.raise_for_status()
    return r.json()["token"]


def fetch(path, token, params=None):
    r = requests.get(f"{PB_URL}{path}", headers={"Authorization": f"Bearer {token}"}, params=params or {})
    r.raise_for_status()
    return r.json()


def patch(path, token, data):
    r = requests.patch(f"{PB_URL}{path}", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }, json=data)
    r.raise_for_status()
    return r.json()


def has_complete_macros(nutrition):
    """Return False if nutrition is missing any of Energy, Protein, Carb, Fat."""
    if not isinstance(nutrition, list) or len(nutrition) < 4:
        return False
    names_lower = [n.get("nutrientName", "").lower() for n in nutrition]
    has_energy = any("energy" in n for n in names_lower)
    has_protein = any(n == "protein" for n in names_lower)
    has_carb = any("carbohydrate" in n for n in names_lower)
    has_fat = any("lipid" in n or n == "fat" for n in names_lower)
    return has_energy and has_protein and has_carb and has_fat


def main():
    dry_run = "--dry-run" in sys.argv or "-n" in sys.argv
    date_arg = None
    for a in sys.argv[1:]:
        if a.startswith("--date="):
            date_arg = a[7:]
        elif a.startswith("--date "):
            date_arg = sys.argv[sys.argv.index(a) + 1] if sys.argv.index(a) + 1 < len(sys.argv) else None

    if not PB_EMAIL or not PB_PASSWORD:
        if not SERVICE_TOKEN:
            print("❌ Set PB_EMAIL/PB_PASSWORD or PB_SERVICE_TOKEN in .env")
            return

    print("🔗 Connecting to PocketBase...")
    token = get_token()
    print("✅ Authenticated")
    print(f"   Mode: {'DRY RUN (no updates)' if dry_run else 'LIVE (will update)'}\n")

    if date_arg:
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            from backports.zoneinfo import ZoneInfo
        tz = ZoneInfo(os.getenv("TZ", "America/New_York"))
        start = datetime(int(date_arg[:4]), int(date_arg[5:7]), int(date_arg[8:10]), 0, 0, 0, tzinfo=tz)
        end = datetime(int(date_arg[:4]), int(date_arg[5:7]), int(date_arg[8:10]), 23, 59, 59, 999000, tzinfo=tz)
        start_utc = start.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M:%S.%f")[:23] + "Z"
        end_utc = end.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M:%S.%f")[:23] + "Z"
        filt = urllib.parse.quote(f'timestamp >= "{start_utc}" && timestamp <= "{end_utc}"')
        meals_data = fetch(f"/api/collections/meals/records?filter={filt}&perPage=100&sort=timestamp", token)
    else:
        meals_data = fetch("/api/collections/meals/records?perPage=300&sort=-timestamp", token)

    meals = meals_data.get("items", [])
    meal_ids = {m["id"] for m in meals}
    all_ings = []
    for mid in meal_ids:
        ing_filt = urllib.parse.quote(f"mealId='{mid}'")
        ing_data = fetch(f"/api/collections/ingredients/records?filter={ing_filt}&perPage=200", token)
        all_ings.extend(ing_data.get("items", []))

    incomplete = [i for i in all_ings if not has_complete_macros(i.get("nutrition"))]
    print(f"Found {len(incomplete)} ingredients with incomplete nutrition (of {len(all_ings)} total)\n")

    updated = 0
    for ing in incomplete:
        name = ing.get("name", "?")
        ing_id = ing.get("id")
        qty = ing.get("quantity", 1)
        unit = ing.get("unit", "serving") or "serving"

        usda = usda_lookup(name)
        scaled = []
        source = "gpt"
        if usda:
            serving_size = usda.get("serving_size_g", 100.0)
            unit_lower = (unit or "").lower()
            if unit_lower in ("piece", "pieces"):
                pg = get_piece_grams(name)
                if pg is not None:
                    serving_size = pg
            scaled = scale_nutrition(usda.get("nutrition", []), qty, unit, serving_size)
            cal_val = next((n.get("value", 0) for n in scaled if n.get("nutrientName") == "Energy"), 0)
            if validate_scaled_calories(name, qty, unit, cal_val)[0]:
                source = "usda"
        if not scaled:
            scaled = gpt_estimate_nutrition(name, qty, unit)
        if not scaled:
            print(f"   ⚠️ Skip {name}: no USDA/GPT result")
            continue

        cal = next((n.get("value", 0) for n in scaled if n.get("nutrientName") == "Energy"), 0)
        prot = next((n.get("value", 0) for n in scaled if n.get("nutrientName") == "Protein"), 0)
        carb = next((n.get("value", 0) for n in scaled if "carbohydrate" in (n.get("nutrientName") or "").lower()), 0)
        fat = next((n.get("value", 0) for n in scaled if "lipid" in (n.get("nutrientName") or "").lower() or n.get("nutrientName") == "fat"), 0)
        print(f"   {'Would update' if dry_run else 'Updating'} {name}: {cal:.0f} cal, {prot:.0f}g P, {carb:.0f}g C, {fat:.0f}g F [{source}]")

        if not dry_run:
            patch(f"/api/collections/ingredients/records/{ing_id}", token, {
                "nutrition": scaled,
                "source": source,
                "usdaCode": usda.get("usdaCode") if usda else None,
            })
            updated += 1

    total = len(incomplete)
    print(f"\n{'Would update' if dry_run else 'Updated'}: {total if dry_run else updated} ingredients")


if __name__ == "__main__":
    main()
