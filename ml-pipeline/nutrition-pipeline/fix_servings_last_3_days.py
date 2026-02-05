#!/usr/bin/env python3
"""
Check and fix foodGroupServings for ingredients in the last 3 days of meals.
Recomputes servings from current quantity/unit/name (matching foodFrameworks.js logic)
and patches ingredients where stored values differ.
Usage: python fix_servings_last_3_days.py [--dry-run]
"""
import os
import sys
import re
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pb_client import get_token, fetch_ingredients_by_meal_id
import requests
import urllib.parse

PB_URL = os.getenv("PB_URL") or "http://127.0.0.1:8090"

# Port of foodFrameworks.js - keyword lists and unit conversion
UNIT_TO_GRAMS = {
    "oz": 28.35, "g": 1, "grams": 1, "gram": 1, "cup": 150, "cups": 150,
    "tbsp": 15, "tablespoon": 15, "tsp": 5, "teaspoon": 5,
    "piece": 50, "pieces": 50, "slice": 20, "slices": 20, "serving": 100,
    "eggs": 50, "egg": 50, "pill": 0, "pills": 0, "capsule": 0, "capsules": 0,
    "l": 0, "liter": 1000, "ml": 1,
}

BEANS = ["bean", "beans", "lentil", "lentils", "chickpea", "chickpeas", "hummus", "edamame", "tofu", "tempeh", "soy", "split pea", "black bean", "pinto", "kidney", "garbanzo"]
BERRIES = ["berry", "berries", "strawberry", "strawberries", "blueberry", "blueberries", "raspberry", "raspberries", "blackberry", "blackberries", "cherry", "cherries", "cranberry", "cranberries"]
OTHER_FRUITS = ["apple", "apples", "banana", "bananas", "orange", "oranges", "grape", "grapes", "mango", "mangoes", "pineapple", "pineapples", "kiwi", "kiwis", "peach", "peaches", "pear", "pears", "plum", "plums", "melon", "melons", "watermelon", "watermelons", "cantaloupe", "avocado", "avocados", "grapefruit"]
CRUCIFEROUS = ["broccoli", "brussels", "cabbage", "cauliflower", "kale", "bok choy", "arugula", "collard", "mustard green", "turnip", "radish", "watercress"]
GREENS = ["lettuce", "spinach", "kale", "arugula", "chard", "collard", "mustard", "turnip green", "watercress", "dandelion", "endive", "mesclun"]
OTHER_VEG = ["carrot", "carrots", "tomato", "tomatoes", "marinara", "pasta sauce", "tomato sauce", "cucumber", "pepper", "peppers", "onion", "garlic", "celery", "mushroom", "zucchini", "squash", "eggplant", "asparagus", "green bean", "beet", "corn", "pea", "salsa", "vegetable"]
NUTS = ["nut", "nuts", "almond", "almonds", "walnut", "walnuts", "cashew", "cashews", "peanut", "peanuts", "pecan", "pecans", "pistachio", "nut butter", "almond butter", "peanut butter"]
WHOLE_GRAINS = ["oat", "oats", "oatmeal", "quinoa", "brown rice", "barley", "millet", "bulgur", "whole wheat", "whole grain"]
GRAINS_ALL = WHOLE_GRAINS + ["flour", "wheat", "rye", "couscous", "wrap", "bun", "roll", "focaccia", "bread", "toast", "bagel", "pita", "tortilla", "rice", "pasta", "noodle", "cereal", "cracker", "muffin", "pizza", "crust"]
PROTEIN = ["chicken", "beef", "pork", "turkey", "lamb", "fish", "salmon", "tuna", "sardine", "shrimp", "crab", "lobster", "egg", "meat", "sausage", "bacon", "ham", "burger", "patty", "wing", "breast", "thigh", "steak", "rib"]
DAIRY = ["milk", "cheese", "yogurt", "butter", "cream", "cottage cheese", "greek yogurt", "kefir"]


def to_grams(qty: float, unit: str) -> float:
    u = (unit or "serving").lower()
    return qty * UNIT_TO_GRAMS.get(u, 80)


def _includes(name: str, keywords: list) -> bool:
    return any(k in name for k in keywords)


