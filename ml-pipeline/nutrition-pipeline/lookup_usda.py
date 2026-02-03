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
    
    # Count units - food-specific defaults when ingredient name is known (see get_piece_grams)
    "piece": 50.0,   # generic fallback
    "pieces": 50.0,
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


# Food-specific grams per piece (when unit is "piece"/"pieces")
# USDA often returns 100g as "serving" which inflates piece counts 2-3x
PIECE_GRAMS_BY_FOOD = {
    "chicken wing": 30, "chicken wings": 30, "wing": 30, "wings": 30,
    "chicken breast": 120, "chicken breasts": 120,  # ~4oz
    "wingette": 25, "drummette": 25, "wingettes": 25, "drummettes": 25,
    "egg": 50, "eggs": 50,
    "bread slice": 30, "slice of bread": 30, "slice": 30,
    "nugget": 20, "nuggets": 20, "chicken nugget": 20, "chicken nuggets": 20,
    "meatball": 30, "meatballs": 30,
    "cookie": 15, "cookies": 15,
    "apple": 180, "apples": 180,
    "banana": 120, "bananas": 120,
    "orange": 130, "oranges": 130,
}


def get_piece_grams(ingredient_name: str) -> float | None:
    """Return food-specific grams per piece, or None for generic default."""
    name_lower = (ingredient_name or "").lower().strip()
    for key, grams in PIECE_GRAMS_BY_FOOD.items():
        if key in name_lower:
            return float(grams)
    return None


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


def validate_scaled_calories(
    ingredient_name: str, quantity: float, unit: str, scaled_calories: float
) -> tuple[bool, str]:
    """
    Sanity check: reject scaled calories that are absurd for this portion.
    Returns (is_valid, reason_if_invalid).
    E.g. 6 small chicken wings should be ~200-400 cal, not 1500.
    """
    if scaled_calories <= 0:
        return True, ""
    name_lower = ingredient_name.lower()

    # Per-piece/per-unit upper bounds (calories) - generous but catch 3x+ overestimates
    piece_bounds = {
        "chicken wing": (35, 80),   # wingette/drummette: ~48 cal each
        "wing": (35, 80),
        "chicken breast": (100, 280),  # ~165 cal per 4oz breast
        "chicken": (80, 280),   # wing ~50, breast ~165
        "steak": (150, 450),    # 4-6oz beef ~250-350
        "beef": (100, 450),
        "egg": (60, 120),
        "nugget": (40, 100),
        "meatball": (50, 150),
        "cookie": (30, 120),
        "orange": (35, 80),   # ~45-60 cal each
        "apple": (50, 120),   # ~95 cal each
        "banana": (70, 130),  # ~105 cal each
    }
    unit_lower = (unit or "").lower()
    if unit_lower in ("piece", "pieces") and quantity > 0:
        for key, (lo, hi) in piece_bounds.items():
            if key in name_lower:
                per_piece = scaled_calories / quantity
                if per_piece > hi:
                    return False, f"Scaled {scaled_calories:.0f} cal for {quantity} {key} = {per_piece:.0f} cal/piece (expected <{hi})"
                break

    # Whole-meal sanity: single ingredient >1200 cal is suspect (unless bulk)
    if quantity <= 10 and unit_lower in ("piece", "pieces", "oz", "g", "cup", "cups"):
        if scaled_calories > 1200:
            return False, f"Scaled {scaled_calories:.0f} cal seems too high for {quantity} {unit} of {ingredient_name[:40]}"
    return True, ""


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
        "pageSize": 10,
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
            ingredient_lower = ingredient_name.lower()
            # Composite foods (sandwich, salad, wrap, etc.) should have carbs — prefer matches that do
            is_composite = any(w in ingredient_lower for w in [
                "sandwich", "wrap", "burrito", "taco", "burger", "pizza",
                "salad", "bowl", "plate", "combo", "meal"
            ])
            
            best = None
            for f in foods:
                raw_nutrients = f.get("foodNutrients", [])
                macros = extract_macros(raw_nutrients)
                matched_name = f["description"]
                is_valid, reason = validate_usda_match(ingredient_name, matched_name, macros)
                if not is_valid:
                    continue
                if best is None:
                    best = (f, macros, matched_name, raw_nutrients)
                    continue
                # Prefer composite matches with carbs when ingredient suggests composite
                if is_composite and macros.get("carbs", 0) > 0 and best[1].get("carbs", 0) == 0:
                    best = (f, macros, matched_name, raw_nutrients)
                    break
                if is_composite and macros.get("carbs", 0) > best[1].get("carbs", 0):
                    best = (f, macros, matched_name, raw_nutrients)
            
            if best:
                f, macros, matched_name, raw_nutrients = best
                print(f"   ✅ Matched: '{matched_name}' (fdcId: {f['fdcId']})")
                print(f"   Macros: {macros}")
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


