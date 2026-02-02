"""
Setup script to add classification fields to PocketBase.
Run this ONCE to set up the schema for the classifier.

This is safer than migrations for testing - you can easily undo via Admin UI.
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
    # PocketBase 0.22+ uses _superusers collection
    url = f"{PB_URL}/api/collections/_superusers/auth-with-password"
    r = requests.post(url, json={"identity": PB_EMAIL, "password": PB_PASSWORD})
    if r.status_code == 200:
        return r.json()["token"]
    
    # Fall back to old admin endpoint
    url = f"{PB_URL}/api/admins/auth-with-password"
    r = requests.post(url, json={"identity": PB_EMAIL, "password": PB_PASSWORD})
    if r.status_code == 200:
        return r.json()["token"]
    
    raise Exception(f"Could not authenticate as admin: {r.status_code} {r.text}")


def check_collection_exists(name: str, token: str) -> bool:
    """Check if a collection exists."""
    url = f"{PB_URL}/api/collections/{name}"
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(url, headers=headers)
    return r.status_code == 200


def get_collection(name: str, token: str) -> dict:
    """Get collection details."""
    url = f"{PB_URL}/api/collections/{name}"
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        return r.json()
    return None


def check_field_exists(collection: str, field_name: str, token: str) -> bool:
    """Check if a field exists in a collection."""
    col = get_collection(collection, token)
    if not col:
        return False
    
    # PocketBase 0.22+ uses 'fields' instead of 'schema'
    fields = col.get("fields", col.get("schema", []))
    return any(f.get("name") == field_name for f in fields)


def dry_run():
    """Check what needs to be done without making changes."""
    print("🔍 DRY RUN - Checking current schema...\n")
    
    try:
        token = get_admin_token()
        print("✅ Connected to PocketBase\n")
    except Exception as e:
        print(f"❌ Could not connect to PocketBase: {e}")
        print(f"   URL: {PB_URL}")
        return False
    
    # Check meals collection
    print("📋 Checking 'meals' collection...")
    if check_collection_exists("meals", token):
        print("   ✅ meals collection exists")
        
        if check_field_exists("meals", "isFood", token):
            print("   ⚠️  isFood field already exists")
        else:
            print("   🔧 isFood field needs to be added")
        
        if check_field_exists("meals", "categories", token):
            print("   ⚠️  categories field already exists")
        else:
            print("   🔧 categories field needs to be added")
    else:
        print("   ❌ meals collection not found!")
        return False
    
    # Check non_food_logs collection
    print("\n📋 Checking 'non_food_logs' collection...")
    if check_collection_exists("non_food_logs", token):
        print("   ⚠️  non_food_logs collection already exists")
    else:
        print("   🔧 non_food_logs collection needs to be created")
    
    print("\n" + "="*50)
    print("To apply changes, run: python setup_classification_schema.py --apply")
    return True


def apply_changes():
    """Actually apply the schema changes."""
    print("🚀 APPLYING SCHEMA CHANGES...\n")
    
    try:
        token = get_admin_token()
        print("✅ Authenticated as admin\n")
    except Exception as e:
        print(f"❌ Could not connect: {e}")
        return False
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Step 1: Check if we need to add fields to meals
    print("Step 1: Updating 'meals' collection...")
    
    # Get current meals collection
    meals_data = get_collection("meals", token)
    if not meals_data:
        print(f"   ❌ Could not get meals collection")
        return False
    
    # PocketBase 0.22+ uses 'fields' instead of 'schema'
    fields = meals_data.get("fields", meals_data.get("schema", []))
    fields_updated = False
    
    # Check and add isFood
    if not any(f.get("name") == "isFood" for f in fields):
        fields.append({
            "name": "isFood",
            "type": "bool",
            "required": False
        })
        print("   + Adding isFood field")
        fields_updated = True
    else:
        print("   ✓ isFood already exists")
    
    # Check and add categories
    if not any(f.get("name") == "categories" for f in fields):
        fields.append({
            "name": "categories",
            "type": "json",
            "required": False
        })
        print("   + Adding categories field")
        fields_updated = True
    else:
        print("   ✓ categories already exists")
    
    # Update meals collection if needed
    if fields_updated:
        url = f"{PB_URL}/api/collections/meals"
        # Use whichever key the collection uses
        if "fields" in meals_data:
            meals_data["fields"] = fields
        else:
            meals_data["schema"] = fields
        
        r = requests.patch(url, headers=headers, json=meals_data)
        if r.status_code == 200:
            print("   ✅ meals collection updated!")
        else:
            print(f"   ❌ Failed to update meals: {r.status_code} {r.text[:200]}")
            return False
    else:
        print("   ✓ No updates needed")
    
    # Step 2: Create non_food_logs collection
    print("\nStep 2: Creating 'non_food_logs' collection...")
    
    if check_collection_exists("non_food_logs", token):
        print("   ✓ non_food_logs already exists, skipping")
    else:
        # Get users collection ID
        users_col = get_collection("users", token)
        users_id = users_col["id"] if users_col else "_pb_users_auth_"
        
        new_collection = {
            "name": "non_food_logs",
            "type": "base",
            "fields": [
                {"name": "mealId", "type": "relation", "required": False, "options": {"collectionId": meals_data["id"], "maxSelect": 1}},
                {"name": "user", "type": "relation", "required": True, "options": {"collectionId": users_id, "maxSelect": 1}},
                {"name": "category", "type": "text", "required": True},
                {"name": "content", "type": "text", "required": False},
                {"name": "timestamp", "type": "date", "required": False},
                {"name": "metadata", "type": "json", "required": False}
            ],
            "listRule": "@request.auth.id != '' && user = @request.auth.id",
            "viewRule": "@request.auth.id != '' && user = @request.auth.id",
            "createRule": "@request.auth.id != ''",
            "updateRule": "@request.auth.id != '' && user = @request.auth.id",
            "deleteRule": "@request.auth.id != '' && user = @request.auth.id"
        }
        
        url = f"{PB_URL}/api/collections"
        r = requests.post(url, headers=headers, json=new_collection)
        if r.status_code == 200:
            print("   ✅ non_food_logs collection created!")
        else:
            print(f"   ❌ Failed to create non_food_logs: {r.status_code} {r.text[:300]}")
            return False
    
    print("\n" + "="*50)
    print("✅ Schema setup complete!")
    print("\nYou can now run the classifier:")
    print("   python log_classifier.py")
    return True


if __name__ == "__main__":
    import sys
    
    if "--apply" in sys.argv:
        apply_changes()
    else:
        dry_run()
