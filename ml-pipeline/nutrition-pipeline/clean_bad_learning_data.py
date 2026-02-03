#!/usr/bin/env python3
"""
Remove bad entries from user_food_profile:
- confusionPairs where mistaken/actual look like units (e.g. "6 pieces" -> "2 tbsp")
- foods that are units/quantities (e.g. "2 tbsp")
Run: python clean_bad_learning_data.py [--dry-run]
"""
import os
import argparse
from dotenv import load_dotenv

load_dotenv()
import requests

PB_URL = os.getenv("PB_URL", "https://pocketbase-1j2x.onrender.com")
PB_EMAIL = os.getenv("PB_EMAIL")
PB_PASSWORD = os.getenv("PB_PASSWORD")

UNIT_WORDS = {"piece", "pieces", "oz", "gram", "grams", "cup", "cups",
              "tbsp", "tablespoon", "tablespoons", "tsp", "teaspoon",
              "serving", "servings", "slice", "slices", "lb", "pound", "mg", "ml"}


def looks_like_unit(s: str) -> bool:
    if not s or not isinstance(s, str):
        return True
    low = s.lower().strip()
    parts = [p for p in low.split() if p]
    if len(parts) <= 2 and parts:
        first = parts[0].replace(".", "")
        if first.isdigit() and len(parts) == 2 and parts[1] in UNIT_WORDS:
            return True
        if len(parts) == 1 and parts[0] in UNIT_WORDS:
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Only print what would be removed")
    args = ap.parse_args()

    if not PB_EMAIL or not PB_PASSWORD:
        print("Set PB_EMAIL and PB_PASSWORD in .env")
        return

    r = requests.post(
        f"{PB_URL}/api/collections/users/auth-with-password",
        json={"identity": PB_EMAIL, "password": PB_PASSWORD}
    )
    r.raise_for_status()
    token = r.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    data = requests.get(
        f"{PB_URL}/api/collections/user_food_profile/records",
        headers=headers,
        params={"perPage": 50}
    ).json()
    profiles = data.get("items", [])

    for p in profiles:
        pid = p.get("id")
        user = p.get("user")
        changed = False
        confusions = (p.get("confusionPairs") or [])[:]
        foods = (p.get("foods") or [])[:]

        # Remove bad confusion pairs
        new_confusions = []
        for c in confusions:
            m, a = c.get("mistaken", ""), c.get("actual", "")
            if looks_like_unit(m) or looks_like_unit(a):
                print(f"  Remove confusion: '{m}' -> '{a}'")
                changed = True
            else:
                new_confusions.append(c)

        # Remove bad foods
        new_foods = []
        for f in foods:
            name = f.get("name", "")
            if looks_like_unit(name):
                print(f"  Remove food: '{name}'")
                changed = True
            else:
                new_foods.append(f)

        if changed:
            if not args.dry_run:
                patch = {}
                if confusions != new_confusions:
                    patch["confusionPairs"] = new_confusions
                if foods != new_foods:
                    patch["foods"] = new_foods
                if patch:
                    resp = requests.patch(
                        f"{PB_URL}/api/collections/user_food_profile/records/{pid}",
                        headers=headers,
                        json=patch
                    )
                    resp.raise_for_status()
                    print(f"  Updated profile {pid}")
            else:
                print(f"  [dry-run] Would update profile {pid}")

    if args.dry_run:
        print("\nRe-run without --dry-run to apply changes.")


if __name__ == "__main__":
    main()
