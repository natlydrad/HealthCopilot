import os
import requests
from dotenv import load_dotenv

load_dotenv()   # make sure env vars are loaded

USDA_KEY = os.getenv("USDA_KEY")
USDA_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"

def usda_lookup(ingredient_name):
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
        return {
            "usdaCode": f["fdcId"],
            "name": f["description"],
            "nutrition": f.get("foodNutrients", [])
        }
    return None
