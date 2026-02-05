#!/usr/bin/env python3
"""
Review all ingredient corrections for a given date.
Shows: original parse, user correction, reason, conversation, what was learned, what was added to pantry.
Usage: python review_corrections_for_date.py 2026-02-04
"""
import os
import sys
from dotenv import load_dotenv
load_dotenv()

# Add parent for pb_client
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pb_client import (
    get_token,
    fetch_ingredients_by_meal_id,
    get_user_food_profile,
)
import requests
import urllib.parse

PB_URL = os.getenv("PB_URL") or "http://127.0.0.1:8090"


def fetch_meals_for_date(date_iso: str):
    """Fetch all meals on a given date (any user)."""
    date_iso = date_iso.strip()[:10]
    start_ts = f"{date_iso} 00:00:00.000Z"
    end_ts = f"{date_iso} 23:59:59.999Z"
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


def fetch_all_corrections_recent(limit: int = 200):
    """Fetch recent ingredient_corrections (we filter by ingredient ID in Python)."""
    headers = {"Authorization": f"Bearer {get_token()}"}
    url = f"{PB_URL}/api/collections/ingredient_corrections/records?sort=-created&perPage={limit}"
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        return []
    return r.json().get("items", [])


def main():
    date_iso = sys.argv[1] if len(sys.argv) > 1 else "2026-02-04"
    print(f"\n{'='*60}")
    print(f"REVIEW: Corrections for meals on {date_iso}")
    print(f"{'='*60}\n")

    meals = fetch_meals_for_date(date_iso)
    print(f"Found {len(meals)} meals on {date_iso}\n")

    all_ingredient_ids = []
    meal_by_ing = {}
    ing_by_id = {}
    for m in meals:
        ings = fetch_ingredients_by_meal_id(m.get("id"))
        for ing in ings:
            iid = ing.get("id")
            if iid:
                all_ingredient_ids.append(iid)
                meal_by_ing[iid] = m
                ing_by_id[iid] = ing

    if not all_ingredient_ids:
        print("No ingredients found for these meals.")
        return

    # Fetch all recent corrections, filter to our ingredient IDs
    all_corrections = fetch_all_corrections_recent()
    ingredient_id_set = set(all_ingredient_ids)
    corrections = [c for c in all_corrections if c.get("ingredientId") in ingredient_id_set]

    print(f"Found {len(corrections)} corrections\n")

    if not corrections:
        print("No corrections recorded for ingredients from these meals.")
        return

    for c in corrections:
        ing_id = c.get("ingredientId")
        meal = meal_by_ing.get(ing_id, {})
        ing = ing_by_id.get(ing_id, {})
        orig = c.get("originalParse", {})
        corr = c.get("userCorrection", {})
        ctx = c.get("context", {})
        # Fallback to context for old records that didn't persist top-level fields
        reason = c.get("correctionReason") or ctx.get("correctionReason") or "?"
        should_learn = c.get("shouldLearn") if "shouldLearn" in c else ctx.get("shouldLearn", False)
        conv = ctx.get("conversation", [])
        added_ing = ctx.get("addedIngredientId")  # for missing_item

        print("-" * 50)
        print(f"Meal: {meal.get('text', '(no text)')[:60]}...")
        print(f"Timestamp: {meal.get('timestamp', '?')}")
        print(f"Original: {orig.get('name', '?')} ({orig.get('quantity', '?')} {orig.get('unit', '?')})")
        print(f"Corrected to: {corr.get('name', orig.get('name'))} ({corr.get('quantity', orig.get('quantity'))} {corr.get('unit', orig.get('unit'))})")
        print(f"Reason: {reason}  |  shouldLearn: {should_learn}")
        if conv:
            print("Conversation:")
            for msg in conv[:8]:
                role = msg.get("role", "?")
                content = (msg.get("content") or "")[:200]
                print(f"  [{role}]: {content}")
            if len(conv) > 8:
                print(f"  ... ({len(conv)-8} more messages)")
        if added_ing:
            print(f"(Added new ingredient ID: {added_ing})")
        print()

    # Summary: what was learned / added to profile
    def _resolve_user_id(u):
        if not u:
            return None
        return u if isinstance(u, str) else u.get("id") or u.get("expand", {}).get("user", {}).get("id")

    user_ids = set()
    for m in meals:
        uid = _resolve_user_id(m.get("user"))
        if uid:
            user_ids.add(uid)
    # Resolve user IDs (PocketBase may return expanded)
    user_ids = {u for u in user_ids if u}

    print(f"\n{'='*60}")
    print("USER PROFILE (learned + pantry)")
    print(f"{'='*60}\n")

    for uid in user_ids:
        profile = get_user_food_profile(uid)
        if not profile:
            print(f"User {uid[:8]}...: No profile found")
            continue
        print(f"User {uid[:12]}...")
        print(f"  Common foods: {[f.get('name') for f in (profile.get('foods') or [])[:12]]}")
        confusions = profile.get("confusionPairs") or []
        if confusions:
            print(f"  Confusion pairs (learned):")
            for cp in confusions[:10]:
                print(f"    - {cp.get('mistaken')} → {cp.get('actual')} (count: {cp.get('count', 0)})")
        portion_prefs = profile.get("portionPreferences") or []
        if portion_prefs:
            print(f"  Portion preferences: {[(p.get('food'), p.get('quantity'), p.get('unit')) for p in portion_prefs[:6]]}")
        pantry = profile.get("pantry") or []
        if pantry:
            pantry = sorted(pantry, key=lambda x: x.get("lastUsed", ""), reverse=True)
            print(f"  Pantry (recent): {[p.get('name') for p in pantry[:12]]}")
        else:
            print(f"  Pantry: (empty or not yet populated)")
        print()


if __name__ == "__main__":
    main()
