"""
Create the golden_entries collection in PocketBase for the parse-accuracy golden set.
Run once after adding the collection schema (see docs/how-to-improve-parse-accuracy.md step 0.1).

Uses PB_URL, PB_EMAIL, PB_PASSWORD from .env (admin auth).
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

PB_URL = os.getenv("PB_URL") or "http://127.0.0.1:8090"
PB_EMAIL = os.getenv("PB_EMAIL")
PB_PASSWORD = os.getenv("PB_PASSWORD")


def get_admin_token():
    """Get admin/superuser auth token."""
    url = f"{PB_URL}/api/collections/_superusers/auth-with-password"
    r = requests.post(url, json={"identity": PB_EMAIL, "password": PB_PASSWORD})
    if r.status_code == 200:
        return r.json()["token"]
    url = f"{PB_URL}/api/admins/auth-with-password"
    r = requests.post(url, json={"identity": PB_EMAIL, "password": PB_PASSWORD})
    if r.status_code == 200:
        return r.json()["token"]
    raise Exception(f"Could not authenticate as admin: {r.status_code} {r.text}")


def check_collection_exists(name: str, token: str) -> bool:
    """Check if a collection exists."""
    url = f"{PB_URL}/api/collections/{name}"
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    return r.status_code == 200


def main():
    print("Creating golden_entries collection...")
    print(f"   PB_URL: {PB_URL}\n")

    try:
        token = get_admin_token()
    except Exception as e:
        print(f"❌ Auth failed: {e}")
        return 1

    if check_collection_exists("golden_entries", token):
        print("✅ golden_entries already exists. Nothing to do.")
        return 0

    new_collection = {
        "name": "golden_entries",
        "type": "base",
        "fields": [
            {"name": "mealId", "type": "text", "required": False},
            {"name": "text", "type": "text", "required": True},
            {"name": "expected", "type": "json", "required": True},
            {"name": "category", "type": "text", "required": False},
            {"name": "addedAt", "type": "date", "required": False},
        ],
        "listRule": "@request.auth.id != ''",
        "viewRule": "@request.auth.id != ''",
        "createRule": "@request.auth.id != ''",
        "updateRule": "@request.auth.id != ''",
        "deleteRule": "@request.auth.id != ''",
    }

    r = requests.post(
        f"{PB_URL}/api/collections",
        headers={"Authorization": f"Bearer {token}"},
        json=new_collection,
    )
    if r.status_code != 200:
        print(f"❌ Failed to create collection: {r.status_code} {r.text[:400]}")
        return 1

    print("✅ golden_entries collection created.")
    print("\nYou can now use the Golden set builder (Regression → Load recent meals, Add selected to golden set).")
    return 0


if __name__ == "__main__":
    exit(main())
