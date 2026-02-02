import os
import requests
from dotenv import load_dotenv

load_dotenv()   # make sure env vars are loaded

USDA_KEY = os.getenv("USDA_KEY")
USDA_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"


# Unit to grams conversion table
# These are approximate but reasonable defaults
UNIT_TO_GRAMS = {
    # Weight units
    "oz": 28.35,
    "ounce": 28.35,
    "ounces": 28.35,
    "g": 1.0,
    "gram": 1.0,
    "grams": 1.0,
    "lb": 453.6,
    "pound": 453.6,
    "pounds": 453.6,
    "kg": 1000.0,
    
    # Volume units (approximate for typical foods)
    "cup": 240.0,
    "cups": 240.0,
    "tbsp": 15.0,
    "tablespoon": 15.0,
    "tablespoons": 15.0,
    "tsp": 5.0,
    "teaspoon": 5.0,
    "teaspoons": 5.0,
    "ml": 1.0,  # close enough for most foods
    "fl oz": 30.0,
    "fluid ounce": 30.0,
    
    # Count units - these need context, use reasonable defaults
    "piece": 100.0,  # default, will be overridden by serving_size if available
    "pieces": 100.0,
    "slice": 30.0,   # bread slice ~30g
    "slices": 30.0,
    "egg": 50.0,
    "eggs": 50.0,
    "pill": 1.0,     # supplements - negligible weight
    "pills": 1.0,
    "capsule": 1.0,
    "capsules": 1.0,
    "serving": 100.0,  # default to 100g if no other info
    "servings": 100.0,
}


def convert_to_grams(quantity: float, unit: str, serving_size_g: float = 100.0) -> float:
    """
    Convert a quantity + unit to grams.
    
    Args:
        quantity: The numeric amount (e.g., 4)
        unit: The unit string (e.g., "oz")
        serving_size_g: USDA serving size in grams (used for "piece"/"serving" units)
    
    Returns:
        Weight in grams
    """
    unit_lower = unit.lower().strip() if unit else "serving"
    
    # Special handling for serving/piece - use USDA serving size
    if unit_lower in ("serving", "servings", "piece", "pieces"):
        return quantity * serving_size_g
    
    # Look up conversion factor
    grams_per_unit = UNIT_TO_GRAMS.get(unit_lower, 100.0)  # default 100g if unknown
    
    return quantity * grams_per_unit


def scale_nutrition(nutrients: list, quantity: float, unit: str, serving_size_g: float = 100.0) -> list:
    """
    Scale USDA nutrition values (per 100g) to the actual portion size.
    
    Args:
        nutrients: List of nutrient dicts from USDA (values per 100g)
        quantity: Amount of food
        unit: Unit of measurement
        serving_size_g: USDA serving size for this food
    
    Returns:
        New list with scaled nutrient values
    """
    grams = convert_to_grams(quantity, unit, serving_size_g)
    scale_factor = grams / 100.0  # USDA data is per 100g
    
    print(f"   📊 Scaling: {quantity} {unit} = {grams:.1f}g (scale factor: {scale_factor:.2f}x)")
    
    scaled = []
    for n in nutrients:
        scaled_nutrient = n.copy()
        if "value" in scaled_nutrient and scaled_nutrient["value"] is not None:
            scaled_nutrient["value"] = round(scaled_nutrient["value"] * scale_factor, 2)
        scaled.append(scaled_nutrient)
    
    return scaled


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
    print(f"🔍 USDA lookup for: '{ingredient_name}'")
    print(f"   API key present: {bool(USDA_KEY)} (length: {len(USDA_KEY) if USDA_KEY else 0})")
    
    if not USDA_KEY:
        print("   ❌ ERROR: USDA_KEY environment variable is not set!")
        return None
    
    params = {
        "query": ingredient_name,
        "api_key": USDA_KEY,
        "pageSize": 1
    }
    
    try:
        r = requests.get(USDA_URL, params=params)
        print(f"   Response status: {r.status_code}")
        
        if r.status_code != 200:
            print(f"   ❌ USDA API error: {r.status_code} - {r.text[:200]}")
            return None
            
        data = r.json()
        foods = data.get("foods", [])
        print(f"   Results found: {len(foods)}")
        
        if foods:
            f = foods[0]
            raw_nutrients = f.get("foodNutrients", [])
            macros = extract_macros(raw_nutrients)
            matched_name = f["description"]
            
            print(f"   ✅ Matched: '{matched_name}' (fdcId: {f['fdcId']})")
            print(f"   Macros: {macros}")
            
            # Validate the match
            is_valid, reason = validate_usda_match(ingredient_name, matched_name, macros)
            if not is_valid:
                print(f"   ⚠️ Rejected USDA match: {reason}")
                return None
            
            return {
                "usdaCode": f["fdcId"],
                "name": matched_name,
                "nutrition": raw_nutrients,
                "macros_per_100g": macros,
                "serving_size_g": f.get("servingSize", 100),
            }
        else:
            print(f"   ⚠️ No USDA results for '{ingredient_name}'")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"   ❌ USDA request failed: {e}")
        return None
    except Exception as e:
        print(f"   ❌ USDA lookup error: {e}")
        return None
