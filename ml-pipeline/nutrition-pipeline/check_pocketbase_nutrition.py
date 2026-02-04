#!/usr/bin/env python3
"""Check PocketBase: does ingredients schema include nutrition? What do we get back?"""

import requests
from dotenv import load_dotenv
load_dotenv()

from pb_client import get_token, PB_URL

def main():
    headers = {"Authorization": f"Bearer {get_token()}"}
    url = f"{PB_URL}/api/collections/ingredients/records?perPage=3&sort=-created"
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    data = r.json()
    items = data.get("items", [])
    
    print(f"PocketBase URL: {PB_URL}")
    print(f"Total ingredients in first page: {len(items)}")
    
    if not items:
        print("No ingredients found.")
        return
    
    ing = items[0]
    print(f"\nFirst ingredient keys: {list(ing.keys())}")
    print(f"Has 'nutrition' key: {'nutrition' in ing}")
    nut = ing.get("nutrition")
    print(f"nutrition value: {repr(nut)[:200]}...")
    if nut:
        if isinstance(nut, list):
            print(f"nutrition length: {len(nut)}")
            if nut:
                print(f"First nutrient sample: {nut[0]}")
        elif isinstance(nut, str):
            print(f"nutrition is string (length {len(nut)})")
    
    # Count how many have empty vs non-empty nutrition
    empty = sum(1 for i in items if not (isinstance(i.get("nutrition"), list) and len(i.get("nutrition", [])) > 0))
    print(f"\nOf {len(items)} sampled: {empty} with empty/missing nutrition")

if __name__ == "__main__":
    main()
