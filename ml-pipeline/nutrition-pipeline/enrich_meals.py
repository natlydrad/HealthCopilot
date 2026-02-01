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
    # Kitchen items that slip through from images
    "knife", "fork", "spoon", "plate", "napkin", "cup", "glass", "table",
    "cutting board", "pan", "pot", "utensil", "container", "wrapper",
}


def normalize_quantity(ing):
    if not ing.get("quantity") or ing["quantity"] == 0:
        ing["quantity"] = 1
        ing["unit"] = ing.get("unit") or "serving"
    return ing


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
            if not skip_usda:
                try:
                    usda = usda_lookup(ing["name"])
                except Exception as e:
                    print(f"⚠️  USDA lookup failed for {ing['name']}: {e}")
            
            meal_timestamp = meal.get("timestamp")

            ingredient = {
                "mealId": meal["id"],
                "name": ing["name"],
                "quantity": ing.get("quantity"),
                "unit": ing.get("unit"),
                "source": "usda" if usda else "gpt",
                "usdaCode": usda["usdaCode"] if usda else None,
                "nutrition": usda["nutrition"] if usda else {},
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