def compute_myplate_servings(ing: dict) -> dict:
    """Compute MyPlate servings (grains, vegetables, fruits, protein, dairy) from ingredient.
    Matches foodFrameworks.js keyword-based logic for consistency with dashboard.
    """
    mp = {"grains": 0, "vegetables": 0, "fruits": 0, "protein": 0, "dairy": 0}
    cat = ing.get("category") or "food"
    if cat == "supplement":
        return mp

    name = (ing.get("name") or "").lower()
    qty = float(ing.get("quantity") or 1)
    unit = (ing.get("unit") or "").lower()
    grams = to_grams(qty, unit)

    if _includes(name, BEANS):
        if unit in ("cup", "cups"):
            mp["protein"] = qty * 4
        elif unit in ("tbsp", "tablespoon"):
            mp["protein"] = 0.5
        else:
            mp["protein"] = grams / 28
    elif _includes(name, BERRIES):
        if unit in ("cup", "cups"):
            mp["fruits"] = qty
        else:
            mp["fruits"] = grams / 150
    elif _includes(name, OTHER_FRUITS):
        if unit in ("cup", "cups"):
            mp["fruits"] = qty
        elif unit in ("piece", "pieces"):
            mp["fruits"] = qty  # 1 apple = 1 serving (MyPlate)
        else:
            mp["fruits"] = grams / 150
    elif _includes(name, CRUCIFEROUS):
        if unit in ("cup", "cups"):
            mp["vegetables"] = qty
        else:
            mp["vegetables"] = grams / 150
    elif _includes(name, GREENS):
        if unit in ("cup", "cups"):
            mp["vegetables"] = qty
        else:
            mp["vegetables"] = grams / 150
    elif _includes(name, OTHER_VEG):
        if unit in ("cup", "cups"):
            mp["vegetables"] = qty
        elif unit in ("piece", "pieces"):
            mp["vegetables"] = qty * 0.5
        else:
            mp["vegetables"] = grams / 150
    elif _includes(name, NUTS):
        pass  # nuts don't map to MyPlate top 5
    elif "flax" in name or "chia" in name:
        pass
    elif "turmeric" in name or "cumin" in name or "cinnamon" in name or "spice" in name:
        pass
    elif _includes(name, GRAINS_ALL):
        is_whole = _includes(name, WHOLE_GRAINS)
        if unit in ("slice", "slices"):
            mp["grains"] = qty
        elif unit in ("piece", "pieces"):
            mp["grains"] = qty
        elif unit in ("cup", "cups"):
            mp["grains"] = qty * 2
        else:
            mp["grains"] = grams / 28
        if _includes(name, PROTEIN) or _includes(name, BEANS):
            pass  # grain products that are also protein/beans handled above
        elif not _includes(name, PROTEIN) and not _includes(name, BEANS):
            mp["protein"] = 0  # pure grain, no protein
    elif _includes(name, PROTEIN) and not _includes(name, BEANS):
        if unit == "oz":
            mp["protein"] = qty
        elif unit in ("egg", "eggs"):
            mp["protein"] = qty
        elif unit in ("cup", "cups"):
            mp["protein"] = qty * 4
        else:
            mp["protein"] = grams / 28
    elif _includes(name, DAIRY):
        if unit in ("cup", "cups"):
            mp["dairy"] = qty
        elif unit == "oz":
            mp["dairy"] = qty / 8
        else:
            mp["dairy"] = grams / 240

    # Soy/oat milk etc -> legumes, not dairy; broth -> no protein
    if re.search(r"\b(almond|oat|coconut|cashew|rice)\s*milk\b", name):
        mp["dairy"] = 0
    if re.search(r"\b(broth|stock)\b", name):
        mp["protein"] = 0

    return mp


def fetch_meals_for_date_range(start_iso: str, end_iso: str):
    """Fetch meals where timestamp is in [start_iso, end_iso]."""
    start_ts = f"{start_iso} 00:00:00.000Z"
    end_ts = f"{end_iso} 23:59:59.999Z"
    filter_str = f'timestamp >= "{start_ts}" && timestamp <= "{end_ts}"'
    encoded = urllib.parse.quote(filter_str)
    headers = {"Authorization": f"Bearer {get_token()}"}
    all_meals = []
    page = 1
    while True:
        url = f"{PB_URL}/api/collections/meals/records?filter={encoded}&sort=-timestamp&perPage=50&page={page}"
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            break
        items = r.json().get("items", [])
        all_meals.extend(items)
        if len(items) < 50:
            break
        page += 1
    return all_meals


def _servings_match(a: dict, b: dict, tol: float = 0.01) -> bool:
    for k in ("grains", "vegetables", "fruits", "protein", "dairy"):
        va = float(a.get(k) or 0)
        vb = float(b.get(k) or 0)
        if abs(va - vb) > tol:
            return False
    return True


def main():
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("DRY RUN - no changes will be written\n")

    today = datetime.utcnow().date()
    start_date = (today - timedelta(days=3)).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")

    print(f"Fetching meals from {start_date} to {end_date}...")
    meals = fetch_meals_for_date_range(start_date, end_date)
    print(f"Found {len(meals)} meals\n")

    fixed = 0
    checked = 0

    for meal in meals:
        ts = meal.get("timestamp", "")
        text = (meal.get("text") or "")[:50]
        ings = fetch_ingredients_by_meal_id(meal.get("id"))
        for ing in ings:
            if (ing.get("category") or "food") == "supplement":
                continue
            checked += 1
            computed = compute_myplate_servings(ing)
            pm = ing.get("parsingMetadata") or {}
            stored = (pm.get("foodGroupServings") or {}) if isinstance(pm, dict) else {}

            if _servings_match(computed, stored):
                continue

            name = ing.get("name") or "?"
            qty = ing.get("quantity", 1)
            unit = ing.get("unit") or "serving"
            print(f"  Fix: {name} ({qty} {unit})")
            print(f"    stored:   g={stored.get('grains')} v={stored.get('vegetables')} f={stored.get('fruits')} p={stored.get('protein')} d={stored.get('dairy')}")
            print(f"    computed: g={computed['grains']:.2f} v={computed['vegetables']:.2f} f={computed['fruits']:.2f} p={computed['protein']:.2f} d={computed['dairy']:.2f}")

            fixed += 1
            if not dry_run:
                pm_new = dict(pm) if isinstance(pm, dict) else {}
                fg_new = {k: round(v, 2) for k, v in computed.items()}
                pm_new["foodGroupServings"] = fg_new
                url = f"{PB_URL}/api/collections/ingredients/records/{ing.get('id')}"
                headers = {"Authorization": f"Bearer {get_token()}", "Content-Type": "application/json"}
                r = requests.patch(url, headers=headers, json={"parsingMetadata": pm_new})
                if r.status_code in (200, 201):
                    print(f"    -> patched")
                else:
                    print(f"    -> FAILED {r.status_code}: {r.text[:200]}")
            else:
                print(f"    -> would patch")

    print(f"\nChecked {checked} ingredients, {'would fix' if dry_run else 'fixed'} {fixed}")

if __name__ == "__main__":
    main()
