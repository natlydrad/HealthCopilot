from pb_client import (
    fetch_unparsed_meals, insert_ingredient, get_token,
    # Tier 4: Hybrid parsing helpers
    lookup_parsing_cache, save_to_parsing_cache,
    lookup_brand_food, search_brand_foods,
    lookup_meal_template, lookup_similar_meal_in_history,
    # Tier 2: Learning from corrections
    check_learned_correction, get_all_learned_patterns,
    # Pantry
    add_to_pantry, is_branded_or_specific, lookup_pantry_match,
)
from parser_gpt import parse_ingredients, parse_ingredients_from_image
from lookup_usda import usda_lookup, usda_lookup_by_fdc_id
import os
import argparse

# ============================================================
# TIER 4: Feature Flags
# ============================================================
# Set to True to enable hybrid parsing (reduces GPT calls)
# Set to False to use GPT-only parsing (current behavior)
HYBRID_PARSING_ENABLED = os.getenv("HYBRID_PARSING", "false").lower() == "true"

# Individual feature flags for testing
USE_PARSING_CACHE = os.getenv("USE_PARSING_CACHE", "true").lower() == "true"
USE_BRAND_DATABASE = os.getenv("USE_BRAND_DATABASE", "true").lower() == "true"
USE_MEAL_TEMPLATES = os.getenv("USE_MEAL_TEMPLATES", "true").lower() == "true"
USE_HISTORY_LOOKUP = os.getenv("USE_HISTORY_LOOKUP", "false").lower() == "true"  # Disabled by default (experimental)

# Items to skip - either too vague or non-food items from image parsing
BANNED_INGREDIENTS = {
    # Vague meal descriptors
    "smoothie", "salad", "sandwich", "bowl", "dish", "meal", "food", "snack",
    "breakfast", "lunch", "dinner", "unknown item", "unknown", "item",
    "serving", "1 serving", "portion",
    # Kitchen items that slip through from images
    "knife", "fork", "spoon", "plate", "napkin", "cup", "glass", "table",
    "cutting board", "pan", "pot", "utensil", "container", "wrapper",
    "plate with food", "bowl with food", "dish with food",
    # Household items GPT sometimes sees (exact matches only)
    "rug", "round rug", "grey round rug", "thermo mug", 
    "counter", "countertop", "kitchen", "placemat", "towel",
}


def normalize_quantity(ing):
    if not ing.get("quantity") or ing["quantity"] == 0:
        ing["quantity"] = 1
        ing["unit"] = ing.get("unit") or "serving"
    return ing


# Unit to grams conversion (approximate)
UNIT_TO_GRAMS = {
    # Weight
    "oz": 28.35,
    "g": 1,
    "grams": 1,
    "gram": 1,
    # Volume
    "cup": 150,      # varies by food, conservative estimate
    "cups": 150,
    "tbsp": 15,
    "tablespoon": 15,
    "tsp": 5,
    "teaspoon": 5,
    # Count - smaller portions to avoid overestimating
    "piece": 50,
    "pieces": 50,
    "slice": 20,
    "slices": 20,
    "serving": 100,
    "link": 50,      # sausage link
    "links": 50,
    # Eggs
    "eggs": 50,
    "egg": 50,
    # Supplements - no macros
    "pill": 0,
    "pills": 0,
    "capsule": 0,
    "capsules": 0,
    "l": 0,
}


# ============================================================
# TIER 4: Hybrid Parsing Logic
# ============================================================

# Common brand keywords to detect brand mentions
KNOWN_BRANDS = {
    "chipotle", "starbucks", "mcdonalds", "mcdonald's", "subway", 
    "chick-fil-a", "chickfila", "wendys", "wendy's", "taco bell",
    "panera", "sweetgreen", "cava", "shake shack", "five guys",
    "in-n-out", "popeyes", "kfc", "dominos", "pizza hut",
    "whole foods", "trader joes", "trader joe's", "costco"
}


def detect_brand_in_text(text: str) -> str:
    """Detect if meal text mentions a known brand."""
    text_lower = text.lower()
    for brand in KNOWN_BRANDS:
        if brand in text_lower:
            return brand.title()
    return None


