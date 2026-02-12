#!/usr/bin/env python3
"""
One-time backdelete: Remove ingredient_corrections whose ingredient no longer exists
(orphaned records from before we cleared the log on clear). Also remove those
corrected names from the user's learned patterns (confusionPairs / foods) so they
won't be re-applied on next parse.

Option --unlearn-name: Find corrections (and profile entries) where the learned/corrected
name contains the given substring; delete those correction records and remove from
user profiles (e.g. to nuke "homemade banana bread with avocado oil..." so it
stops re-applying on parse).

Usage:
  python backdelete_orphan_corrections.py [--dry-run] [--limit N]
  python backdelete_orphan_corrections.py --dry-run   # report only, no deletes
  python backdelete_orphan_corrections.py --unlearn-name "banana bread" [--dry-run]   # nuke that learned name
"""

import argparse
from collections import defaultdict

import requests
from dotenv import load_dotenv
load_dotenv()

from pb_client import (
    get_token,
    PB_URL,
    fetch_records,
    fetch_ingredient_ids,
    remove_learned_patterns_for_names,
    update_user_food_profile,
)


def run_unlearn_by_name(substring: str, dry_run: bool):
    """Find corrections (and profile) where corrected/actual name contains substring; delete and unlearn."""
    substring_lower = (substring or "").strip().lower()
    if not substring_lower:
        print("   --unlearn-name requires a non-empty substring.")
        return
    # 1) Correction records
    print(f"📡 Loading ingredient_corrections (looking for corrected name containing {substring_lower!r})...")
    corrections = fetch_records("ingredient_corrections", per_page=500)
    matching = []
    for c in corrections:
        corr = c.get("userCorrection") or {}
        name = (corr.get("name") or "").strip()
        if substring_lower in name.lower():
            user_id = c.get("user") or ""
            if isinstance(user_id, dict):
                user_id = user_id.get("id") or ""
            matching.append({"id": c.get("id"), "user": user_id, "corrected_name": name})

    if matching:
        print(f"   Found {len(matching)} correction(s) with that name:")
        for m in matching[:15]:
            print(f"      - {m['corrected_name'][:60]!r} (user={m['user'][:8] if m['user'] else '?'}...)")
        if len(matching) > 15:
            print(f"      ... and {len(matching) - 15} more.")
    else:
        print(f"   No correction records with corrected name containing {substring_lower!r}.")

    # 2) User food profiles (confusionPairs / foods) — where the banana bread wording often lives
    print("📡 Loading user_food_profile (checking confusionPairs and foods for that name)...")
    profiles = fetch_records("user_food_profile", per_page=200)
    profile_updates = []
    for profile in profiles:
        user_id = profile.get("user") or ""
        if isinstance(user_id, dict):
            user_id = user_id.get("id") or ""
        confusions = profile.get("confusionPairs") or []
        foods = profile.get("foods") or []
        new_confusions = [c for c in confusions if substring_lower not in (c.get("actual") or "").lower()]
        new_foods = [f for f in foods if substring_lower not in (f.get("name") or "").lower()]
        if len(new_confusions) < len(confusions) or len(new_foods) < len(foods):
            removed_c = [c.get("actual") for c in confusions if c not in new_confusions]
            removed_f = [f.get("name") for f in foods if f not in new_foods]
            profile_updates.append({
                "profile": profile,
                "user_id": user_id,
                "confusions": new_confusions,
                "foods": new_foods,
                "removed": removed_c + removed_f,
            })

    if profile_updates:
        print(f"   Found {len(profile_updates)} profile(s) with that name in confusionPairs/foods:")
        for u in profile_updates[:5]:
            print(f"      - user={u['user_id'][:8] if u['user_id'] else '?'}... removed: {u['removed']}")
        if len(profile_updates) > 5:
            print(f"      ... and {len(profile_updates) - 5} more.")
    else:
        print("   No profile entries with that name.")

    if dry_run:
        print("   [DRY RUN] No changes made.")
        if matching:
            print("   Would delete the correction record(s) above and remove from profile(s).")
        if profile_updates:
            print("   Would update the profile(s) above to remove those entries.")
        return

    headers = {"Authorization": f"Bearer {get_token()}"}
    deleted = 0
    for m in matching:
        rid = m.get("id")
        if not rid:
            continue
        r = requests.delete(
            f"{PB_URL}/api/collections/ingredient_corrections/records/{rid}",
            headers=headers,
        )
        if r.status_code in (200, 204):
            deleted += 1
    if deleted:
        print(f"   Deleted {deleted} correction record(s).")

    by_user = defaultdict(set)
    for m in matching:
        if m.get("user") and m.get("corrected_name"):
            by_user[m["user"]].add(m["corrected_name"])
    for user_id, names in by_user.items():
        remove_learned_patterns_for_names(user_id, names)
    if by_user:
        print(f"   Updated learned patterns for {len(by_user)} user(s) (from corrections).")

    for u in profile_updates:
        update_user_food_profile(u["profile"]["id"], {"confusionPairs": u["confusions"], "foods": u["foods"]})
    if profile_updates:
        print(f"   Updated {len(profile_updates)} user profile(s) (removed confusionPairs/foods containing name).")
    print("✅ Done.")


