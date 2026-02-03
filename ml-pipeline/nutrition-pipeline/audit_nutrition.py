#!/usr/bin/env python3
"""
Audit stored nutrition for ingredients. Dumps what's actually in PocketBase
to debug incomplete macros (e.g. chicken salad sandwich with no carbs).

Usage:
  python audit_nutrition.py [date]     # e.g. 2026-01-27
  python audit_nutrition.py --name "chicken salad"  # filter by ingredient name
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

PB_URL = os.getenv("PB_URL", "https://pocketbase-1j2x.onrender.com")
PB_EMAIL = os.getenv("PB_EMAIL")
PB_PASSWORD = os.getenv("PB_PASSWORD")


def get_token():
    r = requests.post(f"{PB_URL}/api/collections/users/auth-with-password",
                      json={"identity": PB_EMAIL, "password": PB_PASSWORD})
    r.raise_for_status()
    return r.json()["token"]


def fetch(path, token, params=None):
    r = requests.get(f"{PB_URL}{path}", headers={"Authorization": f"Bearer {token}"}, params=params or {})
    r.raise_for_status()
    return r.json()


def extract_macros(nutrition):
    """Extract macros from nutrition array (matches lookup_usda + frontend logic)."""
    if not isinstance(nutrition, list):
        return None
    macros = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
    for n in nutrition:
        name = (n.get("nutrientName") or n.get("name") or "").lower()
        value = n.get("value", 0) or 0
        unit = (n.get("unitName") or n.get("unit") or "").upper()
        if "energy" in name and unit == "KCAL":
            macros["calories"] = value
        elif name == "protein":
            macros["protein"] = value
        elif "carbohydrate" in name or "carb" in name:
            macros["carbs"] = value
        elif "total lipid" in name or "fat" in name:
            macros["fat"] = value
    return macros


def main():
    if not PB_EMAIL or not PB_PASSWORD:
        print("❌ Set PB_EMAIL and PB_PASSWORD in .env")
        return

    # Parse args
    name_filter = None
    date_filter = None
    for a in sys.argv[1:]:
        if a.startswith("--name="):
            name_filter = a[7:].lower()
        elif a.startswith("--name "):
            name_filter = a[7:].lower()
        elif len(a) == 10 and a[4] == "-" and a[7] == "-" and a.replace("-", "").isdigit():
            date_filter = a

    print("🔗 Connecting to PocketBase...")
    token = get_token()
    print("✅ Authenticated\n")

    # Fetch meals (optionally filtered by date)
    if date_filter:
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            from backports.zoneinfo import ZoneInfo
        tz = ZoneInfo(os.getenv("TZ", "America/New_York"))
        start = datetime(int(date_filter[:4]), int(date_filter[5:7]), int(date_filter[8:10]), 0, 0, 0, tzinfo=tz)
        end = datetime(int(date_filter[:4]), int(date_filter[5:7]), int(date_filter[8:10]), 23, 59, 59, 999000, tzinfo=tz)
        start_utc = start.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M:%S.%f")[:23] + "Z"
        end_utc = end.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M:%S.%f")[:23] + "Z"
        filt = urllib.parse.quote(f'timestamp >= "{start_utc}" && timestamp <= "{end_utc}"')
        meals_data = fetch(f"/api/collections/meals/records?filter={filt}&perPage=100&sort=timestamp", token)
    else:
        meals_data = fetch("/api/collections/meals/records?perPage=200&sort=-timestamp", token)

    meals = meals_data.get("items", [])
    meal_ids = {m["id"] for m in meals}

    # Fetch all ingredients for these meals
    all_ings = []
    for mid in meal_ids:
        ing_filt = urllib.parse.quote(f"mealId='{mid}'")
        ing_data = fetch(f"/api/collections/ingredients/records?filter={ing_filt}&perPage=200", token)
        all_ings.extend(ing_data.get("items", []))

    if name_filter:
        all_ings = [i for i in all_ings if name_filter in (i.get("name") or "").lower()]

    print("=" * 70)
    print("NUTRITION AUDIT — Stored data in PocketBase")
    print("=" * 70)
    print(f"Ingredients: {len(all_ings)} (date_filter={date_filter}, name_filter={name_filter or 'none'})\n")

    for ing in all_ings:
        name = ing.get("name", "?")
        source = ing.get("source", "?")
        qty = ing.get("quantity")
        unit = ing.get("unit", "")
        nutrition = ing.get("nutrition")
        if isinstance(nutrition, str):
            try:
                nutrition = json.loads(nutrition)
            except json.JSONDecodeError:
                nutrition = None

        macros = extract_macros(nutrition) if nutrition else None
        print(f"\n📦 {name} ({qty} {unit}) [source={source}]")
        print(f"   nutrition type: {type(nutrition).__name__}, len={len(nutrition) if isinstance(nutrition, list) else 'N/A'}")
        if macros:
            print(f"   extracted macros: {macros['calories']:.0f} cal, {macros['protein']:.0f}g P, {macros['carbs']:.0f}g C, {macros['fat']:.0f}g F")
        else:
            print("   extracted macros: (none)")
        if isinstance(nutrition, list) and nutrition:
            # Show raw nutrient names (helps catch naming mismatches)
            names = [n.get("nutrientName") or n.get("name") or "?" for n in nutrition[:12]]
            print(f"   nutrient names: {names}")
            if len(nutrition) > 12:
                print(f"   ... +{len(nutrition)-12} more")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
