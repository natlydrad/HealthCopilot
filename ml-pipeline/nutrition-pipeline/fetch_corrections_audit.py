#!/usr/bin/env python3
"""
Fetch ingredient_corrections and user_food_profile from PocketBase for audit.
Outputs chicken wings related data and all learned patterns to analyze flaws.
"""
import os
import json
from dotenv import load_dotenv

load_dotenv()

# Use same PB as parse_api (Render deployment)
PB_URL = os.getenv("PB_URL", "https://pocketbase-1j2x.onrender.com")
PB_EMAIL = os.getenv("PB_EMAIL")
PB_PASSWORD = os.getenv("PB_PASSWORD")

def get_token():
    import requests
    url = f"{PB_URL}/api/collections/users/auth-with-password"
    r = requests.post(url, json={"identity": PB_EMAIL, "password": PB_PASSWORD})
    r.raise_for_status()
    return r.json()["token"]

def fetch_json(path, token, params=None):
    import requests
    url = f"{PB_URL}{path}"
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(url, headers=headers, params=params or {})
    r.raise_for_status()
    return r.json()

def main():
    if not PB_EMAIL or not PB_PASSWORD:
        print("❌ Set PB_EMAIL and PB_PASSWORD in .env (nutrition-pipeline folder)")
        print("   Use the same user account that made the chicken wings corrections.")
        return

    print(f"🔗 Connecting to {PB_URL}...")
    token = get_token()
    print("✅ Authenticated\n")

    # 1. Fetch all ingredient corrections
    print("=" * 60)
    print("INGREDIENT CORRECTIONS (all, sorted by newest)")
    print("=" * 60)
    data = fetch_json("/api/collections/ingredient_corrections/records", token, {"perPage": 200, "sort": "-created"})
    corrections = data.get("items", [])

    if not corrections:
        print("(No corrections found)\n")
    else:
        # Filter chicken/wing related
        chicken_corrections = []
        for c in corrections:
            orig = c.get("originalParse", {}) or {}
            corr = c.get("userCorrection", {}) or {}
            orig_name = (orig.get("name") or "").lower()
            corr_name = (corr.get("name") or "").lower()
            if "chicken" in orig_name or "wing" in orig_name or "chicken" in corr_name or "wing" in corr_name:
                chicken_corrections.append(c)

        if chicken_corrections:
            print(f"\n🍗 CHICKEN/WING RELATED ({len(chicken_corrections)}):\n")
            for c in chicken_corrections:
                orig = c.get("originalParse", {}) or {}
                corr = c.get("userCorrection", {}) or {}
                ctx = c.get("context") or {}
                print(f"  {c.get('created', '')[:19]}")
                print(f"    original: {orig.get('name')} {orig.get('quantity')} {orig.get('unit')}")
                print(f"    corrected: {corr.get('name')} {corr.get('quantity')} {corr.get('unit')}")
                print(f"    type: {c.get('correctionType')}")
                if ctx.get("learned"):
                    print(f"    learned: {ctx.get('learned')}")
                if ctx.get("conversation"):
                    print(f"    conversation snippets: {[m.get('content','')[:50] for m in (ctx.get('conversation') or [])[:3]]}")
                print()

        print(f"\nALL CORRECTIONS (first 30):\n")
        for c in corrections[:30]:
            orig = c.get("originalParse", {}) or {}
            corr = c.get("userCorrection", {}) or {}
            print(f"  \"{orig.get('name')}\" → \"{corr.get('name')}\"  |  {orig.get('quantity')}{orig.get('unit')} → {corr.get('quantity')}{corr.get('unit')}  |  {c.get('created','')[:10]}")

    # 2. Fetch user_food_profile (confusion pairs, common foods)
    print("\n" + "=" * 60)
    print("USER FOOD PROFILE (learned confusions & foods)")
    print("=" * 60)
    try:
        # List all profiles (admin would be needed for filter; try direct list)
        data = fetch_json("/api/collections/user_food_profile/records", token, {"perPage": 10})
        profiles = data.get("items", [])
        if not profiles:
            print("(No user_food_profile records - migration may not have run on server)")
        else:
            for p in profiles:
                confusions = p.get("confusionPairs") or []
                foods = p.get("foods") or []
                print(f"\nProfile for user {p.get('user', '?')}:")
                print(f"  confusionPairs: {len(confusions)}")
                for cp in confusions[:20]:
                    print(f"    \"{cp.get('mistaken')}\" → \"{cp.get('actual')}\" (count={cp.get('count')})")
                print(f"  foods: {len(foods)}")
                for f in foods[:15]:
                    print(f"    {f.get('name')} (freq={f.get('frequency')})")
    except Exception as e:
        print(f"(Could not fetch user_food_profile: {e})")

    # 3. Summary for Learning Panel logic
    print("\n" + "=" * 60)
    print("LEARNING PANEL PATTERNS (as getLearnedPatterns would compute)")
    print("=" * 60)
    patterns = {}
    for c in corrections:
        orig = (c.get("originalParse") or {}).get("name")
        corr = (c.get("userCorrection") or {}).get("name")
        if orig and corr and orig.lower() != corr.lower():
            key = f"{orig.lower()}→{corr}"
            if key not in patterns:
                patterns[key] = {"original": orig.lower(), "learned": corr, "count": 0}
            patterns[key]["count"] += 1
    for k, v in sorted(patterns.items(), key=lambda x: -x[1]["count"]):
        status = "confident" if v["count"] >= 3 else "learning"
        print(f"  \"{v['original']}\" → \"{v['learned']}\"  ({v['count']}x) [{status}]")

if __name__ == "__main__":
    main()