def main():
    ap = argparse.ArgumentParser(description="Delete orphan correction records and unlearn those names.")
    ap.add_argument("--dry-run", action="store_true", help="Only report what would be deleted, do not delete.")
    ap.add_argument("--limit", type=int, default=None, help="Max number of correction records to process (default: all).")
    ap.add_argument("--unlearn-name", type=str, default=None, help="Unlearn by name: delete corrections and profile entries where corrected name contains this substring (e.g. 'banana bread').")
    args = ap.parse_args()

    if args.unlearn_name:
        run_unlearn_by_name(args.unlearn_name, args.dry_run)
        return

    print("📡 Loading all ingredient IDs...")
    existing_ids = fetch_ingredient_ids()
    print(f"   {len(existing_ids)} ingredients exist.")

    print("📡 Loading all ingredient_corrections...")
    corrections = fetch_records("ingredient_corrections", per_page=500)
    if args.limit is not None:
        corrections = corrections[: args.limit]
        print(f"   Limited to {args.limit} corrections.")
    print(f"   {len(corrections)} correction records to check.")

    orphans = []
    for c in corrections:
        ing_id = c.get("ingredientId")
        if not ing_id:
            continue
        if ing_id not in existing_ids:
            user_id = c.get("user") or ""
            if isinstance(user_id, dict):
                user_id = user_id.get("id") or ""
            corr = c.get("userCorrection") or {}
            name = (corr.get("name") or "").strip()
            orphans.append({"id": c.get("id"), "user": user_id, "corrected_name": name})

    if not orphans:
        print("✅ No orphan corrections found.")
        return

    print(f"🗑️ Found {len(orphans)} orphan correction(s) (ingredient no longer exists).")
    for o in orphans[:10]:
        print(f"   - {o['id']} user={o['user'][:8]}... name={o['corrected_name'][:50]!r}")
    if len(orphans) > 10:
        print(f"   ... and {len(orphans) - 10} more.")

    if args.dry_run:
        print("   [DRY RUN] No changes made.")
        return

    headers = {"Authorization": f"Bearer {get_token()}"}
    deleted = 0
    for o in orphans:
        rid = o["id"]
        if not rid:
            continue
        r = requests.delete(
            f"{PB_URL}/api/collections/ingredient_corrections/records/{rid}",
            headers=headers,
        )
        if r.status_code in (200, 204):
            deleted += 1
    print(f"   Deleted {deleted} orphan correction record(s).")

    # Group by user and remove learned patterns for the corrected names
    by_user = defaultdict(set)
    for o in orphans:
        if o.get("user") and o.get("corrected_name"):
            by_user[o["user"]].add(o["corrected_name"])

    for user_id, names in by_user.items():
        remove_learned_patterns_for_names(user_id, names)
    print(f"   Updated learned patterns for {len(by_user)} user(s).")
    print("✅ Done.")


if __name__ == "__main__":
    main()
