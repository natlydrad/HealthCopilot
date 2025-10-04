from pb_client import fetch_meals, insert_ingredient
from parser_gpt import parse_ingredients
from lookup_usda import usda_lookup

# Dish-level junk to ignore
BANNED_INGREDIENTS = {"smoothie", "salad", "sandwich", "bowl", "dish"}

def normalize_quantity(ing):
    """If GPT leaves quantity empty, assume 1 serving by default."""
    if not ing.get("quantity") or ing["quantity"] == 0:
        ing["quantity"] = 1
        ing["unit"] = ing.get("unit") or "serving"
    return ing

def enrich_meals():
    meals = fetch_meals()

    for meal in meals:
        if not meal.get("text"):
            continue

        # 🧠 Step 1: GPT parse
        raw_gpt = parse_ingredients(meal["text"])
        print(f"\nMeal: {meal['text']} → GPT Parsed: {raw_gpt}")

        for ing in raw_gpt:
            # skip junk terms
            if ing["name"].lower() in BANNED_INGREDIENTS:
                continue

            ing = normalize_quantity(ing)

            # 🧠 Step 2: USDA lookup
            usda = usda_lookup(ing["name"])

            ingredient = {
                "mealId": meal["id"],
                "name": ing["name"],
                "quantity": ing.get("quantity"),
                "unit": ing.get("unit"),
                "source": "usda" if usda else "gpt",
                "usdaCode": usda["usdaCode"] if usda else None,
                "nutrition": usda["nutrition"] if usda else {},
                # 🗄️ store raw outputs for auditability
                "rawGPT": ing,
                "rawUSDA": usda or {}
            }

            result = insert_ingredient(ingredient)
            print("✅ Inserted:", result["id"], result["name"])

if __name__ == "__main__":
    enrich_meals()
