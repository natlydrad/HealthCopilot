#!/usr/bin/env python3
"""
Audit PocketBase collections for duplicate entries.
Checks glucose and steps for records with same (user, timestamp).
"""

import sys
import os
from pathlib import Path

# Load .env from project root BEFORE importing pb_client
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path, override=True)

print(f"🔗 Using PocketBase at: {os.getenv('PB_URL')}")

sys.path.insert(0, "nutrition-pipeline")

# Now import pb_client (after env is loaded)
from pb_client import fetch_records
from collections import defaultdict

def audit_collection(name: str, timestamp_field: str = "timestamp"):
    """
    Fetch all records and find duplicates by (user, timestamp).
    Returns: (total_records, duplicate_groups, duplicate_record_count)
    """
    print(f"\n{'='*50}")
    print(f"Auditing: {name}")
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
    
    total = len(records)
    unique = len(groups)
    dupe_groups = len(duplicates)
    dupe_records = sum(len(v) for v in duplicates.values())
    extra_records = sum(len(v) - 1 for v in duplicates.values())  # records that should be deleted
    
    print(f"\n📊 Results for {name}:")
    print(f"   Total records:     {total:,}")
    print(f"   Unique (user,ts):  {unique:,}")
    print(f"   Duplicate groups:  {dupe_groups:,}")
    print(f"   Records in dupes:  {dupe_records:,}")
    print(f"   Extra to delete:   {extra_records:,}")
    
    if dupe_groups > 0:
        print(f"\n   Sample duplicates:")
        for i, (key, recs) in enumerate(list(duplicates.items())[:5]):
            user, ts = key
            print(f"     [{i+1}] user={user[:8]}... ts={ts} → {len(recs)} copies")
            for r in recs[:3]:
                val = r.get("value_mgdl") or r.get("steps") or "?"
                print(f"         id={r['id']} value={val}")
    
    return {
        "collection": name,
        "total": total,
        "unique": unique,
        "duplicate_groups": dupe_groups,
        "extra_to_delete": extra_records,
        "duplicates": duplicates
    }


def main():
    print("🔍 PocketBase Duplicate Audit")
    print("="*50)
    
    results = []
    
    # Audit glucose
    results.append(audit_collection("glucose", "timestamp"))
    
    # Audit steps
    results.append(audit_collection("steps", "timestamp"))
    
    # Audit daily collections (by date field)
    for coll in ["sleep_daily", "energy_daily", "heart_daily", "body_daily"]:
        try:
            results.append(audit_collection(coll, "date"))
        except Exception as e:
            print(f"⚠️  Could not audit {coll}: {e}")
    
    # Summary
    print("\n" + "="*50)
    print("📋 SUMMARY")
    print("="*50)
    
    total_extra = 0
    for r in results:
        extra = r["extra_to_delete"]
        total_extra += extra
        status = "✅" if extra == 0 else "⚠️ "
        print(f"   {status} {r['collection']}: {r['total']:,} records, {extra:,} duplicates to clean")
    
    print(f"\n   Total duplicate records to delete: {total_extra:,}")
    
    if total_extra > 0:
        print("\n💡 Run `python cleanup_duplicates.py` to remove duplicates.")


if __name__ == "__main__":
    main()
