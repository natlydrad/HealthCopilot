from pb_client import fetch_meals, insert_ingredient, get_token
from parser_gpt import parse_ingredients, parse_ingredients_from_image
from lookup_usda import usda_lookup
import os

BANNED_INGREDIENTS = {"smoothie", "salad", "sandwich", "bowl", "dish"}

def normalize_quantity(ing):
    if not ing.get("quantity") or ing["quantity"] == 0:
        ing["quantity"] = 1
        ing["unit"] = ing.get("unit") or "serving"
    return ing


def enrich_meals():
    meals = fetch_meals()
    PB_URL = os.getenv("PB_URL", "http://127.0.0.1:8090")
    token = get_token()

    for meal in meals:
        text = (meal.get("text") or "").strip()
        image_field = meal.get("image")

        # Skip only if both missing
        if not text and not image_field:
            continue

        print(f"\nMeal: {text or '[Image only]'}")

        # 🧠 Step 1: GPT parsing
        if text and image_field:
            print("🧠 Parsing both text + image...")
            ingredients_text = parse_ingredients(text)
            ingredients_image = parse_ingredients_from_image(meal, PB_URL, token)
            parsed = ingredients_text + ingredients_image
        elif text:
            parsed = parse_ingredients(text)
        elif image_field:
            print("🧠 Parsing from image...")
            parsed = parse_ingredients_from_image(meal, PB_URL, token)
        else:
            parsed = []

        print(f"→ GPT Parsed: {parsed}")

        # 🧠 Step 2: USDA + insert
        for ing in parsed:
            if ing["name"].lower() in BANNED_INGREDIENTS:
                continue

            ing = normalize_quantity(ing)
            usda = usda_lookup(ing["name"])

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
            }

            result = insert_ingredient(ingredient)
            print("✅ Inserted:", result["id"], result["name"])


if __name__ == "__main__":
    enrich_meals()