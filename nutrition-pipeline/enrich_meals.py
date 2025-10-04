from pb_client import fetch_meals, insert_ingredient
from parser_gpt import parse_ingredients

def enrich_meals():
    meals = fetch_meals()
    for meal in meals:
        # Skip meals with no text
        if not meal.get("text"):
            continue

        ing_list = parse_ingredients(meal["text"])
        print(f"Meal: {meal['text']} → Parsed: {ing_list}")  # debug print

        for ing in ing_list:
            ingredient = {
                "mealId": meal["id"],
                "name": ing.get("name"),
                "quantity": ing.get("quantity"),
                "unit": ing.get("unit"),
                "source": "gpt",
                "usdaCode": None,
                "nutrition": {},      # leave empty for now
                "rawResponse": {"parser": "gpt"}
            }
            result = insert_ingredient(ingredient)
            print("Inserted:", result["id"], result["name"])

if __name__ == "__main__":
    enrich_meals()
