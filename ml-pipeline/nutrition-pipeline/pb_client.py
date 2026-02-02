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


def add_learned_confusion(user_id: str, mistaken: str, actual: str):
    """
    Add a confusion pair to user's profile (mistaken -> actual).
    E.g., "yellow mustard" -> "pickled banana peppers"
    """
    profile = get_or_create_user_food_profile(user_id)
    if not profile:
        return None
    
    confusion_pairs = profile.get("confusionPairs", []) or []
    
    # Check if this pair already exists
    for pair in confusion_pairs:
        if pair.get("mistaken", "").lower() == mistaken.lower():
            # Update existing pair
            pair["actual"] = actual
            pair["count"] = pair.get("count", 0) + 1
            break
    else:
        # Add new pair
        confusion_pairs.append({
            "mistaken": mistaken,
            "actual": actual,
            "count": 1
        })
    
    return update_user_food_profile(profile["id"], {"confusionPairs": confusion_pairs})


def add_common_food(user_id: str, food_name: str, default_portion: str = None, aliases: list = None):
    """
    Add a food to user's common foods list.
    """
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


def build_user_context_prompt(user_id: str) -> str:
    """
    Build a context string for GPT prompts based on user's food profile.
    Returns a string to inject into parsing prompts.
    """
    profile = get_user_food_profile(user_id)
    if not profile:
        return ""
    
    context_parts = []
    
    # Common foods
    foods = profile.get("foods", [])
    if foods:
        food_names = [f.get("name") for f in foods[:10] if f.get("name")]  # Top 10
        if food_names:
            context_parts.append(f"USER'S COMMON FOODS: {', '.join(food_names)}")
    
    # Confusion pairs (most important for learning)
    confusions = profile.get("confusionPairs", [])
    if confusions:
        confusion_strs = []
        for c in confusions[:5]:  # Top 5
            mistaken = c.get("mistaken")
            actual = c.get("actual")
            if mistaken and actual:
                confusion_strs.append(f'"{mistaken}" is usually "{actual}"')
        if confusion_strs:
            context_parts.append(f"KNOWN CONFUSIONS: {'; '.join(confusion_strs)}")
    
    # Portion bias
    portion_bias = profile.get("portionBias", 1.0)
    if portion_bias and abs(portion_bias - 1.0) > 0.1:
        if portion_bias > 1.0:
            context_parts.append(f"PORTION NOTE: User's portions are typically {portion_bias:.1f}x larger than average")
        else:
            context_parts.append(f"PORTION NOTE: User's portions are typically {portion_bias:.1f}x smaller than average")
    
    return "\n".join(context_parts)
