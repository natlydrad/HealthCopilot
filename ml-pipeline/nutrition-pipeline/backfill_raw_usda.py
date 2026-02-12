#!/usr/bin/env python3
"""Backfill rawUSDA for USDA ingredients that have usdaCode but empty rawUSDA."""
import argparse
import requests
from dotenv import load_dotenv
from pb_client import get_token, PB_URL, fetch_all_ingredients
from lookup_usda import usda_lookup_by_fdc_id, usda_lookup

load_dotenv()


def patch_raw_usda(ing_id: str, raw_usda: dict) -> bool:
    """PATCH ingredient with rawUSDA."""
    headers = {"Authorization": f"Bearer {get_token()}"}
    url = f"{PB_URL}/api/collections/ingredients/records/{ing_id}"
    r = requests.patch(url, headers=headers, json={"rawUSDA": raw_usda})
    return r.status_code in (200, 204)


def backfill_raw_usda(dry_run=True, limit=None):
    print("📦 Backfilling rawUSDA for USDA ingredients with usdaCode but empty rawUSDA...")
    print(f"   PB_URL: {PB_URL}\n")

    all_ings = fetch_all_ingredients()
    # Only USDA ingredients with usdaCode
    candidates = [
        ing for ing in all_ings
        if ing.get("source") == "usda"
        and ing.get("usdaCode")
    ]
    # Filter to those with empty rawUSDA (no name = not populated)
    to_fill = [
        ing for ing in candidates
        if not (ing.get("rawUSDA") or {}).get("name")
    ]

    if limit:
        to_fill = to_fill[:limit]
        print(f"   Limit: {limit}")

    print(f"   USDA ingredients with usdaCode: {len(candidates)}")
    print(f"   Need rawUSDA backfill: {len(to_fill)}\n")

    updated = 0
    skipped = 0
    errors = 0

    for i, ing in enumerate(to_fill):
        name = ing.get("name", "?")
        usda_code = ing.get("usdaCode")
        print(f"[{i + 1}/{len(to_fill)}] {name} (fdcId: {usda_code})")

        usda = usda_lookup_by_fdc_id(usda_code)
        if not usda:
            # Fallback: search by name for a valid USDA match (the stored fdcId may have zero-data)
            usda = usda_lookup(name)
            if not usda:
                print(f"   ⏭️ USDA lookup by ID and by name both failed")
                skipped += 1
                continue
            print(f"   📋 FDC {usda_code} had zero-data; used search match: {usda.get('name', '?')}")

        raw_usda = {
            "usdaCode": usda.get("usdaCode"),
            "name": usda.get("name"),
            "nutrition": usda.get("nutrition", []),
            "serving_size_g": usda.get("serving_size_g"),
        }

        if dry_run:
            print(f"   [DRY RUN] Would set rawUSDA.name = {raw_usda.get('name', '?')}")
            updated += 1
            continue

        if patch_raw_usda(ing["id"], raw_usda):
            print(f"   ✅ rawUSDA.name = {raw_usda.get('name', '?')}")
            updated += 1
        else:
            print(f"   ❌ PATCH failed")
            errors += 1

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Done! Updated {updated}, skipped {skipped}, errors {errors}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill rawUSDA for USDA ingredients")
    parser.add_argument("--no-dry-run", action="store_true", help="Actually patch (default is dry-run)")
    parser.add_argument("--limit", type=int, help="Max ingredients to process")
    args = parser.parse_args()
    backfill_raw_usda(dry_run=not args.no_dry_run, limit=args.limit)
