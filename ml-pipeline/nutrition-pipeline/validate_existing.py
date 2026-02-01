#!/usr/bin/env python3
"""Validate existing ingredients and flag/remove bad USDA matches."""
import os
import sys
from dotenv import load_dotenv
from pb_client import get_token, PB_URL, fetch_all_ingredients
from lookup_usda import validate_usda_match, extract_macros
import requests

load_dotenv()

def validate_existing_ingredients(dry_run=True, since_date=None):
    """
    Check all existing ingredients with USDA data and flag bad matches.
    
    Args:
        dry_run: If True, only report issues without deleting
        since_date: Only check ingredients after this date (ISO format)
    """
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    print("📦 Fetching all ingredients...")
    all_ingredients = fetch_all_ingredients()
    
    if since_date:
        all_ingredients = [
            ing for ing in all_ingredients
            if (ing.get("timestamp") or "")[:10] >= since_date
        ]
        print(f"📅 Filtered to {len(all_ingredients)} ingredients since {since_date}")
    
    print(f"🔍 Checking {len(all_ingredients)} ingredients...\n")
    
    bad_matches = []
    
    for ing in all_ingredients:
        # Only check ingredients with USDA data
        if ing.get("source") != "usda":
            continue
        
        nutrition = ing.get("nutrition", [])
        if not isinstance(nutrition, list) or not nutrition:
            continue
        
        macros = extract_macros(nutrition)
        ingredient_name = ing.get("name", "")
        matched_name = ing.get("rawUSDA", {}).get("name", "") or "unknown"
        
        # Validate
        is_valid, reason = validate_usda_match(ingredient_name, matched_name, macros)
        
        if not is_valid:
            bad_matches.append({
                "id": ing["id"],
                "name": ingredient_name,
                "matched": matched_name,
                "protein_per_100g": macros.get("protein", 0),
                "reason": reason,
                "timestamp": ing.get("timestamp", "")[:10]
            })
    
    if not bad_matches:
        print("✅ All USDA matches look valid!")
        return
    
    print(f"⚠️  Found {len(bad_matches)} suspicious matches:\n")
    
    for bad in bad_matches:
        print(f"  ❌ {bad['name']:30} → {bad['matched']:40}")
        print(f"     Protein: {bad['protein_per_100g']:.1f}g/100g | {bad['reason']}")
        print(f"     ID: {bad['id']} | Date: {bad['timestamp']}\n")
    
    if not dry_run:
        print(f"\n🗑️  Deleting {len(bad_matches)} bad matches...")
        deleted = 0
        for bad in bad_matches:
            url = f"{PB_URL}/api/collections/ingredients/records/{bad['id']}"
            resp = requests.delete(url, headers=headers)
            if resp.status_code == 204:
                deleted += 1
            else:
                print(f"  ⚠️  Failed to delete {bad['id']}: {resp.status_code}")
        
        print(f"✅ Deleted {deleted}/{len(bad_matches)} bad matches")
    else:
        print("\n💡 Run with --delete to remove these bad matches")
        print("   (They'll be re-parsed without USDA data)")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--delete", action="store_true", help="Actually delete bad matches")
    parser.add_argument("--since", help="Only check ingredients after this date (YYYY-MM-DD)")
    parser.add_argument("--last-week", action="store_true", help="Only check last week")
    args = parser.parse_args()
    
    since_date = None
    if args.last_week:
        from datetime import datetime, timedelta
        since_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    elif args.since:
        since_date = args.since
    
    validate_existing_ingredients(dry_run=not args.delete, since_date=since_date)
