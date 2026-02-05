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


def fetch_ingredients_by_meal_id(meal_id: str, per_page: int = 500):
    """Fetch all ingredients for a meal. Paginates to get everything."""
    if not meal_id:
        return []
    import urllib.parse
    filter_str = f"mealId='{meal_id}'"
    encoded = urllib.parse.quote(filter_str)
    headers = {"Authorization": f"Bearer {get_token()}"}
    all_items = []
    page = 1
    try:
        while True:
            url = f"{PB_URL}/api/collections/ingredients/records?filter={encoded}&perPage={per_page}&page={page}"
            r = requests.get(url, headers=headers)
            if r.status_code != 200:
                return all_items
            data = r.json()
            items = data.get("items", [])
            all_items.extend(items)
            if len(items) < per_page:
                break
            page += 1
        return all_items
    except Exception as e:
        print(f"⚠️ fetch_ingredients_by_meal_id failed: {e}")
        return all_items


def insert_ingredient(ingredient):
    url = f"{PB_URL}/api/collections/ingredients/records"
    headers = {"Authorization": f"Bearer {get_token()}"}
    r = requests.post(url, headers=headers, json=ingredient)
    if r.status_code >= 400:
        try:
            err = r.json()
            msg = err.get("message", r.text) or r.text
            details = err.get("data", {})
            raise RuntimeError(f"PocketBase {r.status_code}: {msg} | details: {details}")
        except (ValueError, KeyError):
            r.raise_for_status()
    return r.json()


def delete_non_food_logs_for_meal(meal_id: str) -> int:
    """Delete all non_food_logs for a meal. Returns count deleted. Prevents duplicates on re-parse."""
    headers = {"Authorization": f"Bearer {get_token()}"}
    import urllib.parse
    filt = urllib.parse.quote(f"mealId='{meal_id}'")
    url = f"{PB_URL}/api/collections/non_food_logs/records?filter={filt}&perPage=100"
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        return 0
    data = r.json()
    items = data.get("items", [])
    deleted = 0
    for item in items:
        rid = item.get("id")
        if rid:
            dr = requests.delete(f"{PB_URL}/api/collections/non_food_logs/records/{rid}", headers=headers)
            if dr.status_code in (200, 204):
                deleted += 1
    if deleted:
        print(f"   🗑️ Deleted {deleted} existing non_food_log(s) for meal {meal_id}")
    return deleted


def delete_corrections_for_ingredient(ingredient_id: str) -> int:
    """Delete ingredient_corrections that reference this ingredient (required before deleting ingredient)."""
    if not ingredient_id:
        return 0
    import urllib.parse
    filt = f"ingredientId='{ingredient_id}'"
    encoded = urllib.parse.quote(filt)
    headers = {"Authorization": f"Bearer {get_token()}"}
    deleted = 0
    while True:
        url = f"{PB_URL}/api/collections/ingredient_corrections/records?filter={encoded}&perPage=100"
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            break
        items = r.json().get("items", [])
        if not items:
            break
        for rec in items:
            rid = rec.get("id")
            if rid:
                dr = requests.delete(f"{PB_URL}/api/collections/ingredient_corrections/records/{rid}", headers=headers)
                if dr.status_code in (200, 204):
                    deleted += 1
    return deleted


def delete_ingredient(ingredient_id: str) -> bool:
    """Delete an ingredient by ID. Uses service token (bypasses API rules)."""
    lid = (ingredient_id or "").strip() if isinstance(ingredient_id, str) else None
    if not lid and isinstance(ingredient_id, dict):
        lid = (ingredient_id.get("id") or "").strip()
    if not lid:
        return False
    headers = {"Authorization": f"Bearer {get_token()}"}
    # Must delete ingredient_corrections first (they have required relation to ingredient)
    n = delete_corrections_for_ingredient(lid)
    if n:
        print(f"   📎 Deleted {n} correction(s) for ingredient {lid}")
    url = f"{PB_URL}/api/collections/ingredients/records/{lid}"
    r = requests.delete(url, headers=headers)
    ok = r.status_code in (200, 204)
    if not ok:
        print(f"   ⚠️ Delete {lid} failed: {r.status_code} {r.text[:150]}")
    return ok


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


