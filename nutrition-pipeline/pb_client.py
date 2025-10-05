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
