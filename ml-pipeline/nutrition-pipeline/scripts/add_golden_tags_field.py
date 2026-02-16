"""
Add the optional `tags` (JSON) field to the existing golden_entries collection.
Run once if the collection was created before tags were added to the schema.

Uses PB_URL, PB_EMAIL, PB_PASSWORD from .env (admin auth).
See docs/golden-set-pocketbase-schema.md.
"""

import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

PB_URL = (os.getenv("PB_URL") or "http://127.0.0.1:8090").rstrip("/")
PB_EMAIL = os.getenv("PB_EMAIL")
PB_PASSWORD = os.getenv("PB_PASSWORD")


def get_admin_token():
    """Get admin auth token."""
    url = f"{PB_URL}/api/admins/auth-with-password"
    r = requests.post(url, json={"identity": PB_EMAIL, "password": PB_PASSWORD})
    if r.status_code == 200:
        return r.json()["token"]
    url = f"{PB_URL}/api/collections/_superusers/auth-with-password"
    r = requests.post(url, json={"identity": PB_EMAIL, "password": PB_PASSWORD})
    if r.status_code == 200:
        return r.json()["token"]
    raise Exception(f"Could not authenticate as admin: {r.status_code} {r.text[:400]}")


def main():
    print("Adding tags field to golden_entries (if missing)...")
    print(f"   PB_URL: {PB_URL}\n")

    if not PB_EMAIL or not PB_PASSWORD:
        print("❌ Set PB_EMAIL and PB_PASSWORD in .env")
        return 1

    try:
        token = get_admin_token()
    except Exception as e:
        print(f"❌ Auth failed: {e}")
        return 1

    headers = {"Authorization": f"Bearer {token}"}

    # GET collection by name
    r = requests.get(f"{PB_URL}/api/collections/golden_entries", headers=headers)
    if r.status_code != 200:
        print(f"❌ Could not load golden_entries: {r.status_code} {r.text[:400]}")
        return 1

    coll = r.json()
    coll_id = coll.get("id")
    fields = list(coll.get("fields") or [])

    if any(f.get("name") == "tags" for f in fields):
        print("✅ golden_entries already has a tags field. Nothing to do.")
        return 0

    # Append new field. PocketBase expects name, type, required; existing fields may have id.
    new_field = {"name": "tags", "type": "json", "required": False}
    fields.append(new_field)

    r = requests.patch(
        f"{PB_URL}/api/collections/{coll_id}",
        headers=headers,
        json={"fields": fields},
    )
    if r.status_code != 200:
        print(f"❌ Failed to update collection: {r.status_code} {r.text[:400]}")
        return 1

    print("✅ tags field added to golden_entries.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
