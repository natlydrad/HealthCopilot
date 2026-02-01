import os, requests
from dotenv import load_dotenv
load_dotenv()


PB_URL = os.getenv("PB_URL") or "http://127.0.0.1:8090"
PB_EMAIL= os.getenv("PB_EMAIL")      # service user email
PB_PASSWORD = os.getenv("PB_PASSWORD")      # service user password

# Keep token cached in memory
_cached_token = None

def get_token():
    global _cached_token
    if _cached_token:
        return _cached_token
    
    # Log in service user
    url = f"{PB_URL}/api/collections/users/auth-with-password"
    r = requests.post(url, json={"identity":PB_EMAIL, "password": PB_PASSWORD})
    r.raise_for_status()
    data = r.json()
    _cached_token = data["token"]
    return _cached_token

def fetch_meals():
    headers = {"Authorization": f"Bearer {get_token()}"}
    all_items = []
    page = 1
    per_page = 200  # grab up to 200 at a time

    while True:
        url = f"{PB_URL}/api/collections/meals/records?page={page}&perPage={per_page}&sort=-created"
        print(f"🔄 Fetching meals page {page}...")
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        items = data.get("items", [])
        all_items.extend(items)
        if len(items) < per_page:
            break
        page += 1

    print(f"✅ Retrieved {len(all_items)} meals from PocketBase")
    return all_items


def insert_ingredient(ingredient):
    url = f"{PB_URL}/api/collections/ingredients/records"
    headers = {"Authorization": f"Bearer {get_token()}"}
    r = requests.post(url, headers=headers, json=ingredient)
    r.raise_for_status()
    return r.json()

def fetch_records(collection_name, per_page=200):
    """Generic fetch helper for any PocketBase collection."""
    headers = {"Authorization": f"Bearer {get_token()}"}
    all_items = []
    page = 1

    while True:
        url = f"{PB_URL}/api/collections/{collection_name}/records?page={page}&perPage={per_page}&sort=-created"
        print(f"📡 Fetching {collection_name} page {page}...")
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        items = data.get("items", [])
        all_items.extend(items)
        if len(items) < per_page:
            break
        page += 1

    print(f"✅ Retrieved {len(all_items)} records from {collection_name}")
    return all_items


def get_parsed_meal_ids():
    """Get set of meal IDs that already have ingredients parsed."""
    headers = {"Authorization": f"Bearer {get_token()}"}
    meal_ids = set()
    page = 1
    per_page = 500

    while True:
        # Only fetch the mealId field to minimize data transfer
        url = f"{PB_URL}/api/collections/ingredients/records?page={page}&perPage={per_page}&fields=mealId"
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        items = data.get("items", [])
        for item in items:
            if item.get("mealId"):
                meal_ids.add(item["mealId"])
        if len(items) < per_page:
            break
        page += 1

    return meal_ids


def fetch_unparsed_meals(since_date=None):
    """
    Fetch only meals that haven't been parsed yet.
    
    Args:
        since_date: Optional ISO date string (e.g. '2026-01-24') to filter meals after this date
    """
    all_meals = fetch_meals()
    parsed_ids = get_parsed_meal_ids()
    
    # Filter by date if specified
    if since_date:
        from datetime import datetime
        cutoff = datetime.fromisoformat(since_date)
        all_meals = [m for m in all_meals if m.get("timestamp") and 
                     datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00").split("+")[0]) >= cutoff]
        print(f"📅 Filtered to {len(all_meals)} meals since {since_date}")
    
    unparsed = [m for m in all_meals if m["id"] not in parsed_ids]
    print(f"🆕 {len(unparsed)} unparsed meals (skipped {len(parsed_ids)} already parsed)")
    return unparsed


def fetch_all_ingredients():
    """Fetch all ingredients from PocketBase."""
    return fetch_records("ingredients")


def delete_all_ingredients():
    """Delete all ingredients from PocketBase. Returns count deleted."""
    headers = {"Authorization": f"Bearer {get_token()}"}
    ingredients = fetch_all_ingredients()
    
    deleted = 0
    for ing in ingredients:
        url = f"{PB_URL}/api/collections/ingredients/records/{ing['id']}"
        r = requests.delete(url, headers=headers)
        if r.status_code == 204:
            deleted += 1
    
    return deleted
