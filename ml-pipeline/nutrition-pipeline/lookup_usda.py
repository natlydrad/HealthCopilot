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


def validate_usda_match(ingredient_name: str, matched_name: str, macros: dict) -> tuple[bool, str]:
    """
    Validate if USDA match seems reasonable.
    Returns (is_valid, reason_if_invalid)
    """
    ingredient_lower = ingredient_name.lower()
    matched_lower = matched_name.lower()
    
    # Meat/protein foods that can have high protein
    meat_foods = [
        "beef", "steak", "chicken", "turkey", "pork", "lamb", "duck",
        "tuna", "salmon", "cod", "fish", "shrimp", "crab", "lobster",
        "sardines", "anchovy", "mackerel", "herring",
        "bacon", "sausage", "hot dog", "ribs", "meat", "burger", "patty",
        "protein powder", "whey", "casein", "isolate", "concentrate"
    ]
    
    # Low protein foods that shouldn't have high protein
    low_protein_foods = [
        "broth", "soup", "stock", "tea", "coffee", "water", "juice",
        "matcha", "green tea", "herbal", "spice", "seasoning",
        "flour", "sugar", "oil", "butter", "cream", "milk",  # milk is ~3g/100g
        "powder"  # most powders (matcha, cocoa, etc.) are low protein
    ]
    
    # Very low protein foods (<5g per 100g expected)
    very_low_protein = ["broth", "soup", "stock", "tea", "coffee", "water", "juice", "matcha"]
    
    protein_per_100g = macros.get("protein", 0)
    
    # Check 1: Very strict for very low protein foods (broth, tea, etc.)
    is_very_low_protein = any(food in ingredient_lower for food in very_low_protein)
    if is_very_low_protein and protein_per_100g > 10:
        return False, f"Suspicious: {ingredient_name} matched to {matched_name} with {protein_per_100g:.1f}g protein/100g (expected <10g for beverages/broth)"
    
    # Check 2: Non-meat foods shouldn't exceed 15g per 100g
    is_meat = any(food in ingredient_lower for food in meat_foods)
    is_low_protein_food = any(food in ingredient_lower for food in low_protein_foods)
    
    if not is_meat and protein_per_100g > 15:
        return False, f"Suspicious: {ingredient_name} matched to {matched_name} with {protein_per_100g:.1f}g protein/100g (non-meat expected <15g)"
    
    # Check 3: Meat foods shouldn't exceed 40g per 100g (unless it's pure protein powder)
    is_protein_powder = any(p in ingredient_lower for p in ["protein powder", "whey", "casein", "isolate", "concentrate"])
    if is_meat and not is_protein_powder and protein_per_100g > 40:
        return False, f"Suspicious: {ingredient_name} matched to {matched_name} with {protein_per_100g:.1f}g protein/100g (meat expected <40g)"
    
    # Check 3: Name mismatch (e.g., "bone broth" matching to "beef")
    # Simple check: if ingredient has a modifier, matched should too
    if "bone" in ingredient_lower and "bone" not in matched_lower:
        if protein_per_100g > 15:
            return False, f"Name mismatch: '{ingredient_name}' matched to '{matched_name}' with high protein"
    
    return True, ""


def usda_lookup(ingredient_name):
    """
    Look up nutrition data from USDA FoodData Central.
    Returns macros per 100g serving, or None if match seems invalid.
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
        matched_name = f["description"]
        
        # Validate the match
        is_valid, reason = validate_usda_match(ingredient_name, matched_name, macros)
        if not is_valid:
            print(f"⚠️  Rejected USDA match: {reason}")
            return None
        
        return {
            "usdaCode": f["fdcId"],
            "name": matched_name,
            "nutrition": raw_nutrients,
            "macros_per_100g": macros,
            "serving_size_g": f.get("servingSize", 100),
        }
    return None
