import os
import requests
from dotenv import load_dotenv

load_dotenv()   # make sure env vars are loaded

USDA_KEY = os.getenv("USDA_KEY")
USDA_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"


def extract_macros(nutrients: list) -> dict:
    """Extract key macros from USDA nutrient array. Values are per 100g."""
    macros = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
    
    for n in nutrients:
        name = n.get("nutrientName", "").lower()
        value = n.get("value", 0) or 0
        
        if "energy" in name and n.get("unitName") == "KCAL":
            macros["calories"] = value
        elif name == "protein":
            macros["protein"] = value
        elif "carbohydrate" in name:
            macros["carbs"] = value
        elif "total lipid" in name or name == "fat":
            macros["fat"] = value
    
    return macros


def usda_lookup(ingredient_name):
    """
    Look up nutrition data from USDA FoodData Central.
    Returns macros per 100g serving.
    """
    params = {
        "query": ingredient_name,
        "api_key": USDA_KEY,
        "pageSize": 1
    }
    r = requests.get(USDA_URL, params=params)
    r.raise_for_status()
    data = r.json()
    
    if data.get("foods"):
        f = data["foods"][0]
        raw_nutrients = f.get("foodNutrients", [])
        macros = extract_macros(raw_nutrients)
        
        return {
            "usdaCode": f["fdcId"],
            "name": f["description"],
            "nutrition": raw_nutrients,
            "macros_per_100g": macros,
            "serving_size_g": f.get("servingSize", 100),
        }
    return None
