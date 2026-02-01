#!/usr/bin/env python3
"""
Clean up duplicate records in PocketBase.
For each (user, timestamp) group with multiple records, keeps the first and deletes the rest.
"""

import sys
import os
from pathlib import Path
from collections import defaultdict
import time

# Load .env from project root BEFORE importing pb_client
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path, override=True)

print(f"🔗 Using PocketBase at: {os.getenv('PB_URL')}")

sys.path.insert(0, "nutrition-pipeline")

from pb_client import fetch_records, get_token
import requests

PB_URL = os.getenv("PB_URL")


def delete_record(collection: str, record_id: str):
    """Delete a single record from PocketBase."""
    url = f"{PB_URL}/api/collections/{collection}/records/{record_id}"
    headers = {"Authorization": f"Bearer {get_token()}"}
    r = requests.delete(url, headers=headers)
    return r.status_code in [200, 204, 404]  # 404 = already deleted, treat as success


def cleanup_collection(name: str, timestamp_field: str = "timestamp", dry_run: bool = False):
    """
    Deduplicate a collection by (user, timestamp).
    Keeps the first record (by 'created' timestamp) in each duplicate group.
    """
    print(f"\n{'='*50}")
    print(f"Cleaning: {name}")
    print('='*50)
    
    records = fetch_records(name)
    
    # Group by (user, timestamp)
    groups = defaultdict(list)
    for r in records:
        user = r.get("user", "unknown")
        ts = r.get(timestamp_field, "unknown")
        key = (user, ts)
        groups[key].append(r)
    
    # Find duplicates (groups with more than 1 record)
    duplicates = {k: v for k, v in groups.items() if len(v) > 1}
    
    if not duplicates:
        print(f"✅ No duplicates found in {name}")
        return 0
    
    # Collect IDs to delete (keep the first/oldest by 'created')
    to_delete = []
    for key, recs in duplicates.items():
        # Sort by 'created' timestamp, keep the first
        sorted_recs = sorted(recs, key=lambda r: r.get("created", ""))
        keep = sorted_recs[0]
        delete = sorted_recs[1:]
        to_delete.extend(delete)
    
    print(f"📊 Found {len(duplicates)} duplicate groups")
    print(f"🗑️  Will delete {len(to_delete)} records (keeping 1 per group)")
    
    if dry_run:
        print("🔍 DRY RUN - no records will be deleted")
        return len(to_delete)
    
    # Delete in batches with progress
    deleted = 0
    errors = 0
    batch_size = 50
    
    for i, rec in enumerate(to_delete):
        try:
            success = delete_record(name, rec["id"])
            if success:
                deleted += 1
            else:
                errors += 1
        except Exception as e:
            errors += 1
            print(f"⚠️  Error deleting {rec['id']}: {e}")
        
        # Progress every batch_size records
        if (i + 1) % batch_size == 0:
            print(f"   Progress: {i + 1}/{len(to_delete)} ({deleted} deleted, {errors} errors)")
            time.sleep(0.1)  # Brief pause to avoid overwhelming the server
    
    print(f"✅ Deleted {deleted}/{len(to_delete)} records ({errors} errors)")
    return deleted


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Clean up duplicate records in PocketBase")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting")
    parser.add_argument("--collection", type=str, help="Only clean specific collection (glucose, steps)")
    args = parser.parse_args()
    
    print("🧹 PocketBase Duplicate Cleanup")
    print("="*50)
    
    if args.dry_run:
        print("🔍 DRY RUN MODE - no records will be deleted\n")
    
    collections = [
        ("glucose", "timestamp"),
        ("steps", "timestamp"),
    ]
    
    # Filter to specific collection if requested
    if args.collection:
        collections = [(c, f) for c, f in collections if c == args.collection]
        if not collections:
            print(f"❌ Unknown collection: {args.collection}")
            return
    
    total_deleted = 0
    
    for coll, field in collections:
        try:
            deleted = cleanup_collection(coll, field, dry_run=args.dry_run)
            total_deleted += deleted
        except Exception as e:
            print(f"⚠️  Could not clean {coll}: {e}")
    
    print("\n" + "="*50)
    print("📋 CLEANUP COMPLETE")
    print("="*50)
    
    if args.dry_run:
        print(f"   Would delete: {total_deleted} records")
        print("\n   Run without --dry-run to actually delete.")
    else:
        print(f"   Total deleted: {total_deleted} records")


if __name__ == "__main__":
    main()
