#!/usr/bin/env python3
"""
Archive and optionally clear existing ingredients from PocketBase.

Usage:
    # Export to JSON only (safe)
    python archive_ingredients.py
    
    # Export to JSON and delete from PocketBase
    python archive_ingredients.py --delete
"""

import json
import argparse
from datetime import datetime
from pb_client import fetch_all_ingredients, delete_all_ingredients

def archive_ingredients(delete_after=False):
    print("📦 Fetching all ingredients from PocketBase...")
    ingredients = fetch_all_ingredients()
    
    if not ingredients:
        print("✨ No ingredients found in PocketBase")
        return
    
    print(f"Found {len(ingredients)} ingredients")
    
    # Export to JSON with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"ingredients_backup_{timestamp}.json"
    
    with open(filename, "w") as f:
        json.dump(ingredients, f, indent=2, default=str)
    
    print(f"✅ Exported to {filename}")
    
    if delete_after:
        print(f"\n🗑️  Deleting {len(ingredients)} ingredients from PocketBase...")
        deleted = delete_all_ingredients()
        print(f"✅ Deleted {deleted} ingredients")
    else:
        print("\n💡 To also delete from PocketBase, run with --delete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Archive ingredients from PocketBase")
    parser.add_argument("--delete", action="store_true",
                        help="Delete ingredients from PocketBase after export")
    args = parser.parse_args()
    
    archive_ingredients(delete_after=args.delete)
