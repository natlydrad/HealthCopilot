from pb_client import fetch_meals, insert_ingredient
from parser_gpt import parse_ingredients
from lookup_usda import usda_lookup

def enrich_meals():
    meals = fetch_meals()
    for meal in meals:
        ing_list = parse_ingredients(meal["text"])
        for ing in ing_list:
            usda = usda_lookup(ing["name"])
            ingredient = {
                "mealId": meal["id"],
                "name": ing["name"],
                "quantity": ing.get("quantity"),
                "unit": ing.get("unit"),
                "source": "usda" if usda else "gpt",
                "usdaCode": usda["usdaCode"] if usda else None,
                "nutrition": usda["nutrition"] if usda else {},
                "rawResponse": usda or {}
            }
            insert_ingredient(ingredient)

if __name__ == "__main__":
    enrich_meals()