def fetch_meals_for_user_on_date(user_id: str, date_iso: str, exclude_meal_id: str = None, before_timestamp: str = None, limit: int = 20):
    """
    Fetch meals for a user on a given UTC calendar day (for "recent meals" context).
    date_iso: YYYY-MM-DD (UTC).
    before_timestamp: if set, only return meals with timestamp < this (so "most recent" = immediately before current).
    Returns list of meals (id, text, timestamp) sorted by -timestamp (newest first).
    """
    if not user_id or not date_iso or len(date_iso.strip()) < 10:
        return []
    import urllib.parse
    date_iso = date_iso.strip()[:10]  # YYYY-MM-DD only
    # PocketBase stores timestamp with space (e.g. "2026-02-02 18:05:21.123Z"); filter must match
    start_ts = f"{date_iso} 00:00:00.000Z"
    end_ts = f"{date_iso} 23:59:59.999Z"
    filter_parts = [f"user='{user_id}'", f'timestamp >= "{start_ts}"', f'timestamp <= "{end_ts}"']
    if before_timestamp and (before_timestamp or "").strip():
        # Only meals that happened BEFORE the current one → first in list = immediately previous
        filter_parts.append(f'timestamp < "{before_timestamp.strip()}"')
    if exclude_meal_id:
        filter_parts.append(f"id != '{exclude_meal_id}'")
    filter_str = " && ".join(filter_parts)
    encoded = urllib.parse.quote(filter_str)
    url = f"{PB_URL}/api/collections/meals/records?filter={encoded}&sort=-timestamp&perPage={limit}&fields=id,text,timestamp"
    headers = {"Authorization": f"Bearer {get_token()}"}
    try:
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            return []
        items = r.json().get("items", [])
        return items
    except Exception as e:
        print(f"⚠️ fetch_meals_for_user_on_date failed: {e}")
        return []


