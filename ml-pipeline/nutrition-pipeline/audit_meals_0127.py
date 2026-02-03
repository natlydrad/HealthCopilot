#!/usr/bin/env python3
"""
Audit meals from 01-27: ingredients, corrections, contexts, and learned patterns.
Validates flow: correction → context → learned → user_food_profile.

Uses LOCAL date for filtering (matches Dashboard). Pass --tz America/Los_Angeles or set TZ env.
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

def local_date_to_utc_range(date_ymd: str, tz_name: str):
    """Convert local YYYY-MM-DD to UTC start/end for PocketBase filter."""
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo
    tz = ZoneInfo(tz_name)
    start_local = datetime(int(date_ymd[:4]), int(date_ymd[5:7]), int(date_ymd[8:10]), 0, 0, 0, tzinfo=tz)
    end_local = datetime(int(date_ymd[:4]), int(date_ymd[5:7]), int(date_ymd[8:10]), 23, 59, 59, 999000, tzinfo=tz)
    start_utc = start_local.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M:%S.%f")[:23] + "Z"
    end_utc = end_local.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M:%S.%f")[:23] + "Z"
    return start_utc, end_utc

def utc_to_local(ts_str: str, tz_name: str) -> str:
    """Format UTC timestamp as local time for display."""
    if not ts_str:
        return "?"
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo
    ts = ts_str.replace(" ", "T").replace("Z", "+00:00")
    if "+" not in ts and "Z" not in ts_str:
        ts += "+00:00"
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt.astimezone(ZoneInfo(tz_name)).strftime("%Y-%m-%d %H:%M")

def main():
    if not PB_EMAIL or not PB_PASSWORD:
        print("❌ Set PB_EMAIL and PB_PASSWORD in .env")
        return

    tz = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--tz=")), None) or os.getenv("TZ", "America/New_York")
    date = next((a for a in sys.argv if len(a) == 10 and a[4] == "-" and a[7] == "-" and a.replace("-", "").isdigit()), "2026-01-27")

    print("🔗 Connecting to PocketBase...")
    token = get_token()
    print("✅ Authenticated\n")

    # 1. Meals on 01-27 in LOCAL time (convert to UTC range for filter)
    start_utc, end_utc = local_date_to_utc_range(date, tz)
    filt = urllib.parse.quote(f'timestamp >= "{start_utc}" && timestamp <= "{end_utc}"')
    meals_data = fetch(f"/api/collections/meals/records?filter={filt}&perPage=50&sort=timestamp", token)
    meals = meals_data.get("items", [])

    if not meals:
        print(f"⚠️ No meals found for {date} ({tz}). Try --tz=Your/Timezone or different date.")

    print("=" * 70)
    print(f"MEALS ON {date} ({tz}) — {len(meals)} found")
    print("=" * 70)

    meal_ids = {m["id"] for m in meals}
    all_ingredients = []
    for mid in meal_ids:
        ing_filt = urllib.parse.quote(f"mealId='{mid}'")
        ing_data = fetch(f"/api/collections/ingredients/records?filter={ing_filt}&perPage=200", token)
        ings = ing_data.get("items", [])
        all_ingredients.extend(ings)

    ing_ids = {i["id"] for i in all_ingredients}
    print(f"Total ingredients across meals: {len(all_ingredients)}\n")

    # 2. Corrections for these ingredients (fetch all corrections, filter)
    corr_data = fetch("/api/collections/ingredient_corrections/records", token, {"perPage": 300, "sort": "-created"})
    all_corrections = corr_data.get("items", [])
    corrections = [c for c in all_corrections if c.get("ingredientId") in ing_ids]

    print(f"Corrections for these meals' ingredients: {len(corrections)}\n")

    # 3. user_food_profile (learned confusions & foods)
    try:
        profile_data = fetch("/api/collections/user_food_profile/records", token, {"perPage": 5})
        profiles = profile_data.get("items", [])
    except Exception as e:
        profiles = []
        print(f"⚠️ Could not fetch user_food_profile: {e}\n")

    # --- OUTPUT ---
    for m in meals:
        ts = utc_to_local(m.get("timestamp"), tz) if m.get("timestamp") else "?"
        text = (m.get("text") or "(image only)")[:60]
        print(f"\n📅 {ts} | {text}")
        print("-" * 60)

        # Ingredients for this meal
        ings = [i for i in all_ingredients if i.get("mealId") == m["id"]]
        for ing in ings:
            name = ing.get("name", "?")
            qty = ing.get("quantity", "")
            unit = ing.get("unit", "")
            src = ing.get("source", "?")
            print(f"   🥗 {name} ({qty} {unit}) [source={src}]")

        # Corrections for these ingredients
        for c in corrections:
            # ingredientId might be expanded to object
            c_ing_id = c.get("ingredientId")
            if isinstance(c_ing_id, dict):
                c_ing_id = c_ing_id.get("id")
            if c_ing_id not in {i["id"] for i in ings}:
                continue

            orig = c.get("originalParse") or {}
            corr = c.get("userCorrection") or {}
            ctx = c.get("context") or {}
            ctype = c.get("correctionType", "?")

            print(f"\n   📝 CORRECTION:")
            print(f"      original: {orig.get('name')} ({orig.get('quantity')} {orig.get('unit')})")
            print(f"      corrected: {corr.get('name')} ({corr.get('quantity')} {corr.get('unit')})")
            print(f"      type: {ctype}")

            # Context (full)
            learned = ctx.get("learned")
            via = ctx.get("via")
            conv = ctx.get("conversation") or []
            meal_ctx = ctx.get("mealContext") or ctx.get("mealText")

            if learned:
                print(f"      learned: {json.dumps(learned, default=str)[:400]}")
            if via:
                print(f"      via: {via}")
            if meal_ctx:
                print(f"      mealContext: {(str(meal_ctx))[:80]}")
            if conv:
                print(f"      conversation ({len(conv)} msgs):")
                for msg in conv[:8]:
                    role = msg.get("role", "?")
                    content = (msg.get("content") or "")[:150]
                    print(f"         [{role}]: {content}")

    # 4. Learned patterns (user_food_profile)
    print("\n" + "=" * 70)
    print("LEARNED PATTERNS (user_food_profile)")
    print("=" * 70)
    for p in profiles:
        confusions = p.get("confusionPairs") or []
        foods = p.get("foods") or []
        print(f"\n  confusionPairs ({len(confusions)}):")
        for cp in confusions:
            print(f"    \"{cp.get('mistaken')}\" → \"{cp.get('actual')}\" (count={cp.get('count', 1)})")
        print(f"  common foods ({len(foods)}):")
        for f in foods[:20]:
            print(f"    {f.get('name')} (freq={f.get('frequency', 1)})")

    # 5. Flow validation
    print("\n" + "=" * 70)
    print("FLOW VALIDATION")
    print("=" * 70)
    print("""
Expected flow:
1. User corrects ingredient → correction record created with context (conversation, learned, via)
2. save_correction/add_learned_confusion adds to user_food_profile (confusionPairs or foods)
3. Learning Panel shows patterns from corrections (excluding add_missing)
4. Future parses use confusionPairs to suggest corrections

Checks:
""")
    # Check: corrections with learned in context should have matching confusionPair or food
    for c in corrections:
        ctx = c.get("context") or {}
        learned = ctx.get("learned")
        if not learned:
            continue
        orig = (c.get("originalParse") or {}).get("name", "")
        corr = (c.get("userCorrection") or {}).get("name", "")
        found = False
        for p in profiles:
            for cp in (p.get("confusionPairs") or []):
                if (cp.get("mistaken") or "").lower() == (orig or "").lower() and (cp.get("actual") or "") == (corr or ""):
                    found = True
                    break
            for f in (p.get("foods") or []):
                if (f.get("name") or "") == (corr or ""):
                    found = True
                    break
        status = "✅" if found else "⚠️ (not in profile?)"
        print(f"  Correction \"{orig}\" → \"{corr}\" | learned={bool(learned)} | in profile: {status}")

if __name__ == "__main__":
    main()
