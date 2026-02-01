from pb_client import fetch_unparsed_meals, insert_ingredient, get_token
from parser_gpt import parse_ingredients, parse_ingredients_from_image
from lookup_usda import usda_lookup
import os
import argparse

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

    for meal in meals:
        text = (meal.get("text") or "").strip()
        image_field = meal.get("image")

        # Skip only if both missing
        if not text and not image_field:
            continue

        print(f"\n{'='*50}")
        print(f"Meal: {text or '[Image only]'}")
        print(f"ID: {meal['id']} | Time: {meal.get('timestamp', 'N/A')}")

        # Step 1: GPT parsing
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
        except Exception as e:
            print(f"❌ GPT parsing failed: {e}")
            errors += 1
            continue

        print(f"→ Parsed {len(parsed)} ingredients: {[i['name'] for i in parsed]}")

        # Step 2: Store ingredients
        for ing in parsed:
            if ing["name"].lower() in BANNED_INGREDIENTS:
                print(f"⏭️  Skipped banned: {ing['name']}")
                continue

            ing = normalize_quantity(ing)
            
            # USDA lookup (optional for MVP)
            usda = None
            macros = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
            
            if not skip_usda:
                try:
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
            
            ingredient = {
                "mealId": meal["id"],
                "name": ing["name"],
                "quantity": ing.get("quantity"),
                "unit": ing.get("unit"),
                "category": category,
                "source": "usda" if usda else "gpt",
                "usdaCode": usda["usdaCode"] if usda else None,
                "nutrition": usda.get("nutrition", []) if usda else [],
                "macros": macros,
                "rawGPT": ing,
                "rawUSDA": usda or {},
                "timestamp": meal_timestamp,
            }

            try:
                result = insert_ingredient(ingredient)
                print(f"✅ {result['name']} ({ing.get('quantity')} {ing.get('unit')})")
            except Exception as e:
                print(f"❌ Failed to insert {ing['name']}: {e}")
                errors += 1
        
        processed += 1

    print(f"\n{'='*50}")
    print(f"🏁 Done! Processed {processed} meals, {errors} errors")


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
    args = parser.parse_args()
    
    # Calculate date for --last-week
    since_date = args.since
    if args.last_week:
        from datetime import datetime, timedelta
        since_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        print(f"📅 --last-week: processing since {since_date}")
    
    enrich_meals(skip_usda=args.skip_usda, limit=args.limit, since_date=since_date)