def fetch_meals_for_user_on_local_date(user_id: str, timestamp_iso: str, timezone_iana: str, exclude_meal_id: str = None, before_timestamp: str = None, limit: int = 20):
    """
    Fetch meals for a user on the same *local* calendar day as the given timestamp.
    Use this when the client sends timezone so "recent meals today" matches the user's day, not UTC.
    timestamp_iso: meal timestamp (used to get local date; also for before_timestamp when provided).
    before_timestamp: if set, only return meals with timestamp < this (so first = immediately before current).
    Returns list of meals (id, text, timestamp) sorted by -timestamp (newest first).
    """
    if not user_id or not timestamp_iso or not (timezone_iana or "").strip():
        return []
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
    except ImportError:
        print("⚠️ zoneinfo not available, falling back to UTC day")
        date_iso = (timestamp_iso.strip()[:10] if len((timestamp_iso or "").strip()) >= 10 else "").strip()
        if date_iso and len(date_iso) == 10:
            return fetch_meals_for_user_on_date(user_id, date_iso, exclude_meal_id=exclude_meal_id, limit=limit)
        return []
    ts = (timestamp_iso or "").strip().replace(" ", "T")
    if ts.endswith("Z") and "+" not in ts[-2:] and "-" not in ts[-3:]:
        ts = ts[:-1] + "+00:00"
    try:
        dt_utc = datetime.fromisoformat(ts)
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=ZoneInfo("UTC"))
        tz = ZoneInfo(timezone_iana.strip())
        dt_local = dt_utc.astimezone(tz)
        local_date = dt_local.strftime("%Y-%m-%d")
        # UTC range for that local day: start and end of local_date in tz
        start_local = datetime.strptime(local_date + " 00:00:00", "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
        end_local = datetime.strptime(local_date + " 23:59:59", "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
        start_utc = start_local.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M:%S.%f")[:23] + "Z"
        end_utc = end_local.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M:%S.%f")[:23] + "Z"
    except Exception as e:
        print(f"⚠️ fetch_meals_for_user_on_local_date parse failed: {e}")
        date_iso = (timestamp_iso.strip()[:10] if len((timestamp_iso or "").strip()) >= 10 else "").strip()
        if date_iso and len(date_iso) == 10:
            return fetch_meals_for_user_on_date(user_id, date_iso, exclude_meal_id=exclude_meal_id, limit=limit)
        return []
    import urllib.parse
    filter_parts = [f"user='{user_id}'", f'timestamp >= "{start_utc}"', f'timestamp <= "{end_utc}"']
    # Only meals that happened BEFORE the current one → first in list = immediately previous
    if before_timestamp and (before_timestamp or "").strip():
        bt = before_timestamp.strip()  # keep same format as PB (e.g. "2026-02-02 18:05:21.123Z")
        filter_parts.append(f'timestamp < "{bt}"')
    if exclude_meal_id:
        filter_parts.append(f"id != '{exclude_meal_id}'")
    filter_str = " && ".join(filter_parts)
    encoded = urllib.parse.quote(filter_str)
    url = f"{PB_URL}/api/collections/meals/records?filter={encoded}&sort=-timestamp&perPage={limit}&fields=id,text,timestamp"
    headers = {"Authorization": f"Bearer {get_token()}"}
    try:
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            return []
        items = r.json().get("items", [])
        return items
    except Exception as e:
        print(f"⚠️ fetch_meals_for_user_on_local_date failed: {e}")
        return []


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


# ============================================================
# TIER 4: Hybrid Parsing Helper Functions
# ============================================================

import hashlib

def compute_meal_hash(meal_text: str) -> str:
    """Compute SHA-256 hash of normalized meal text for cache lookup."""
    normalized = meal_text.lower().strip()
    return hashlib.sha256(normalized.encode()).hexdigest()


def lookup_parsing_cache(meal_text: str):
    """
    Check if we have a cached parse for this meal text.
    Returns cached ingredients list or None if not found.
    """
    if not meal_text:
        return None
    
    meal_hash = compute_meal_hash(meal_text)
    url = f"{PB_URL}/api/collections/parsing_cache/records?filter=(mealHash='{meal_hash}')"
    
    try:
        r = requests.get(url)  # Public read, no auth needed
        if r.status_code == 200:
            data = r.json()
            items = data.get("items", [])
            if items:
                cached = items[0]
                # Increment hit count (fire and forget)
                try:
                    update_url = f"{PB_URL}/api/collections/parsing_cache/records/{cached['id']}"
                    headers = {"Authorization": f"Bearer {get_token()}"}
                    requests.patch(update_url, headers=headers, json={"hitCount": (cached.get("hitCount") or 0) + 1})
                except:
                    pass  # Don't fail if hit count update fails
                return cached.get("parsedIngredients", [])
    except Exception as e:
        print(f"⚠️ Cache lookup failed: {e}")
    
    return None


def save_to_parsing_cache(meal_text: str, parsed_ingredients: list, model_used: str = "gpt-4o-mini", cost_usd: float = None):
    """
    Save parsed ingredients to cache for future lookups.
    """
    if not meal_text or not parsed_ingredients:
        return None
    
    meal_hash = compute_meal_hash(meal_text)
    
    record = {
        "mealText": meal_text[:500],  # Truncate very long text
        "mealHash": meal_hash,
        "parsedIngredients": parsed_ingredients,
        "modelUsed": model_used,
        "hitCount": 0,
    }
    if cost_usd is not None:
        record["costUsd"] = cost_usd
    
    url = f"{PB_URL}/api/collections/parsing_cache/records"
    headers = {"Authorization": f"Bearer {get_token()}"}
    
    try:
        r = requests.post(url, headers=headers, json=record)
        if r.status_code == 200:
            print(f"💾 Cached parse for: {meal_text[:30]}...")
            return r.json()
    except Exception as e:
        print(f"⚠️ Cache save failed: {e}")
    
    return None


def lookup_brand_food(brand: str, item: str):
    """
    Look up a food item in the brand database.
    Returns brand food record or None if not found.
    
    Example: lookup_brand_food("Chipotle", "Chicken Burrito Bowl")
    """
    if not brand or not item:
        return None
    
    # URL encode the filter
    import urllib.parse
    filter_str = f"(brand~'{brand}' && item~'{item}')"
    encoded_filter = urllib.parse.quote(filter_str)
    url = f"{PB_URL}/api/collections/brand_foods/records?filter={encoded_filter}"
    
    try:
        r = requests.get(url)  # Public read, no auth needed
        if r.status_code == 200:
            data = r.json()
            items = data.get("items", [])
            if items:
                return items[0]
    except Exception as e:
        print(f"⚠️ Brand lookup failed: {e}")
    
    return None


def search_brand_foods(query: str):
    """
    Search brand database for matching items.
    Returns list of matching brand foods.
    
    Example: search_brand_foods("burrito") 
    """
    if not query:
        return []
    
    import urllib.parse
    # Search both brand and item fields
    filter_str = f"(brand~'{query}' || item~'{query}')"
    encoded_filter = urllib.parse.quote(filter_str)
    url = f"{PB_URL}/api/collections/brand_foods/records?filter={encoded_filter}&perPage=10"
    
    try:
        r = requests.get(url)
        if r.status_code == 200:
            return r.json().get("items", [])
    except Exception as e:
        print(f"⚠️ Brand search failed: {e}")
    
    return []


def lookup_meal_template(user_id: str, meal_text: str):
    """
    Look up a meal template for this user that matches the meal text.
    Returns template record or None if not found.
    
    Example: lookup_meal_template("user123", "my usual breakfast")
    """
    if not user_id or not meal_text:
        return None
    
    import urllib.parse
    # Search for templates where name matches the meal text
    filter_str = f"(user='{user_id}' && name~'{meal_text}')"
    encoded_filter = urllib.parse.quote(filter_str)
    url = f"{PB_URL}/api/collections/meal_templates/records?filter={encoded_filter}"
    headers = {"Authorization": f"Bearer {get_token()}"}
    
    try:
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            data = r.json()
            items = data.get("items", [])
            if items:
                template = items[0]
                # Increment usage count
                try:
                    update_url = f"{PB_URL}/api/collections/meal_templates/records/{template['id']}"
                    requests.patch(update_url, headers=headers, json={"usageCount": (template.get("usageCount") or 0) + 1})
                except:
                    pass
                return template
    except Exception as e:
        print(f"⚠️ Template lookup failed: {e}")
    
    return None


def get_user_templates(user_id: str):
    """
    Get all meal templates for a user.
    Returns list of templates sorted by usage count.
    """
    if not user_id:
        return []
    
    import urllib.parse
    filter_str = f"(user='{user_id}')"
    encoded_filter = urllib.parse.quote(filter_str)
    url = f"{PB_URL}/api/collections/meal_templates/records?filter={encoded_filter}&sort=-usageCount"
    headers = {"Authorization": f"Bearer {get_token()}"}
    
    try:
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            return r.json().get("items", [])
    except Exception as e:
        print(f"⚠️ Get templates failed: {e}")
    
    return []


# ============================================================
# TIER 2: Learning from Corrections
# ============================================================

def get_learned_patterns_for_user(user_id: str):
    """
    Get learned patterns for the Learning panel. Uses admin token so it works
    even when PocketBase API rules block direct user access.
    Returns list of { original, learned, count, correctionIds, status, confidence }.
    """
    if not user_id:
        return []
    patterns_from_profile = []
    profile = get_user_food_profile(user_id)
    if profile:
        pairs = profile.get("confusionPairs") or []
        for c in pairs:
            mistaken = (c.get("mistaken") or "").strip()
            actual = (c.get("actual") or "").strip()
            if mistaken and actual and mistaken.lower() != actual.lower():
                patterns_from_profile.append({
                    "original": mistaken.lower(),
                    "learned": actual,
                    "count": c.get("count", 1),
                    "correctionIds": [],
                    "status": "confident" if (c.get("count") or 1) >= 3 else "learning",
                    "confidence": min(0.5 + ((c.get("count") or 1) * 0.15), 0.99),
                })
    if patterns_from_profile:
        patterns_from_profile.sort(key=lambda x: -x["count"])
        return patterns_from_profile
    # Fallback: aggregate from corrections
    corrections = get_user_corrections(user_id=user_id)
    patterns = {}
    for c in corrections:
        if c.get("correctionType") == "add_missing":
            continue
        orig = (c.get("originalParse") or {}).get("name", "").lower()
        corr = (c.get("userCorrection") or {}).get("name", "")
        if orig and corr and orig != corr.lower():
            key = f"{orig}→{corr}"
            if key not in patterns:
                patterns[key] = {
                    "original": orig,
                    "learned": corr,
                    "count": 0,
                    "correctionIds": [],
                }
            patterns[key]["count"] += 1
            patterns[key]["correctionIds"].append(c.get("id", ""))
    result = [
        {
            **p,
            "status": "confident" if p["count"] >= 3 else "learning",
            "confidence": min(0.5 + (p["count"] * 0.15), 0.99),
        }
        for p in patterns.values()
    ]
    result.sort(key=lambda x: -x["count"])
    return result


def get_user_corrections(user_id: str = None, original_name: str = None):
    """
    Get corrections from the database.
    Can filter by user and/or original ingredient name.
    
    Returns list of correction records.
    """
    headers = {"Authorization": f"Bearer {get_token()}"}
    
    filters = []
    if user_id:
        filters.append(f"user='{user_id}'")
    if original_name:
        # Search for corrections where original name matches
        filters.append(f"originalParse.name~'{original_name}'")
    
    filter_str = " && ".join(filters) if filters else ""
    
    import urllib.parse
    url = f"{PB_URL}/api/collections/ingredient_corrections/records?sort=-created&perPage=100"
    if filter_str:
        url += f"&filter={urllib.parse.quote(filter_str)}"
    
    try:
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            return r.json().get("items", [])
    except Exception as e:
        print(f"⚠️ Failed to get corrections: {e}")
    
    return []


def check_learned_correction(ingredient_name: str, user_id: str = None):
    """
    Check if we've learned a correction for this ingredient.
    
    Returns:
        {
            "should_correct": True/False,
            "corrected_name": "soy milk",
            "corrected_quantity": 8,
            "corrected_unit": "oz",
            "confidence": 0.95,
            "times_corrected": 3,
            "reason": "You've corrected 'milk' to 'soy milk' 3 times"
        }
    """
    # Get all corrections for this ingredient name
    corrections = get_user_corrections(user_id=user_id, original_name=ingredient_name)
    
    if not corrections:
        return {"should_correct": False}
    
    # Count corrections by target name
    correction_counts = {}
    for c in corrections:
        original = c.get("originalParse", {})
        corrected = c.get("userCorrection", {})
        
        # Only count name changes
        if original.get("name", "").lower() == ingredient_name.lower():
            target_name = corrected.get("name", "")
            if target_name and target_name.lower() != ingredient_name.lower():
                if target_name not in correction_counts:
                    correction_counts[target_name] = {
                        "count": 0,
                        "latest": corrected
                    }
                correction_counts[target_name]["count"] += 1
    
    if not correction_counts:
        return {"should_correct": False}
    
    # Find most common correction
    most_common = max(correction_counts.items(), key=lambda x: x[1]["count"])
    target_name = most_common[0]
    count = most_common[1]["count"]
    latest = most_common[1]["latest"]
    
    # Instant learning: even 1 correction counts
    # Confidence increases with more corrections
    confidence = min(0.5 + (count * 0.15), 0.99)  # 1 correction = 0.65, 3 = 0.95
    
    return {
        "should_correct": True,
        "corrected_name": target_name,
        "corrected_quantity": latest.get("quantity"),
        "corrected_unit": latest.get("unit"),
        "confidence": confidence,
        "times_corrected": count,
        "reason": f"You've corrected '{ingredient_name}' to '{target_name}' {count} time(s)"
    }


def get_all_learned_patterns(user_id: str = None):
    """
    Get all learned patterns for a user (for the tracking view).
    
    Returns list of patterns like:
    [
        {"original": "milk", "learned": "soy milk", "count": 3, "confidence": 0.95},
        {"original": "chicken", "learned": "chicken breast", "count": 2, "confidence": 0.80},
    ]
    """
    corrections = get_user_corrections(user_id=user_id)
    
    # Group by original name
    patterns = {}
    for c in corrections:
        original = c.get("originalParse", {})
        corrected = c.get("userCorrection", {})
        
        orig_name = original.get("name", "").lower()
        corr_name = corrected.get("name", "")
        
        if orig_name and corr_name and orig_name != corr_name.lower():
            key = f"{orig_name}→{corr_name}"
            if key not in patterns:
                patterns[key] = {
                    "original": orig_name,
                    "learned": corr_name,
                    "count": 0,
                    "latest_correction": c
                }
            patterns[key]["count"] += 1
    
    # Convert to list and add confidence
    result = []
    for p in patterns.values():
        p["confidence"] = min(0.5 + (p["count"] * 0.15), 0.99)
        result.append(p)
    
    # Sort by count descending
    result.sort(key=lambda x: x["count"], reverse=True)
    return result


def lookup_similar_meal_in_history(user_id: str, meal_text: str, limit: int = 5):
    """
    Find similar past meals from user's history.
    Returns list of similar meals with their ingredients.
    
    This is a simple text-based search; could be enhanced with embeddings.
    """
    if not meal_text:
        return []
    
    # Get keywords from meal text
    keywords = [w.strip().lower() for w in meal_text.split() if len(w) > 2]
    if not keywords:
        return []
    
    import urllib.parse
    
    # Search meals containing any keyword
    # Note: This is basic - Tier 3 could use semantic search
    filter_parts = [f"text~'{kw}'" for kw in keywords[:3]]  # Limit to first 3 keywords
    filter_str = "(" + " || ".join(filter_parts) + ")"
    encoded_filter = urllib.parse.quote(filter_str)
    
    url = f"{PB_URL}/api/collections/meals/records?filter={encoded_filter}&sort=-created&perPage={limit}"
    headers = {"Authorization": f"Bearer {get_token()}"}
    
    try:
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            return r.json().get("items", [])
    except Exception as e:
        print(f"⚠️ History lookup failed: {e}")
    
    return []


# ============================================================
# USER FOOD PROFILE - Personal food vocabulary and learning
# ============================================================

def get_user_food_profile(user_id: str):
    """
    Get a user's food profile (common foods, confusion pairs, portion bias).
    Returns the profile record or None if not found.
    """
    if not user_id:
        return None
    
    import urllib.parse
    filter_str = f"(user='{user_id}')"
    encoded_filter = urllib.parse.quote(filter_str)
    url = f"{PB_URL}/api/collections/user_food_profile/records?filter={encoded_filter}"
    headers = {"Authorization": f"Bearer {get_token()}"}
    
    try:
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            items = r.json().get("items", [])
            if items:
                return items[0]
    except Exception as e:
        print(f"⚠️ Failed to get user food profile: {e}")
    
    return None


def get_or_create_user_food_profile(user_id: str):
    """
    Get or create a user's food profile.
    Returns the profile record.
    """
    profile = get_user_food_profile(user_id)
    if profile:
        return profile
    
    # Create new profile
    headers = {"Authorization": f"Bearer {get_token()}"}
    url = f"{PB_URL}/api/collections/user_food_profile/records"
    
    new_profile = {
        "user": user_id,
        "foods": [],
        "confusionPairs": [],
        "portionBias": 1.0,
    }
    
    try:
        r = requests.post(url, headers=headers, json=new_profile)
        if r.status_code == 200:
            print(f"📝 Created new food profile for user {user_id}")
            return r.json()
    except Exception as e:
        print(f"⚠️ Failed to create user food profile: {e}")
    
    return None


def update_user_food_profile(profile_id: str, updates: dict):
    """
    Update a user's food profile.
    """
    headers = {"Authorization": f"Bearer {get_token()}"}
    url = f"{PB_URL}/api/collections/user_food_profile/records/{profile_id}"
    
    try:
        r = requests.patch(url, headers=headers, json=updates)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"⚠️ Failed to update user food profile: {e}")
    
    return None


def remove_learned_pattern(user_id: str, original: str, learned: str, correction_ids: list = None):
    """
    Remove a learned pattern from user's profile. Uses admin token.
    Also deletes the given correction records if provided.
    Returns True on success.
    """
    profile = get_user_food_profile(user_id)
    if not profile:
        return True  # No profile to update
    orig = (original or "").lower().strip()
    learn = (learned or "").strip()
    confusions = [c for c in (profile.get("confusionPairs") or [])
                  if (c.get("mistaken") or "").lower().strip() != orig or (c.get("actual") or "").strip() != learn]
    foods = [f for f in (profile.get("foods") or [])
             if (f.get("name") or "").lower().strip() != learn]
    if len(confusions) < len(profile.get("confusionPairs") or []) or len(foods) < len(profile.get("foods") or []):
        update_user_food_profile(profile["id"], {"confusionPairs": confusions, "foods": foods})
    for cid in (correction_ids or []):
        if cid:
            try:
                headers = {"Authorization": f"Bearer {get_token()}"}
                requests.delete(f"{PB_URL}/api/collections/ingredient_corrections/records/{cid}", headers=headers)
            except Exception:
                pass
    return True


# Unit words - reject if string is JUST these or "number + unit"
UNIT_WORDS = {"piece", "pieces", "oz", "gram", "grams", "cup", "cups",
              "tbsp", "tablespoon", "tablespoons", "tsp", "teaspoon",
              "serving", "servings", "slice", "slices", "lb", "pound", "mg", "ml"}


def _looks_like_unit_or_quantity(s: str) -> bool:
    """Reject strings that are units or quantities, not food names (e.g. '6 pieces', '2 tbsp')."""
    if not s or not isinstance(s, str):
        return True
    low = s.lower().strip()
    parts = [p for p in low.split() if p]
    # "2 tbsp", "6 pieces" - number followed by unit
    if len(parts) <= 2 and parts:
        first = parts[0].replace(".", "")
        if first.isdigit() and len(parts) == 2 and parts[1] in UNIT_WORDS:
            return True
        if len(parts) == 1 and parts[0] in UNIT_WORDS:
            return True
    return False


def add_learned_confusion(user_id: str, mistaken: str, actual: str, visual_context: str = None, meal_context: str = None):
    """
    Add a confusion pair to user's profile (mistaken -> actual).
    E.g., "yellow mustard" -> "pickled banana peppers"
    
    Args:
        user_id: The user's ID
        mistaken: What GPT thought it was
        actual: What it actually was
        visual_context: Description of what it looked like (e.g., "sliced rings on hot dog")
        meal_context: What meal this was part of (e.g., "hot dog")
    """
    # Reject unit/quantity mixups (e.g. "6 pieces" -> "2 tbsp" from wrong parsing)
    if _looks_like_unit_or_quantity(mistaken) or _looks_like_unit_or_quantity(actual):
        print(f"   ⚠️ Skipping learned confusion (looks like unit/quantity): '{mistaken}' -> '{actual}'")
        return None
    profile = get_or_create_user_food_profile(user_id)
    if not profile:
        return None
    
    confusion_pairs = profile.get("confusionPairs", []) or []
    
    # Check if this pair already exists
    found = False
    for pair in confusion_pairs:
        if pair.get("mistaken", "").lower() == mistaken.lower() and pair.get("actual", "").lower() == actual.lower():
            # Update existing pair
            pair["count"] = pair.get("count", 0) + 1
            # Add visual context if provided and not already there
            if visual_context:
                contexts = pair.get("visualContexts", [])
                if visual_context not in contexts:
                    contexts.append(visual_context)
                pair["visualContexts"] = contexts[-5:]  # Keep last 5
            if meal_context:
                meals = pair.get("mealContexts", [])
                if meal_context not in meals:
                    meals.append(meal_context)
                pair["mealContexts"] = meals[-5:]  # Keep last 5
            found = True
            break
    
    if not found:
        # Add new pair
        new_pair = {
            "mistaken": mistaken,
            "actual": actual,
            "count": 1,
            "visualContexts": [visual_context] if visual_context else [],
            "mealContexts": [meal_context] if meal_context else [],
        }
        confusion_pairs.append(new_pair)
    
    return update_user_food_profile(profile["id"], {"confusionPairs": confusion_pairs})


def add_portion_preference(user_id: str, food_name: str, quantity: float, unit: str) -> bool:
    """
    Learn that user typically has this quantity/unit for this food.
    E.g. "egg" -> 2 eggs (user always corrects to 2)
    """
    if not food_name or not isinstance(quantity, (int, float)) or quantity <= 0:
        return False
    profile = get_or_create_user_food_profile(user_id)
    if not profile:
        return False

    prefs = profile.get("portionPreferences", []) or []
    food_lower = food_name.lower().strip()
    unit_norm = (unit or "serving").strip()

    found = False
    for p in prefs:
        if (p.get("food") or "").lower() == food_lower and (p.get("unit") or "").lower() == unit_norm.lower():
            p["quantity"] = quantity
            p["count"] = p.get("count", 0) + 1
            p["unit"] = unit_norm
            found = True
            break
    if not found:
        prefs.append({"food": food_name, "quantity": quantity, "unit": unit_norm, "count": 1})

    return update_user_food_profile(profile["id"], {"portionPreferences": prefs}) is not None


def add_common_food(user_id: str, food_name: str, default_portion: str = None, aliases: list = None):
    """
    Add a food to user's common foods list.
    """
    # Reject units/quantities mistakenly added as foods (e.g. "2 tbsp")
    if _looks_like_unit_or_quantity(food_name):
        print(f"   ⚠️ Skipping add_common_food (looks like unit/quantity): '{food_name}'")
        return None
    profile = get_or_create_user_food_profile(user_id)
    if not profile:
        return None
    
    foods = profile.get("foods", []) or []
    
    # Check if food already exists
    for food in foods:
        if food.get("name", "").lower() == food_name.lower():
            # Update frequency
            food["frequency"] = food.get("frequency", 0) + 1
            if default_portion:
                food["defaultPortion"] = default_portion
            if aliases:
                existing_aliases = food.get("aliases", [])
                food["aliases"] = list(set(existing_aliases + aliases))
            break
    else:
        # Add new food
        foods.append({
            "name": food_name,
            "frequency": 1,
            "defaultPortion": default_portion,
            "aliases": aliases or []
        })
    
    return update_user_food_profile(profile["id"], {"foods": foods})


# Brand-like tokens for pantry (branded/specific items)
_PANTRY_KNOWN_BRANDS = {
    "chipotle", "starbucks", "mcdonalds", "mcdonald's", "subway",
    "chick-fil-a", "chickfila", "wendys", "wendy's", "taco bell",
    "panera", "sweetgreen", "cava", "shake shack", "five guys",
    "in-n-out", "popeyes", "kfc", "dominos", "pizza hut",
    "whole foods", "trader joes", "trader joe's", "costco",
    "wegmans", "oatly", "kirkland", "aldi", "safeway", "kroger",
}


def is_branded_or_specific(name: str) -> bool:
    """
    Heuristic: ingredient name looks branded or specific enough for pantry.
    Returns True if we should add to pantry (e.g. Wegmans bone broth, Oatly oat milk).
    """
    if not name or not isinstance(name, str):
        return False
    n = name.lower().strip()
    if len(n) < 4:
        return False
    # Contains known brand
    for brand in _PANTRY_KNOWN_BRANDS:
        if brand in n:
            return True
    # Longer multi-word name (likely specific, e.g. "organic unsweetened soy milk")
    words = n.split()
    return len(words) >= 3


def add_to_pantry(user_id: str, name: str, usda_code: str = None, nutrition: list = None, source: str = "parse") -> bool:
    """
    Add or bump an item in user's pantry (branded/specific items, most recent first).
    Cap at 50 items; evict oldest when full.
    """
    if not name or not isinstance(name, str) or not name.strip():
        return False
    if _looks_like_unit_or_quantity(name):
        return False
    profile = get_or_create_user_food_profile(user_id)
    if not profile:
        return False

    pantry = profile.get("pantry", []) or []
    now = __import__("datetime").datetime.utcnow().isoformat() + "Z"
    name_norm = name.strip()
    name_lower = name_norm.lower()

    # Update existing or add new
    found = False
    for item in pantry:
        if (item.get("name") or "").lower() == name_lower:
            item["lastUsed"] = now
            item["usdaCode"] = usda_code if usda_code is not None else item.get("usdaCode")
            if nutrition is not None:
                item["nutrition"] = nutrition
            item["source"] = source
            found = True
            break
    if not found:
        pantry.append({
            "name": name_norm,
            "usdaCode": usda_code,
            "nutrition": nutrition,
            "lastUsed": now,
            "source": source,
        })

    # Sort by lastUsed desc, cap at 50
    pantry.sort(key=lambda x: x.get("lastUsed", ""), reverse=True)
    pantry = pantry[:50]

    return update_user_food_profile(profile["id"], {"pantry": pantry}) is not None


def get_pantry(user_id: str, limit: int = 20) -> list:
    """
    Get user's pantry items sorted by most recent first.
    Returns list of {name, usdaCode, nutrition, lastUsed, source}.
    """
    profile = get_user_food_profile(user_id)
    if not profile:
        return []
    pantry = profile.get("pantry", []) or []
    pantry = sorted(pantry, key=lambda x: x.get("lastUsed", ""), reverse=True)
    return pantry[:limit]


def lookup_pantry_match(user_id: str, name: str) -> dict | None:
    """
    Check pantry for a matching ingredient name (normalized).
    Returns pantry item if found, else None.
    """
    if not name or not user_id:
        return None
    name_lower = name.lower().strip()
    pantry = get_pantry(user_id, limit=50)
    for item in pantry:
        item_name = (item.get("name") or "").lower()
        if item_name == name_lower:
            return item
        # Partial match: parsed name contained in pantry name or vice versa
        if name_lower in item_name or item_name in name_lower:
            return item
    return None


def build_user_context_prompt(user_id: str) -> str:
    """
    Build a context string for GPT prompts based on user's food profile.
    Returns a string to inject into parsing prompts.
    
    Key principles:
    - Common foods: User preferences (they eat these often)
    - Confusions: Only suggest after 3+ occurrences, frame as questions not assertions
    - Never auto-replace, always ask for confirmation
    """
    profile = get_user_food_profile(user_id)
    if not profile:
        return ""
    
    context_parts = []
    
    # Common foods - these are user preferences, not visual confusions
    # Frame as: "User frequently eats X" not "X is always Y"
    foods = profile.get("foods", [])
    if foods:
        # Sort by frequency, get top foods
        sorted_foods = sorted(foods, key=lambda f: f.get("frequency", 0), reverse=True)
        frequent_foods = [f.get("name") for f in sorted_foods[:8] if f.get("name") and f.get("frequency", 0) >= 2]
        if frequent_foods:
            context_parts.append(f"USER FREQUENTLY EATS: {', '.join(frequent_foods)}")
            context_parts.append("(Consider these as possibilities when identifying ambiguous items)")
    
    # Pantry - branded/specific items user has logged recently (for identification hints)
    pantry = get_pantry(user_id, limit=10)
    if pantry:
        pantry_names = [p.get("name") for p in pantry if p.get("name")]
        if pantry_names:
            context_parts.append("")
            context_parts.append(f"USER'S RECENT BRANDED ITEMS: {', '.join(pantry_names[:8])}")
            context_parts.append("(User has logged these specific items before - prefer these when they match)")
    
    # Confusion pairs - ONLY include if count >= 3 (reliable pattern)
    # Frame as QUESTIONS/POSSIBILITIES, not assertions
    confusions = profile.get("confusionPairs", [])
    reliable_confusions = [c for c in confusions if c.get("count", 0) >= 3]
    
    if reliable_confusions:
        context_parts.append("")
        context_parts.append("PAST IDENTIFICATION NOTES (ask user to confirm, don't auto-replace):")
        for c in reliable_confusions[:5]:
            mistaken = c.get("mistaken")
            actual = c.get("actual")
            count = c.get("count", 0)
            visual_contexts = c.get("visualContexts", [])
            
            if mistaken and actual:
                note = f"- When you see something that looks like '{mistaken}'"
                if visual_contexts:
                    note += f" (especially: {', '.join(visual_contexts[:2])})"
                note += f", it might actually be '{actual}' (corrected {count}x)"
                note += f" - ASK the user to confirm before assuming"
                context_parts.append(note)
    
    # Pending confusions (1-2 occurrences) - mention but don't emphasize
    pending_confusions = [c for c in confusions if 0 < c.get("count", 0) < 3]
    if pending_confusions:
        pending_items = [c.get("actual") for c in pending_confusions if c.get("actual")]
        if pending_items:
            context_parts.append(f"(Learning: user has also mentioned eating {', '.join(pending_items[:3])})")
    
    # Portion preferences (learned from corrections, e.g. "user always has 2 eggs")
    portion_prefs = profile.get("portionPreferences", []) or []
    if portion_prefs:
        prefs_by_count = sorted([p for p in portion_prefs if p.get("quantity") and p.get("food")],
                                key=lambda x: x.get("count", 0), reverse=True)
        if prefs_by_count:
            context_parts.append("")
            context_parts.append("PORTION PREFERENCES (user has corrected these before - prefer these amounts):")
            for p in prefs_by_count[:6]:
                food = p.get("food", "")
                qty = p.get("quantity")
                unit = p.get("unit", "serving")
                count = p.get("count", 0)
                if food and qty:
                    context_parts.append(f"- {food}: {qty} {unit} (corrected {count}x)")

    # Portion bias
    portion_bias = profile.get("portionBias", 1.0)
    if portion_bias and abs(portion_bias - 1.0) > 0.1:
        if portion_bias > 1.0:
            context_parts.append(f"PORTION NOTE: User's portions are typically {portion_bias:.1f}x larger than average")
        else:
            context_parts.append(f"PORTION NOTE: User's portions are typically {portion_bias:.1f}x smaller than average")
    
    return "\n".join(context_parts)