def hybrid_parse(meal: dict, user_id: str = None) -> tuple:
    """
    Tier 4 Hybrid Parsing Strategy:
    1. Check parsing cache → confidence: 0.80, strategy: "cached"
    2. Check meal templates → confidence: 0.95, strategy: "template"
    3. Check brand database → confidence: 0.90, strategy: "brand_db"
    4. Check user history → confidence: 0.75, strategy: "history"
    5. Fall back to GPT → confidence: 0.70, strategy: "gpt"
    
    Returns: (parsed_ingredients, parsing_strategy, confidence)
    """
    text = (meal.get("text") or "").strip()
    image_field = meal.get("image")
    
    # Strategy 1: Check parsing cache (text-only, images can't be cached this way)
    if HYBRID_PARSING_ENABLED and USE_PARSING_CACHE and text and not image_field:
        cached = lookup_parsing_cache(text)
        if cached:
            print(f"🎯 CACHE HIT: Using cached parse for '{text[:30]}...'")
            return cached, "cached", 0.80
    
    # Strategy 2: Check meal templates (if user_id available)
    if HYBRID_PARSING_ENABLED and USE_MEAL_TEMPLATES and user_id and text:
        template = lookup_meal_template(user_id, text)
        if template:
            print(f"📋 TEMPLATE MATCH: Using template '{template.get('name')}'")
            return template.get("ingredients", []), "template", 0.95
    
    # Strategy 3: Check brand database
    if HYBRID_PARSING_ENABLED and USE_BRAND_DATABASE and text:
        brand = detect_brand_in_text(text)
        if brand:
            # Search for the item in brand database
            brand_results = search_brand_foods(text)
            if brand_results:
                brand_food = brand_results[0]
                print(f"🏪 BRAND MATCH: Using {brand_food.get('brand')} - {brand_food.get('item')}")
                return brand_food.get("ingredients", []), "brand_db", 0.90
    
    # Strategy 4: Check user history (experimental)
    if HYBRID_PARSING_ENABLED and USE_HISTORY_LOOKUP and user_id and text:
        similar_meals = lookup_similar_meal_in_history(user_id, text, limit=1)
        if similar_meals:
            # This would need to fetch ingredients for the similar meal
            # For now, just log that we found a similar meal
            print(f"📚 HISTORY: Found similar meal, but not using (needs ingredients fetch)")
    
    # Strategy 5: Fall back to GPT parsing (current behavior)
    PB_URL = os.getenv("PB_URL", "http://127.0.0.1:8090")
    token = get_token()
    
    try:
        if text and image_field:
            print("🧠 GPT: Parsing both text + image...")
            ingredients_text = parse_ingredients(text)
            ingredients_image = parse_ingredients_from_image(meal, PB_URL, token)
            parsed = ingredients_text + ingredients_image
        elif text:
            print("🧠 GPT: Parsing text...")
            parsed = parse_ingredients(text)
        elif image_field:
            print("🧠 GPT: Parsing image...")
            parsed = parse_ingredients_from_image(meal, PB_URL, token)
        else:
            parsed = []
        
        # Cache the GPT result for future lookups (text-only)
        if HYBRID_PARSING_ENABLED and USE_PARSING_CACHE and text and not image_field and parsed:
            save_to_parsing_cache(text, parsed, model_used="gpt-4o-mini")
        
        return parsed, "gpt", 0.70
        
    except Exception as e:
        print(f"❌ GPT parsing failed: {e}")
        return [], "gpt", 0.0


def estimate_grams(quantity: float, unit: str) -> float:
    """Estimate weight in grams from quantity and unit."""
    if not quantity:
        quantity = 1
    if not unit:
        return quantity * 80  # default to smaller portion
    
    unit_lower = unit.lower().strip()
    multiplier = UNIT_TO_GRAMS.get(unit_lower, 80)  # default to 80g if unknown unit
    return quantity * multiplier