def _alternative_usda_queries(ingredient_name: str) -> list[str]:
    """
    Generate alternative USDA search queries for when the first match fails validation.
    E.g. "orange" may return juice or dried; "orange raw" returns the fruit.
    """
    name = (ingredient_name or "").strip()
    if not name:
        return []
    queries = [name]
    lower = name.lower()
    # Fruits/veg: add "raw" to get whole fruit, not juice/dried/canned
    raw_foods = ["orange", "oranges", "apple", "apples", "banana", "bananas", "grape", "grapes",
                 "strawberry", "strawberries", "blueberry", "blueberries", "peach", "peaches",
                 "carrot", "carrots", "broccoli", "celery", "cucumber", "tomato", "tomatoes",
                 "lettuce", "spinach", "pepper", "peppers", "melon", "watermelon", "mango", "mangoes"]
    if any(f in lower for f in raw_foods):
        # Avoid duplicate: if name already has "raw", skip
        if "raw" not in lower and "juice" not in lower and "dried" not in lower:
            base = name.split(",")[0].strip()
            queries.append(f"{base} raw")
            if not base.endswith("s") and base.lower() not in ("grape", "mango", "peach", "melon"):
                queries.append(f"{base}s raw")
    # Meats: add "raw" to get plain meat, not fried/breaded (which inflates calories)
    meat_terms = ["chicken", "beef", "steak", "pork", "turkey", "lamb", "salmon", "tuna", "fish"]
    if any(m in lower for m in meat_terms):
        if "raw" not in lower and "fried" not in lower and "breaded" not in lower and "battered" not in lower:
            base = name.split(",")[0].strip()
            if "wing" in lower:
                queries.append("chicken wings raw")
                queries.append("chicken wing raw")
            elif "chicken" in lower and "breast" not in lower:
                queries.append("chicken breast raw")
            queries.append(f"{base} raw")
    return queries


def usda_lookup_valid_for_portion(
    ingredient_name: str, quantity: float, unit: str
) -> dict | None:
    """
    Try USDA lookup with original + alternative queries; return first result that
    passes validate_scaled_calories. Use when user flags poor USDA match - prefer
    a better USDA result over GPT estimate.
    """
    queries = _alternative_usda_queries(ingredient_name)
    seen_fdc = set()
    for q in queries:
        usda = usda_lookup(q)
        if not usda:
            continue
        fdc_id = usda.get("usdaCode")
        if fdc_id and fdc_id in seen_fdc:
            continue
        if fdc_id:
            seen_fdc.add(fdc_id)
        # Scale and validate
        scaled = scale_nutrition(
            usda.get("nutrition", []),
            quantity,
            unit,
            usda.get("serving_size_g", 100.0),
        )
        cal_val = next((n.get("value", 0) for n in scaled if n.get("nutrientName") == "Energy"), 0)
        is_valid, reason = validate_scaled_calories(ingredient_name, quantity, unit, cal_val)
        if is_valid:
            print(f"   ✅ Found valid USDA match for portion: '{usda.get('name')}' ({cal_val:.0f} cal)")
            return usda
        print(f"   ⏭️ USDA match '{usda.get('name')}' failed validation: {reason}")
    return None