def calculate_macros(macros_per_100g: dict, grams: float) -> dict:
    """Scale macros from per-100g to actual amount consumed."""
    if not macros_per_100g or grams <= 0:
        return {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
    
    scale = grams / 100.0
    return {
        "calories": round(macros_per_100g.get("calories", 0) * scale, 1),
        "protein": round(macros_per_100g.get("protein", 0) * scale, 1),
        "carbs": round(macros_per_100g.get("carbs", 0) * scale, 1),
        "fat": round(macros_per_100g.get("fat", 0) * scale, 1),
    }


def enrich_meals(skip_usda=False, limit=None, since_date=None):
    """
    Parse meals and store ingredients.
    
    Args:
        skip_usda: If True, skip USDA nutrition lookup (faster, Level 1 MVP)
        limit: Max number of meals to process (useful for testing)
        since_date: Only process meals after this date (ISO format, e.g. '2026-01-24')
    """
    meals = fetch_unparsed_meals(since_date=since_date)
    
    if limit:
        meals = meals[:limit]
        print(f"🔢 Limited to {limit} meals")
    
    if not meals:
        print("✨ All meals already parsed!")
        return
    
    PB_URL = os.getenv("PB_URL", "http://127.0.0.1:8090")
    token = get_token()
    
    processed = 0
    errors = 0

    # Track parsing stats for Tier 4 metrics
    stats = {"cache_hits": 0, "template_hits": 0, "brand_hits": 0, "gpt_calls": 0, "learned_corrections": 0}
    
    for meal in meals:
        text = (meal.get("text") or "").strip()
        image_field = meal.get("image")

        # Skip only if both missing
        if not text and not image_field:
            continue

        print(f"\n{'='*50}")
        print(f"Meal: {text or '[Image only]'}")
        print(f"ID: {meal['id']} | Time: {meal.get('timestamp', 'N/A')}")

        # Step 1: Parse ingredients (hybrid or GPT-only based on feature flag)
        user_id = meal.get("user")  # May be None for anonymous meals
        
        if HYBRID_PARSING_ENABLED:
            print(f"🔄 Using HYBRID parsing (cache={USE_PARSING_CACHE}, brands={USE_BRAND_DATABASE}, templates={USE_MEAL_TEMPLATES})")
            parsed, parsing_strategy, confidence = hybrid_parse(meal, user_id)
            
            # Track stats
            if parsing_strategy == "cached":
                stats["cache_hits"] += 1
            elif parsing_strategy == "template":
                stats["template_hits"] += 1
            elif parsing_strategy == "brand_db":
                stats["brand_hits"] += 1
            else:
                stats["gpt_calls"] += 1
        else:
            # Original GPT-only parsing
            try:
                if text and image_field:
                    print("🧠 Parsing both text + image...")
                    ingredients_text = parse_ingredients(text)
                    ingredients_image = parse_ingredients_from_image(meal, PB_URL, token)
                    parsed = ingredients_text + ingredients_image
                elif text:
                    print("🧠 Parsing text...")
                    parsed = parse_ingredients(text)
                elif image_field:
                    print("🧠 Parsing image...")
                    parsed = parse_ingredients_from_image(meal, PB_URL, token)
                else:
                    parsed = []
                parsing_strategy = "gpt"
                confidence = 0.70
                stats["gpt_calls"] += 1
            except Exception as e:
                print(f"❌ GPT parsing failed: {e}")
                errors += 1
                continue

        print(f"→ Parsed {len(parsed)} ingredients: {[i.get('name', i) if isinstance(i, dict) else i for i in parsed]}")

        # Step 2: Store ingredients
        for ing in parsed:
            if ing["name"].lower() in BANNED_INGREDIENTS:
                print(f"⏭️  Skipped banned: {ing['name']}")
                continue

            ing = normalize_quantity(ing)
            
            # Track original name for learning metadata
            original_name = ing["name"]
            learned_correction = None
            
            # TIER 2: Check if we've learned a correction for this ingredient
            if user_id:
                learned = check_learned_correction(ing["name"], user_id)
                if learned.get("should_correct"):
                    learned_correction = learned
                    old_name = ing["name"]
                    ing["name"] = learned["corrected_name"]
                    if learned.get("corrected_quantity"):
                        ing["quantity"] = learned["corrected_quantity"]
                    if learned.get("corrected_unit"):
                        ing["unit"] = learned["corrected_unit"]
                    print(f"   🧠 LEARNED: '{old_name}' → '{ing['name']}' ({learned['reason']})")
                    stats["learned_corrections"] += 1
            
            # USDA lookup (optional for MVP)
            usda = None
            macros = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
            
            if not skip_usda:
                try:
                    usda = None
                    if user_id:
                        pantry_match = lookup_pantry_match(user_id, ing["name"])
                        if pantry_match and pantry_match.get("usdaCode"):
                            usda = usda_lookup_by_fdc_id(pantry_match["usdaCode"])
                            if usda:
                                print(f"   🏪 Pantry match: using USDA for '{ing['name']}'")
                    if not usda:
                        usda = usda_lookup(ing["name"])
                    if usda and usda.get("macros_per_100g"):
                        # Calculate actual macros based on quantity eaten
                        grams = estimate_grams(ing.get("quantity", 1), ing.get("unit", "serving"))
                        macros = calculate_macros(usda["macros_per_100g"], grams)
                        print(f"   📊 {ing['name']}: {grams:.0f}g → {macros['calories']:.0f} cal, {macros['protein']:.0f}g protein")
                except Exception as e:
                    print(f"⚠️  USDA lookup failed for {ing['name']}: {e}")
            
            meal_timestamp = meal.get("timestamp")

            # Get category from GPT response (default to "food" for backward compatibility)
            category = ing.get("category", "food")
            
            # Build parsing metadata for transparency
            parsing_metadata = {
                "originalInput": original_name,
                "resolvedTo": ing["name"],
                "resolvedVia": "learned_correction" if learned_correction else ("usda" if usda else "gpt"),
            }
            if learned_correction:
                parsing_metadata["learnedFrom"] = {
                    "timesCorrected": learned_correction.get("times_corrected", 0),
                    "confidence": learned_correction.get("confidence", 0),
                    "reason": learned_correction.get("reason", "")
                }
            
            ingredient = {
                "mealId": meal["id"],
                "name": ing["name"],
                "quantity": ing.get("quantity"),
                "unit": ing.get("unit"),
                "category": category,
                "source": "learned" if learned_correction else ("usda" if usda else "gpt"),
                "usdaCode": usda["usdaCode"] if usda else None,
                "nutrition": usda.get("nutrition", []) if usda else [],
                "macros": macros,
                "rawGPT": ing,
                "rawUSDA": usda or {},
                "timestamp": meal_timestamp,
                "parsingMetadata": parsing_metadata,
            }

            try:
                result = insert_ingredient(ingredient)
                print(f"✅ {result['name']} ({ing.get('quantity')} {ing.get('unit')})")
                if user_id and is_branded_or_specific(ing["name"]):
                    try:
                        add_to_pantry(
                            user_id,
                            ingredient["name"],
                            usda_code=ingredient.get("usdaCode"),
                            nutrition=ingredient.get("nutrition"),
                            source="parse",
                        )
                        print(f"   🏪 Added to pantry: {ing['name']}")
                    except Exception as pe:
                        print(f"   ⚠️ Could not add to pantry: {pe}")
            except Exception as e:
                print(f"❌ Failed to insert {ing['name']}: {e}")
                errors += 1
        
        processed += 1

    print(f"\n{'='*50}")
    print(f"🏁 Done! Processed {processed} meals, {errors} errors")
    
    # Show learning stats (always)
    if stats["learned_corrections"] > 0:
        print(f"\n🧠 Learning Stats:")
        print(f"   Learned corrections applied: {stats['learned_corrections']}")
    
    # Tier 4: Show hybrid parsing stats
    if HYBRID_PARSING_ENABLED:
        total = stats["cache_hits"] + stats["template_hits"] + stats["brand_hits"] + stats["gpt_calls"]
        if total > 0:
            gpt_reduction = 100 * (1 - stats["gpt_calls"] / total) if total > 0 else 0
            print(f"\n📊 Tier 4 Hybrid Parsing Stats:")
            print(f"   Cache hits:    {stats['cache_hits']}")
            print(f"   Template hits: {stats['template_hits']}")
            print(f"   Brand hits:    {stats['brand_hits']}")
            print(f"   GPT calls:     {stats['gpt_calls']}")
            print(f"   GPT reduction: {gpt_reduction:.1f}%")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse meals into ingredients")
    parser.add_argument("--skip-usda", action="store_true", 
                        help="Skip USDA nutrition lookup (faster)")
    parser.add_argument("--limit", type=int, 
                        help="Max meals to process")
    parser.add_argument("--since", type=str,
                        help="Only process meals after this date (e.g. 2026-01-24)")
    parser.add_argument("--last-week", action="store_true",
                        help="Only process meals from the last 7 days")
    # Tier 4: Hybrid parsing options
    parser.add_argument("--hybrid", action="store_true",
                        help="Enable Tier 4 hybrid parsing (cache, brands, templates)")
    parser.add_argument("--no-cache", action="store_true",
                        help="Disable parsing cache lookup")
    parser.add_argument("--no-brands", action="store_true",
                        help="Disable brand database lookup")
    args = parser.parse_args()
    
    # Override feature flags from command line
    if args.hybrid:
        HYBRID_PARSING_ENABLED = True
        print("🚀 Tier 4: Hybrid parsing ENABLED")
    if args.no_cache:
        USE_PARSING_CACHE = False
    if args.no_brands:
        USE_BRAND_DATABASE = False
    
    # Calculate date for --last-week
    since_date = args.since
    if args.last_week:
        from datetime import datetime, timedelta
        since_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        print(f"📅 --last-week: processing since {since_date}")
    
    enrich_meals(skip_usda=args.skip_usda, limit=args.limit, since_date=since_date)