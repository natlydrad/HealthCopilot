import os
import re
import requests
from dotenv import load_dotenv

load_dotenv()   # make sure env vars are loaded

USDA_KEY = os.getenv("USDA_KEY")
USDA_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
USDA_FOOD_URL = "https://api.nal.usda.gov/fdc/v1/food"


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
# USDA does not standardize piece weights—each food has its own serving. We use curated values.
# Reference: USDA FDC, typical retail/recipe sizes
PIECE_GRAMS_BY_FOOD = {
    "chicken wing": 30, "chicken wings": 30, "wing": 30, "wings": 30,
    "chicken breast": 120, "chicken breasts": 120,  # ~4oz
    "wingette": 25, "drummette": 25, "wingettes": 25, "drummettes": 25,
    "egg": 50, "eggs": 50,
    "bread slice": 30, "slice of bread": 30, "slice": 30, "slices": 30,
    "bacon": 18, "bacon slice": 18, "bacon strip": 18,  # cooked ~15-20g/slice
    "nugget": 20, "nuggets": 20, "chicken nugget": 20, "chicken nuggets": 20,
    "meatball": 30, "meatballs": 30,
    "cookie": 15, "cookies": 15,
    "apple": 180, "apples": 180,
    "banana": 120, "bananas": 120,
    "orange": 130, "oranges": 130,
    "tomato": 120, "tomatoes": 120,
    "avocado": 150, "avocados": 150,
    "potato": 170, "potatoes": 170,
    "onion": 110, "onions": 110,
    "carrot": 60, "carrots": 60,
    "strawberry": 12, "strawberries": 12,
    "grape": 5, "grapes": 5,
    "blueberry": 1, "blueberries": 1,
    "raspberry": 4, "raspberries": 4,
    "blackberry": 4, "blackberries": 4,
    "muffin": 60, "muffins": 60,
    "pancake": 60, "pancakes": 60,
    "tortilla": 45, "tortillas": 45,
    "sausage": 70, "sausages": 70, "sausage link": 70, "sausage links": 70,
    "fish stick": 25, "fish sticks": 25,
    "shrimp": 15, "shrimps": 15, "large shrimp": 15,
}


def get_piece_grams(ingredient_name: str) -> float | None:
    """Return food-specific grams per piece, or None for generic default."""
    name_lower = (ingredient_name or "").lower().strip()
    for key, grams in PIECE_GRAMS_BY_FOOD.items():
        if key in name_lower:
            return float(grams)
    return None


def use_piece_grams_for_portion(unit_lower: str, name: str, quantity: float, piece_g: float | None) -> bool:
    """
    True when we should use get_piece_grams for serving size (countable foods).
    Unit-agnostic: if piece_g exists and quantity suggests count (1-100), use it.
    """
    if piece_g is None:
        return False
    if unit_lower in ("piece", "pieces", "count"):
        return True
    if unit_lower in ("serving", "servings") and 1 <= quantity <= 30:
        return True
    if unit_lower == (name or "").lower().strip():
        return True
    if unit_lower in PIECE_GRAMS_BY_FOOD:
        return True
    return False


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
    
    # Special handling for serving/piece/count - use USDA serving size (or piece_g when provided)
    if unit_lower in ("serving", "servings", "piece", "pieces", "count"):
        return quantity * serving_size_g
    # Unit matches countable food (e.g. "7 strawberries" with unit "strawberries") - use piece grams
    if unit_lower in PIECE_GRAMS_BY_FOOD:
        return quantity * PIECE_GRAMS_BY_FOOD[unit_lower]
    
    # Look up conversion factor
    grams_per_unit = UNIT_TO_GRAMS.get(unit_lower, 100.0)  # default 100g if unknown
    
    return quantity * grams_per_unit


def scale_nutrition(nutrients: list, quantity: float, unit: str, serving_size_g: float = 100.0, quiet: bool = False) -> list:
    """
    Scale USDA nutrition values (per 100g) to the actual portion size.
    
    Args:
        nutrients: List of nutrient dicts from USDA (values per 100g)
        quantity: Amount of food
        unit: Unit of measurement
        serving_size_g: USDA serving size for this food
        quiet: If True, do not print scaling message
    
    Returns:
        New list with scaled nutrient values
    """
    grams = convert_to_grams(quantity, unit, serving_size_g)
    scale_factor = grams / 100.0  # USDA data is per 100g
    
    if not quiet:
        print(f"   📊 Scaling: {quantity} {unit} = {grams:.1f}g (scale factor: {scale_factor:.2f}x)")
    
    scaled = []
    for n in nutrients:
        scaled_nutrient = n.copy()
        if "value" in scaled_nutrient and scaled_nutrient["value"] is not None:
            scaled_nutrient["value"] = round(scaled_nutrient["value"] * scale_factor, 2)
        scaled.append(scaled_nutrient)
    
    return scaled


def extract_macros(nutrients: list) -> dict:
    """Extract key macros from USDA nutrient array. Values are per 100g. Handles both value and amount (nested FDC format)."""
    macros = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
    
    for n in nutrients:
        name_raw = n.get("nutrientName") or (n.get("nutrient") or {}).get("name")
        name = (str(name_raw) if name_raw else "").lower()
        value = n.get("value")
        if value is None and "amount" in n:
            try:
                value = float(n["amount"])
            except (TypeError, ValueError):
                value = 0
        value = (value or 0) if value is not None else 0
        unit = (n.get("unitName") or (n.get("nutrient") or {}).get("unitName") or "").upper()
        
        if "energy" in name:
            if unit == "KCAL" or unit == "CAL":
                macros["calories"] = value
            elif unit == "KJ" and value > 0:
                macros["calories"] = round(value / 4.184, 1)
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
        "grape": (1, 15), "grapes": (1, 15),
        "strawberry": (2, 15), "strawberries": (2, 15),
        "blueberry": (1, 10), "blueberries": (1, 10),
        "raspberry": (1, 10), "raspberries": (1, 10),
        "blackberry": (1, 10), "blackberries": (1, 10),
        "cherry": (2, 15), "cherries": (2, 15),
        "peach": (40, 100), "peaches": (40, 100),
        "pear": (60, 130), "pears": (60, 130),
        "plum": (20, 60), "plums": (20, 60),
        "mango": (70, 150), "mangoes": (70, 150), "mangos": (70, 150),
        "kiwi": (25, 70), "kiwis": (25, 70),
        "grapefruit": (35, 90), "grapefruits": (35, 90),
        "watermelon": (30, 150), "melon": (30, 100), "melons": (30, 100),
        "pineapple": (40, 120), "avocado": (150, 350), "avocados": (150, 350),
        "lemon": (10, 40), "lemons": (10, 40), "lime": (10, 40), "limes": (10, 40),
    }
    unit_lower = (unit or "").lower()
    # Count-like: piece/pieces/count, or unit is a piece_bounds key (e.g. strawberries, eggs), or unit matches name
    is_count_like = (
        unit_lower in ("piece", "pieces", "count")
        or unit_lower in piece_bounds
        or (quantity > 0 and quantity <= 100 and unit_lower == name_lower.strip())
    )
    if is_count_like and quantity > 0:
        for key, (lo, hi) in piece_bounds.items():
            if key in name_lower:
                per_piece = scaled_calories / quantity
                if per_piece > hi:
                    return False, f"Scaled {scaled_calories:.0f} cal for {quantity} {key} = {per_piece:.0f} cal/piece (expected <{hi})"
                break
    # "serving" with small count (e.g. 7 strawberries) — treat as count for berries/fruit
    if unit_lower == "serving" and 1 <= quantity <= 30:
        for key, (lo, hi) in piece_bounds.items():
            if key in name_lower:
                per_piece = scaled_calories / quantity
                if per_piece > hi:
                    return False, f"Scaled {scaled_calories:.0f} cal for {quantity} {key} = {per_piece:.0f} cal/serving (expected <{hi}; suggests wrong match)"
                break

    # Zero-cal drinks: black coffee, tea, water, ice, etc. — reject USDA matches with calories
    # Skip this check for meats (e.g. "steak" contains "tea" as substring)
    meat_terms = ("steak", "meat", "pork", "beef", "chicken", "turkey", "lamb", "fish")
    if any(m in name_lower for m in meat_terms):
        pass  # skip zero-cal drink check
    else:
        zero_cal_drinks = ("coffee", "tea", "espresso", "black coffee", "green tea", "herbal tea", "water", "ice")
        if any(d in name_lower for d in zero_cal_drinks):
            if unit_lower in ("oz", "cup", "cups", "serving", "servings") and quantity <= 24:
                if scaled_calories > 15:
                    return False, f"Black coffee/tea should be ~0-5 cal, not {scaled_calories:.0f}"

    # Cup-based sanity for berries and fruits (catches dried or wrong match)
    berry_fruit_terms = ("strawberry", "strawberries", "blueberry", "blueberries", "raspberry", "raspberries", "blackberry", "blackberries", "cherry", "cherries", "grape", "grapes")
    if unit_lower in ("cup", "cups") and quantity > 0 and any(t in name_lower for t in berry_fruit_terms):
        cal_per_cup = scaled_calories / quantity
        if cal_per_cup > 150:
            return False, f"Scaled {scaled_calories:.0f} cal for {quantity} cup(s) = {cal_per_cup:.0f} cal/cup (berries/fruit expected <150 cal/cup; suggests dried or wrong match)"

    # Cup-based sanity for oats and rice (catches raw when user meant cooked)
    grain_terms = ("oat", "oats", "oatmeal", "steel cut", "rice", "brown rice", "white rice")
    if unit_lower in ("cup", "cups") and quantity > 0 and any(g in name_lower for g in grain_terms):
        if "raw" not in name_lower and "dry" not in name_lower and "uncooked" not in name_lower:
            cal_per_cup = scaled_calories / quantity
            if cal_per_cup > 250:
                return False, f"Scaled {scaled_calories:.0f} cal for {quantity} cup(s) = {cal_per_cup:.0f} cal/cup (cooked oats/rice expected <250 cal/cup; likely raw when user meant cooked)"

    # Whole-meal sanity: single ingredient >1200 cal is suspect (unless bulk)
    if quantity <= 10 and unit_lower in ("piece", "pieces", "oz", "g", "cup", "cups"):
        if scaled_calories > 1200:
            return False, f"Scaled {scaled_calories:.0f} cal seems too high for {quantity} {unit} of {ingredient_name[:40]}"
    return True, ""


# Beverage/broth-type ingredients: per-serving protein should stay low (catches powder/concentrate scaled wrong)
VERY_LOW_PROTEIN_INGREDIENTS = (
    "broth", "soup", "stock", "tea", "coffee", "water", "juice", "matcha",
    "green tea", "herbal tea", "espresso", "soda", "cola", "lemonade",
)


def validate_scaled_protein(
    ingredient_name: str, scaled_nutrition: list, max_protein_g: float = 8.0
) -> tuple[bool, str]:
    """
    For beverage/broth-type ingredients, reject if scaled total protein is too high.
    Use after scaling: concentrates (e.g. matcha powder, broth paste) can have high
    protein per 100g but a normal serving should have low total protein.
    Returns (is_valid, reason_if_invalid).
    """
    name_lower = (ingredient_name or "").lower()
    if not any(f in name_lower for f in VERY_LOW_PROTEIN_INGREDIENTS):
        return True, ""
    protein_val = 0.0
    for n in scaled_nutrition or []:
        if (n.get("nutrientName") or "").strip() == "Protein":
            protein_val = float(n.get("value") or 0)
            break
    if protein_val <= max_protein_g:
        return True, ""
    return False, (
        f"Beverage/broth '{ingredient_name[:30]}' has {protein_val:.1f}g protein per portion "
        f"(expected ≤{max_protein_g}g); likely matched to concentrate/powder with wrong serving size"
    )


def _normalize_usda_nutrient(n: dict) -> dict | None:
    """
    Normalize a single USDA foodNutrient to {nutrientName, unitName, value}.
    Handles both API shapes: value/nutrientName (already flat) and amount/nutrient.name (raw FDC).
    Treats null value for one nutrient as skip (don't include); partial data still extracts.
    """
    if not n or not isinstance(n, dict):
        return None
    name = n.get("nutrientName") or (n.get("nutrient") or {}).get("name")
    unit = n.get("unitName") or (n.get("nutrient") or {}).get("unitName") or ""
    val = n.get("value")
    if val is None and "amount" in n:
        try:
            val = float(n["amount"])
        except (TypeError, ValueError):
            return None
    if name is None:
        return None
    if val is None:
        return None  # skip this nutrient, don't treat as "no data" for whole food
    return {"nutrientName": name.strip(), "unitName": (unit or "").strip(), "value": round(float(val), 2)}


def normalize_usda_food_nutrients(raw_list: list) -> list:
    """
    Normalize USDA foodNutrients (raw API or already flat) to list of {nutrientName, unitName, value}.
    Use this before scale_nutrition when the source may be raw FDC API response.
    """
    out = []
    for n in raw_list or []:
        norm = _normalize_usda_nutrient(n)
        if norm:
            out.append(norm)
    return out


def extract_caffeine_mg_per_100g(nutrients: list) -> float | None:
    """
    Extract Caffeine (mg per 100g) from USDA nutrient list (raw or normalized).
    Returns None if not present.
    """
    for n in nutrients or []:
        if not isinstance(n, dict):
            continue
        norm = _normalize_usda_nutrient(n)
        if norm and (norm.get("nutrientName") or "").strip().lower() == "caffeine":
            return float(norm.get("value", 0))
    return None


def zero_calorie_nutrition_array() -> list:
    """
    Return a nutrition array with all zero values (Energy, Protein, Carbohydrate, Total lipid, etc.)
    for use when applying common-sense zero_calories (e.g. water, ice).
    """
    return [
        {"nutrientName": "Energy", "unitName": "KCAL", "value": 0},
        {"nutrientName": "Protein", "unitName": "G", "value": 0},
        {"nutrientName": "Carbohydrate, by difference", "unitName": "G", "value": 0},
        {"nutrientName": "Total lipid (fat)", "unitName": "G", "value": 0},
        {"nutrientName": "Caffeine", "unitName": "MG", "value": 0},
    ]


# Expected calories per 100g by food category — prefer USDA matches in this range
# Format: (search_terms, (lo, hi)) — first match wins
EXPECTED_CAL_PER_100G = [
    (["soy milk", "oat milk", "almond milk", "coconut milk beverage", "cashew milk", "pea milk"], (25, 55)),
    (["milk"], (40, 65)),  # dairy milk
    (["orange juice", "apple juice", "grape juice", "cranberry juice"], (40, 55)),
    (["orange", "oranges"], (40, 55)),
    (["apple", "apples"], (45, 60)),
    (["banana", "bananas"], (85, 105)),
    (["strawberry", "strawberries"], (28, 40)),
    (["oatmeal", "oats", "steel cut oats"], (65, 95)),  # cooked
    (["rice", "brown rice", "white rice"], (110, 140)),  # cooked
    (["chicken wing", "wing", "wings"], (150, 250)),  # per 100g raw
    (["chicken breast", "chicken"], (100, 180)),
    (["egg", "eggs"], (140, 160)),
]


def get_expected_cal_range(ingredient_name: str) -> tuple[float, float] | None:
    """Return (lo, hi) expected cal/100g for this food, or None if unknown."""
    lower = (ingredient_name or "").lower()
    for terms, (lo, hi) in EXPECTED_CAL_PER_100G:
        if any(t in lower for t in terms):
            return (lo, hi)
    return None


def score_calorie_fit(cal_per_100g: float, expected_lo: float, expected_hi: float) -> float:
    """
    Lower score = better fit. 0 = inside range. Penalize distance outside.
    """
    if cal_per_100g <= 0:
        return 999.0
    mid = (expected_lo + expected_hi) / 2
    if expected_lo <= cal_per_100g <= expected_hi:
        return abs(cal_per_100g - mid)  # prefer closer to mid
    if cal_per_100g < expected_lo:
        return expected_lo - cal_per_100g + 100
    return cal_per_100g - expected_hi + 100


def _is_drink_like_query(query_lower: str) -> bool:
    """True if the query looks like a beverage (tea, coffee, matcha, soda, juice, etc.)."""
    if not query_lower:
        return False
    terms = ("tea", "coffee", "matcha", "espresso", "soda", "cola", "juice", "lemonade", "smoothie")
    return any(t in query_lower for t in terms)


def _query_implies_decaf_or_herbal(query_lower: str) -> bool:
    """True if query suggests a decaf/herbal/sleepy drink (prefer 0-caffeine match)."""
    if not query_lower:
        return False
    return any(
        x in query_lower
        for x in (
            "decaf", "herbal", "caffeine-free", "caffeine free",
            "sleepy", "sleep ", "sleepy ", "bedtime", "calm", "chamomile", "peppermint", "rooibos",
        )
    )


def _query_implies_caffeine(query_lower: str) -> bool:
    """True if query suggests a caffeinated drink (tea/coffee/matcha) without decaf/herbal/sleepy."""
    if not query_lower:
        return False
    if _query_implies_decaf_or_herbal(query_lower):
        return False
    return any(t in query_lower for t in ("tea", "coffee", "matcha", "espresso"))


_DRINK_QUERY_STOPWORDS = {"tea", "coffee", "the", "and", "with", "cup", "cups", "oz", "serving", "brewed"}


def _tea_type_mismatch(query_lower: str, matched_name: str) -> bool:
    """
    Return True if tea query should reject this match (e.g. hibiscus/raspberry/sleepy tea -> reject Oolong).
    Oolong has caffeine; hibiscus, raspberry hibiscus, sleepy/bedtime imply herbal.
    """
    if not query_lower or not matched_name:
        return False
    ml = matched_name.lower()
    if "oolong" not in ml:
        return False
    # Hibiscus/raspberry hibiscus: reject Oolong (no hibiscus in Oolong)
    if "hibiscus" in query_lower or ("raspberry" in query_lower and "tea" in query_lower):
        return True
    # Sleepy/bedtime/calm: reject Oolong (herbal tea, not caffeinated)
    if any(x in query_lower for x in ("sleepy", "bedtime", "calm")):
        return True
    return False


def _drink_match_has_query_overlap(query_lower: str, matched_name: str) -> bool:
    """
    For drink-like queries: True iff the USDA match name contains at least one
    significant word from the query. Used as the single gate for accepting a drink match.
    """
    if not query_lower or not matched_name:
        return bool(matched_name)
    query_words = set(re.findall(r"[a-z0-9]{2,}", query_lower))
    query_words -= _DRINK_QUERY_STOPWORDS
    if not query_words:
        return True
    matched_lower = (matched_name or "").lower()
    return any(w in matched_lower for w in query_words)


def _score_drink_match_for_ordering(query_lower: str, matched_name: str, raw_nutrients: list) -> float:
    """
    Minimal score for ordering drink candidates that already pass _drink_match_has_query_overlap.
    Higher = better. Prefer brewed/beverage; prefer caffeine when query implies caffeinated; prefer 0 caffeine for herbal.
    """
    if not _is_drink_like_query(query_lower):
        return 0.0
    score = 0.0
    matched_lower = (matched_name or "").lower()
    if "brewed" in matched_lower or "beverage" in matched_lower or "beverages" in matched_lower:
        score += 10.0
    caffeine = extract_caffeine_mg_per_100g(raw_nutrients or [])
    if caffeine is None:
        caffeine = 0.0
    if _query_implies_decaf_or_herbal(query_lower):
        if caffeine == 0:
            score += 12.0
        else:
            score -= 10.0
    elif _query_implies_caffeine(query_lower) and caffeine > 0:
        score += 15.0
    elif _query_implies_caffeine(query_lower) and caffeine == 0:
        score -= 5.0
    return score


def _query_implies_condiment(query_lower: str) -> bool:
    """True if query text contains condiment indicators (tbsp, sauce)."""
    if not query_lower:
        return False
    return "tbsp" in query_lower or "sauce" in query_lower


def _query_or_unit_implies_condiment(query_lower: str, unit: str | None) -> bool:
    """True when portion is condiment-like: query has tbsp/sauce OR unit is tbsp/tsp."""
    if _query_implies_condiment(query_lower):
        return True
    return _unit_implies_condiment(unit)


def _condiment_query_matched_sausage(query_lower: str, matched_name: str, unit: str | None = None) -> bool:
    """Return True if condiment portion but match is sausage/hot dog."""
    if not _query_or_unit_implies_condiment(query_lower, unit):
        return False
    ml = matched_name.lower()
    return "jumbo franks" in ml or ("franks" in ml and "sauce" not in ml and "condiment" not in ml)


def _prefer_cooked_for_meat(query_lower: str, matched_name: str) -> float:
    """Return bonus to subtract from cal_score when match is cooked and query implies cooked (meat without 'raw')."""
    meat_terms = ["chicken", "beef", "steak", "pork", "turkey", "lamb", "salmon", "tuna", "fish", "ground"]
    if not any(m in query_lower for m in meat_terms):
        return 0.0
    if "raw" in query_lower:
        return 0.0
    matched_lower = (matched_name or "").lower()
    if "cooked" in matched_lower:
        return 50.0  # prefer cooked (lower cal_score = better rank)
    return 0.0


def _prefer_sauce_for_condiment_query(query_lower: str, matched_name: str, unit: str | None = None) -> float:
    """Bonus when condiment portion (tbsp/tsp) and match is sauce/condiment form."""
    if not _query_or_unit_implies_condiment(query_lower, unit):
        return 0.0
    matched_lower = (matched_name or "").lower()
    if "sauce" in matched_lower or "condiment" in matched_lower:
        return 500.0
    return 0.0


def _prefer_cooked_for_grains(query_lower: str, matched_name: str) -> float:
    """Return bonus when query says cooked and match is cooked (e.g. cooked steel cut oats -> cooked oats not raw)."""
    if "cooked" not in (query_lower or ""):
        return 0.0
    matched_lower = (matched_name or "").lower()
    if "cooked" in matched_lower:
        return 300.0  # Strong preference so cooked oats outrank raw
    return 0.0


def _has_nutrition_data(raw_nutrients: list, macros: dict) -> bool:
    """True if the match has non-empty, non-zero nutrition data."""
    if not raw_nutrients:
        return False
    total = (macros.get("calories") or 0) + (macros.get("protein") or 0) + (macros.get("carbs") or 0) + (macros.get("fat") or 0)
    return total > 0


def _unit_implies_condiment(unit: str | None) -> bool:
    """True when unit suggests user is measuring a condiment/sauce (tbsp, tsp)."""
    if not unit:
        return False
    return unit.lower().strip() in ("tbsp", "tsp", "tablespoon", "tablespoons", "teaspoon", "teaspoons")


def _match_is_raw_whole_produce(matched_name: str) -> bool:
    """True when match looks like raw whole produce (peppers, vegetables, fruit) not sauce/dressing."""
    ml = (matched_name or "").lower()
    if "raw" not in ml:
        return False
    if any(c in ml for c in ("sauce", "dressing", "paste", "ketchup", "marinade", "condiment")):
        return False
    produce_terms = ("pepper", "peppers", "chili", "tomato", "tomatoes", "vegetable", "fruit", "onion", "carrot")
    return any(p in ml for p in produce_terms)


def validate_usda_match(
    ingredient_name: str, matched_name: str, macros: dict,
    quantity: float | None = None, unit: str | None = None
) -> tuple[bool, str]:
    """
    Validate if USDA match seems reasonable.
    Returns (is_valid, reason_if_invalid).
    When unit is provided: use unit-implies-form checks (e.g. tbsp + raw produce = reject for condiment).
    """
    # Reject USDA matches with no nutrition data (empty or all zeros)
    total_macros = (macros.get("calories") or 0) + (macros.get("protein") or 0) + (macros.get("carbs") or 0) + (macros.get("fat") or 0)
    if total_macros <= 0:
        return False, "USDA match has no nutrition data"

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
    
    # Beverage/broth/concentrates: don't reject on protein per 100g here.
    # Allow powder/concentrate matches; we validate after scaling (validate_scaled_protein).
    very_low_protein = list(VERY_LOW_PROTEIN_INGREDIENTS)
    is_very_low_protein = any(food in ingredient_lower for food in very_low_protein)

    protein_per_100g = macros.get("protein", 0)
    is_meat = any(food in ingredient_lower for food in meat_foods)
    is_low_protein_food = any(food in ingredient_lower for food in low_protein_foods)

    # Non-meat, non-beverage: shouldn't exceed 15g per 100g (beverages allowed to match concentrates)
    if not is_meat and not is_very_low_protein and protein_per_100g > 15:
        return False, f"Suspicious: {ingredient_name} matched to {matched_name} with {protein_per_100g:.1f}g protein/100g (non-meat expected <15g)"
    
    # Check 3: Meat foods shouldn't exceed 40g per 100g (unless it's pure protein powder)
    is_protein_powder = any(p in ingredient_lower for p in ["protein powder", "whey", "casein", "isolate", "concentrate"])
    if is_meat and not is_protein_powder and protein_per_100g > 40:
        return False, f"Suspicious: {ingredient_name} matched to {matched_name} with {protein_per_100g:.1f}g protein/100g (meat expected <40g)"
    
    # Condiment portion matched sausage (tbsp + franks = reject hot dogs)
    if _condiment_query_matched_sausage(ingredient_lower, matched_name, unit):
        return False, f"Condiment query '{ingredient_name}' matched sausage/hot dog '{matched_name}'"
    # Plain cabbage matched kimchi (user meant raw cabbage)
    if "cabbage" in ingredient_lower and "kimchi" not in ingredient_lower and "fermented" not in ingredient_lower:
        if "kimchi" in matched_lower:
            return False, f"Plain cabbage matched kimchi '{matched_name}'; prefer raw cabbage"
    # Unit implies form: tbsp/tsp = condiment portion; reject raw whole produce (peppers, etc.)
    if _unit_implies_condiment(unit) and _match_is_raw_whole_produce(matched_name):
        return False, f"Condiment portion (tbsp/tsp) matched raw produce '{matched_name}'; prefer sauce/condiment"
    # Check 3: Name mismatch (e.g., "bone broth" matching to "beef")
    # Simple check: if ingredient has a modifier, matched should too
    if "bone" in ingredient_lower and "bone" not in matched_lower:
        if protein_per_100g > 15:
            return False, f"Name mismatch: '{ingredient_name}' matched to '{matched_name}' with high protein"

    # Check 4: Require at least one significant word from ingredient to appear in matched name.
    # Rejects e.g. "pork shoulder steak" -> "Beverages, tea, Oolong, brewed" (no word overlap).
    words = re.findall(r"[a-z0-9]{2,}", ingredient_lower)
    stop = {"the", "and", "with", "for", "raw", "cooked", "half", "other", "same", "cup", "cups", "oz"}
    significant = [w for w in words if w not in stop]
    if significant and not any(w in matched_lower for w in significant):
        # #region agent log
        try:
            import json
            import time as _t
            _line = json.dumps({"timestamp": _t.time()*1000, "location": "lookup_usda.py:validate_no_overlap", "message": "reject_no_keyword_overlap", "data": {"ingredient_name": ingredient_name, "matched_name": matched_name}, "hypothesisId": "H5", "sessionId": "debug-session", "runId": "post-fix"}) + "\n"
            open("/Users/natalieradu/Desktop/HealthCopilot/.cursor/debug.log", "a").write(_line)
        except Exception:
            pass
        # #endregion
        return False, f"Name mismatch: no keyword overlap between '{ingredient_name}' and '{matched_name}'"

    return True, ""


def usda_lookup(ingredient_name: str, quantity: float | None = None, unit: str | None = None):
    """
    Look up nutrition data from USDA FoodData Central.
    Returns macros per 100g serving, or None if match seems invalid.
    When quantity/unit are provided, use unit-implies-form validation (e.g. reject raw produce for tbsp).
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
            is_composite = any(w in ingredient_lower for w in [
                "sandwich", "wrap", "burrito", "taco", "burger", "pizza",
                "salad", "bowl", "plate", "combo", "meal"
            ])
            expected_range = get_expected_cal_range(ingredient_name)

            valid = []
            for f in foods:
                raw_nutrients = f.get("foodNutrients", [])
                macros = extract_macros(raw_nutrients)
                matched_name = f["description"]
                # #region agent log
                if _is_drink_like_query(ingredient_lower) and (macros.get("calories") or 0) == 0 and (macros.get("protein") or 0) == 0 and len(raw_nutrients or []) > 0:
                    try:
                        import json as _json, time as _t
                        _tot = (macros.get("calories") or 0) + (macros.get("protein") or 0) + (macros.get("carbs") or 0) + (macros.get("fat") or 0)
                        _line = _json.dumps({"timestamp": _t.time()*1000, "location": "lookup_usda.py:extract_macros_drink_zero", "message": "drink match macros=0", "data": {"query": ingredient_name, "matched": matched_name, "macros_total": _tot, "raw_nutrients_len": len(raw_nutrients), "raw_sample": [n.get("nutrientName") or (n.get("nutrient") or {}).get("name") for n in (raw_nutrients or [])[:5]]}, "hypothesisId": "H3"}) + "\n"
                        open("/Users/natalieradu/Desktop/HealthCopilot/.cursor/debug.log", "a").write(_line)
                    except Exception:
                        pass
                # #endregion
                is_valid, reason = validate_usda_match(ingredient_name, matched_name, macros, quantity, unit)
                if not is_valid:
                    continue
                if _is_drink_like_query(ingredient_lower) and _query_implies_caffeine(ingredient_lower):
                    if (macros.get("calories") or 0) == 0 and (extract_caffeine_mg_per_100g(raw_nutrients) or 0) == 0:
                        continue
                if _query_implies_decaf_or_herbal(ingredient_lower):
                    if (extract_caffeine_mg_per_100g(raw_nutrients) or 0) > 5:
                        continue
                cal_100 = macros.get("calories", 0) or 0
                cal_score = score_calorie_fit(cal_100, expected_range[0], expected_range[1]) if expected_range else 0
                carbs = macros.get("carbs", 0) or 0
                if is_composite and carbs == 0:
                    cal_score += 500
                cal_score -= _prefer_cooked_for_meat(ingredient_lower, matched_name)
                cal_score -= _prefer_sauce_for_condiment_query(ingredient_lower, matched_name, unit)
                cal_score -= _prefer_cooked_for_grains(ingredient_lower, matched_name)
                valid.append((cal_score, carbs, f, macros, matched_name, raw_nutrients))

            if not valid:
                best = None
            else:
                best_carbs = max(v[1] for v in valid) if is_composite else 0
                for i, v in enumerate(valid):
                    s, carbs, *_ = v
                    if is_composite and carbs < best_carbs:
                        valid[i] = (s + 200, carbs, *v[2:])
                valid.sort(key=lambda x: x[0])
                if _is_drink_like_query(ingredient_lower) and len(valid) > 1:
                    valid.sort(key=lambda x: (-_score_drink_match_for_ordering(ingredient_lower, x[4], x[5]), x[0]))
                best = valid[0]
                while valid:
                    if not _has_nutrition_data(best[5], best[3]):
                        valid.pop(0)
                        best = valid[0] if valid else None
                        continue
                    # Reject drink match when match name has no significant word from query (e.g. raspberry hibiscus -> Oolong)
                    if _is_drink_like_query(ingredient_lower):
                        if not _drink_match_has_query_overlap(ingredient_lower, best[4]):
                            valid.pop(0)
                            best = valid[0] if valid else None
                            continue
                        if _tea_type_mismatch(ingredient_lower, best[4]):
                            valid.pop(0)
                            best = valid[0] if valid else None
                            continue
                    break

            if best:
                # For drinks: reject if no query overlap, then try alt queries
                if _is_drink_like_query(ingredient_lower):
                    if not _drink_match_has_query_overlap(ingredient_lower, best[4]):
                        print(f"   ⏭️ Primary drink match has no query overlap, trying alternative queries...")
                        best = None
                    elif _tea_type_mismatch(ingredient_lower, best[4]):
                        print(f"   ⏭️ Primary drink match tea type mismatch (e.g. Oolong for hibiscus/sleepy), trying alternatives...")
                        best = None
                if best:
                    score, _, f, macros, matched_name, raw_nutrients = best
                    cal_100 = macros.get("calories", 0)
                    serving_g = f.get("servingSize", 100)
                    # #region agent log
                    if _is_drink_like_query(ingredient_lower):
                        try:
                            import json as _json, time as _t
                            _line = _json.dumps({"timestamp": _t.time()*1000, "location": "lookup_usda.py:usda_return_drink", "message": "USDA returning drink match", "data": {"query": ingredient_name, "matched": matched_name, "cal_100": cal_100, "macros": macros}, "hypothesisId": "H2"}) + "\n"
                            open("/Users/natalieradu/Desktop/HealthCopilot/.cursor/debug.log", "a").write(_line)
                        except Exception:
                            pass
                    # #endregion
                    print(f"   ✅ Matched: '{matched_name}' (fdcId: {f['fdcId']}) — {cal_100:.0f} cal/100g, score={score:.0f}")
                    print(f"   Macros: {macros}")
                    nutrition = normalize_usda_food_nutrients(raw_nutrients)
                    return {
                        "usdaCode": f["fdcId"],
                        "name": matched_name,
                        "nutrition": nutrition,
                        "macros_per_100g": macros,
                        "serving_size_g": serving_g,
                    }
            # First query had results but none passed validation — try alternative queries (e.g. "matcha" → "matcha beverage")
            for alt_q in _alternative_usda_queries(ingredient_name):
                if alt_q == ingredient_name:
                    continue
                print(f"   🔄 Trying alternative query: '{alt_q}'")
                r2 = requests.get(USDA_URL, params={"query": alt_q, "api_key": USDA_KEY, "pageSize": 10})
                if r2.status_code != 200:
                    continue
                foods2 = r2.json().get("foods", [])
                if not foods2:
                    continue
                valid2 = []
                for f in foods2:
                    raw_nutrients = f.get("foodNutrients", [])
                    macros = extract_macros(raw_nutrients)
                    matched_name = f["description"]
                    is_valid, _ = validate_usda_match(ingredient_name, matched_name, macros, quantity, unit)
                    if not is_valid:
                        continue
                    cal_100 = macros.get("calories", 0) or 0
                    expected_range = get_expected_cal_range(ingredient_name)
                    cal_score = score_calorie_fit(cal_100, expected_range[0], expected_range[1]) if expected_range else 0
                    valid2.append((cal_score, f, macros, matched_name, raw_nutrients))
                if valid2:
                    # For drinks: keep only candidates with query overlap and no tea type mismatch, then sort by drink ordering score
                    if _is_drink_like_query(ingredient_lower):
                        valid2 = [v for v in valid2 if _drink_match_has_query_overlap(ingredient_lower, v[3]) and not _tea_type_mismatch(ingredient_lower, v[3])]
                    if valid2:
                        if _is_drink_like_query(ingredient_lower):
                            valid2.sort(key=lambda x: (-_score_drink_match_for_ordering(ingredient_lower, x[3], x[4]), x[0]))
                        else:
                            valid2.sort(key=lambda x: x[0])
                        for v2 in valid2:
                            _, f, macros, matched_name, raw_nutrients = v2
                            if not _has_nutrition_data(raw_nutrients, macros):
                                continue
                            cal_100 = macros.get("calories", 0)
                            serving_g_alt = f.get("servingSize", 100)
                            # #region agent log
                            if "matcha" in ingredient_name.lower():
                                try:
                                    import json, time
                                    _line = json.dumps({"timestamp": time.time() * 1000, "location": "lookup_usda.py:usda_match_alt", "message": "USDA match (alt) for matcha", "data": {"ingredient_name": ingredient_name, "matched_name": matched_name, "serving_size_g": serving_g_alt}, "sessionId": "debug-session", "hypothesisId": "H3"}) + "\n"
                                    open("/Users/natalieradu/Desktop/HealthCopilot/.cursor/debug.log", "a").write(_line)
                                except Exception:
                                    pass
                            # #endregion
                            print(f"   ✅ Matched (alt): '{matched_name}' (fdcId: {f['fdcId']}) — {cal_100:.0f} cal/100g")
                            nutrition = normalize_usda_food_nutrients(raw_nutrients)
                            return {
                                "usdaCode": f["fdcId"],
                                "name": matched_name,
                                "nutrition": nutrition,
                                "macros_per_100g": macros,
                                "serving_size_g": serving_g_alt,
                            }
        else:
            # Primary query returned no results — try alternative queries (e.g. "pork shoulder steak" → "pork shoulder steak raw")
            print(f"   ⚠️ No USDA results for '{ingredient_name}', trying alternative queries...")
            ingredient_lower = ingredient_name.lower()
            for alt_q in _alternative_usda_queries(ingredient_name):
                if alt_q == ingredient_name:
                    continue
                print(f"   🔄 Trying alternative query: '{alt_q}'")
                r2 = requests.get(USDA_URL, params={"query": alt_q, "api_key": USDA_KEY, "pageSize": 10})
                if r2.status_code != 200:
                    continue
                foods2 = r2.json().get("foods", [])
                if not foods2:
                    continue
                valid2 = []
                for f in foods2:
                    raw_nutrients = f.get("foodNutrients", [])
                    macros = extract_macros(raw_nutrients)
                    matched_name = f["description"]
                    is_valid, _ = validate_usda_match(ingredient_name, matched_name, macros, quantity, unit)
                    if not is_valid:
                        continue
                    cal_100 = macros.get("calories", 0) or 0
                    expected_range = get_expected_cal_range(ingredient_name)
                    cal_score = score_calorie_fit(cal_100, expected_range[0], expected_range[1]) if expected_range else 0
                    valid2.append((cal_score, f, macros, matched_name, raw_nutrients))
                if valid2:
                    if _is_drink_like_query(ingredient_lower):
                        valid2 = [v for v in valid2 if _drink_match_has_query_overlap(ingredient_lower, v[3]) and not _tea_type_mismatch(ingredient_lower, v[3])]
                    if valid2:
                        if _is_drink_like_query(ingredient_lower):
                            valid2.sort(key=lambda x: (-_score_drink_match_for_ordering(ingredient_lower, x[3], x[4]), x[0]))
                        else:
                            valid2.sort(key=lambda x: x[0])
                        for v2 in valid2:
                            _, f, macros, matched_name, raw_nutrients = v2
                            if not _has_nutrition_data(raw_nutrients, macros):
                                continue
                            cal_100 = macros.get("calories", 0)
                            serving_g_alt = f.get("servingSize", 100)
                            print(f"   ✅ Matched (alt): '{matched_name}' (fdcId: {f['fdcId']}) — {cal_100:.0f} cal/100g")
                            nutrition = normalize_usda_food_nutrients(raw_nutrients)
                            return {
                                "usdaCode": f["fdcId"],
                                "name": matched_name,
                                "nutrition": nutrition,
                                "macros_per_100g": macros,
                                "serving_size_g": serving_g_alt,
                            }
            print(f"   ⚠️ No USDA match after trying alternatives")
            return None

    except requests.exceptions.RequestException as e:
        print(f"   ❌ USDA request failed: {e}")
        return None
    except Exception as e:
        print(f"   ❌ USDA lookup error: {e}")
        return None


def usda_lookup_by_fdc_id(fdc_id, serving_size_g: float = 100.0) -> dict | None:
    """
    Fetch food details by FDC ID (for pantry reuse).
    Returns same format as usda_lookup: {usdaCode, name, nutrition, macros_per_100g, serving_size_g}.
    """
    if not fdc_id or not USDA_KEY:
        return None
    url = f"{USDA_FOOD_URL}/{fdc_id}"
    try:
        r = requests.get(url, params={"api_key": USDA_KEY})
        if r.status_code != 200:
            return None
        f = r.json()
        raw_nutrients = f.get("foodNutrients", [])
        if not raw_nutrients:
            return None
        # Normalize (handles amount/nutrient vs value/nutrientName formats)
        norm_nutrients = normalize_usda_food_nutrients(raw_nutrients)
        macros = extract_macros(norm_nutrients)
        # Reject zero-data entries (e.g. USDA placeholder records)
        total_macros = (macros.get("calories") or 0) + (macros.get("protein") or 0) + (macros.get("carbs") or 0) + (macros.get("fat") or 0)
        if total_macros <= 0:
            return None
        name = f.get("description") or f.get("additionalDescriptions") or ""
        if isinstance(name, list):
            name = name[0] if name else ""
        name = (name or "Unknown").strip()
        serving = serving_size_g
        if "servingSize" in f and f["servingSize"]:
            serving = float(f["servingSize"])
        elif "foodPortions" in f and f["foodPortions"]:
            p = f["foodPortions"][0]
            serving = float(p.get("gramWeight", 100))
        return {
            "usdaCode": str(fdc_id),
            "name": name,
            "nutrition": norm_nutrients,
            "macros_per_100g": macros,
            "serving_size_g": serving,
        }
    except Exception as e:
        print(f"   ⚠️ usda_lookup_by_fdc_id({fdc_id}) failed: {e}")
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
                 "kiwi", "kiwis", "pear", "pears", "plum", "plums",
                 "carrot", "carrots", "broccoli", "celery", "cucumber", "tomato", "tomatoes",
                 "lettuce", "spinach", "pepper", "peppers", "melon", "watermelon", "mango", "mangoes",
                 "cabbage", "cabbages"]
    if any(f in lower for f in raw_foods):
        # Avoid duplicate: if name already has "raw", skip
        if "raw" not in lower and "juice" not in lower and "dried" not in lower:
            base = name.split(",")[0].strip()
            queries.append(f"{base} raw")
            if not base.endswith("s") and base.lower() not in ("grape", "mango", "peach", "melon"):
                queries.append(f"{base}s raw")
    # Meats: add "cooked" when user doesn't say raw (meal context usually means cooked); also "raw" for plain meat
    meat_terms = ["chicken", "beef", "steak", "pork", "turkey", "lamb", "salmon", "tuna", "fish", "ground"]
    if any(m in lower for m in meat_terms):
        if "fried" not in lower and "breaded" not in lower and "battered" not in lower:
            base = name.split(",")[0].strip()
            if "raw" not in lower:
                # User implied cooked (e.g. "ground turkey" in meal) — prefer cooked form
                queries.append(f"{base} cooked")
            if "raw" not in lower and "cooked" not in lower:
                if "wing" in lower:
                    queries.append("chicken wings raw")
                    queries.append("chicken wing raw")
                elif "chicken" in lower and "breast" not in lower:
                    queries.append("chicken breast raw")
                queries.append(f"{base} raw")
    # Plant milks: branded search may return sweetened/creamer first; try base "soy milk" etc.
    plant_milks = ["soy milk", "oat milk", "almond milk", "coconut milk", "cashew milk", "pea milk"]
    if any(p in lower for p in plant_milks):
        for p in plant_milks:
            if p in lower:
                queries.append(p)
                queries.append(f"{p} unsweetened")
                break
    # Coffee/tea: search "brewed" to get black coffee (~2 cal), not creamer or sweetened
    if "coffee" in lower or "espresso" in lower:
        queries.append("coffee brewed")
        queries.append("black coffee brewed")
    # Tea: use type-specific alt queries so we don't lose context (earl grey -> black tea, not generic oolong)
    if "tea" in lower:
        if "earl" in lower or "grey" in lower or "gray" in lower:
            queries.append("black tea brewed")
        elif "hibiscus" in lower or ("raspberry" in lower and "tea" in lower):
            queries.append("hibiscus tea brewed")
        elif "chamomile" in lower or "peppermint" in lower or "rooibos" in lower:
            queries.append("herbal tea brewed")
        elif "sleepy" in lower or "bedtime" in lower or "calm" in lower:
            queries.append("herbal tea brewed")
        elif "green" in lower:
            queries.append("green tea brewed")
        elif "herbal" not in lower:
            queries.append("tea brewed")
    # Beverage/broth-type: try "beverage" or "ready to drink" so we get prepared form, not just powder/concentrate
    if any(f in lower for f in VERY_LOW_PROTEIN_INGREDIENTS):
        base = name.split(",")[0].strip()
        if "beverage" not in lower and "drink" not in lower:
            queries.append(f"{base} beverage")
        queries.append(f"beverages {base}")
    # Frank's Red Hot etc: condiment (often tbsp) should get sauce, not hot dogs
    if ("frank" in lower or "franks" in lower) and "red hot" in lower:
        queries.append("frank's red hot sauce")
        queries.append("hot sauce cayenne pepper")
    # Grains (oats, rice): when user said "cooked", prioritize cooked queries first
    grain_terms = ["oat", "oats", "oatmeal", "steel cut", "rice", "brown rice", "white rice"]
    if "milk" not in lower and any(g in lower for g in grain_terms) and "raw" not in lower and "dry" not in lower and "uncooked" not in lower:
        base = name.split(",")[0].strip()
        if "cooked" in lower:
            # Preparation intent: try cooked-specific queries first so USDA returns cooked product
            cooked_alts = []
            if "steel" in lower or "oat" in lower:
                cooked_alts.extend(["oatmeal cooked", "oats cooked with water", "steel cut oatmeal"])
            base_no_cooked = re.sub(r"\bcooked\b", "", base).strip()
            if base_no_cooked and base_no_cooked != base:
                cooked_alts.append(f"{base_no_cooked} cooked")
            for q in cooked_alts:
                if q not in queries:
                    queries.insert(1, q)  # After primary name
        queries.append(f"{base} cooked")
        if "cooked" in lower:
            base_no_cooked = re.sub(r"\bcooked\b", "", base).strip()
            if base_no_cooked and f"{base_no_cooked} cooked" not in queries:
                queries.append(f"{base_no_cooked} cooked")
        if "rice" in lower:
            queries.append("rice cooked")
        if "brown rice" in lower:
            queries.append("brown rice cooked")
    return queries


def _is_product_type_mismatch(query_lower: str, matched_name: str) -> bool:
    """Return True if match is wrong product type (e.g. yogurt when user asked for milk)."""
    q = query_lower
    m = matched_name.lower()
    if "milk" in q and "soy" in q:
        if "yogurt" in m or "creamer" in m or "cream" in m:
            return True
    if "milk" in q and ("oat" in q or "almond" in q):
        if "yogurt" in m or "creamer" in m:
            return True
    return False


def usda_search_options(
    query: str, quantity: float, unit: str, max_options: int = 8
) -> tuple[list[dict], bool]:
    """
    Search USDA and return multiple options with scaled nutrition for the user to choose.
    Returns (options, has_exact_brand_match).
    Excludes product type mismatches (yogurt/creamer when user asked for milk).
    """
    if not USDA_KEY:
        return [], False
    query_lower = (query or "").lower()
    all_candidates = []
    seen_fdc = set()
    for q in [query] + _alternative_usda_queries(query):
        try:
            r = requests.get(USDA_URL, params={"query": q, "api_key": USDA_KEY, "pageSize": 20})
            if r.status_code != 200:
                continue
            foods = r.json().get("foods", [])
            for f in foods:
                fdc_id = f.get("fdcId")
                if fdc_id in seen_fdc:
                    continue
                raw_nutrients = f.get("foodNutrients", [])
                macros = extract_macros(raw_nutrients)
                matched_name = f.get("description", "")
                if not validate_usda_match(query, matched_name, macros)[0]:
                    continue
                if _is_product_type_mismatch(query_lower, matched_name):
                    continue
                seen_fdc.add(fdc_id)
                serving_size = f.get("servingSize", 100) or 100
                unit_lower = (unit or "").lower()
                if unit_lower in ("piece", "pieces"):
                    piece_g = get_piece_grams(query)
                    if piece_g is not None:
                        serving_size = piece_g
                scaled = scale_nutrition(raw_nutrients, quantity, unit, serving_size)
                cal = next((n.get("value", 0) for n in scaled if n.get("nutrientName") == "Energy" and n.get("unitName") == "KCAL"), 0)
                prot = next((n.get("value", 0) for n in scaled if n.get("nutrientName") == "Protein"), 0)
                carbs = next((n.get("value", 0) for n in scaled if "carbohydrate" in (n.get("nutrientName") or "").lower()), 0)
                fat = next((n.get("value", 0) for n in scaled if "lipid" in (n.get("nutrientName") or "").lower() or n.get("nutrientName") == "Total lipid (fat)"), 0)
                all_candidates.append({
                    "usdaCode": fdc_id,
                    "name": matched_name,
                    "nutrition": scaled,
                    "serving_size_g": serving_size,
                    "calories": round(cal, 0) if cal else None,
                    "protein": round(prot, 1) if prot is not None else None,
                    "carbs": round(carbs, 1) if carbs is not None else None,
                    "fat": round(fat, 1) if fat is not None else None,
                })
        except Exception as e:
            print(f"   ⚠️ usda_search_options error for '{q}': {e}")
    # Rank by calorie fit (primary) and name overlap (secondary) — most likely first
    expected = get_expected_cal_range(query)
    q_words = set(w for w in query_lower.split() if len(w) > 2)
    for c in all_candidates:
        grams = convert_to_grams(quantity or 1, unit or "serving", c.get("serving_size_g", 100))
        cal_100 = (c["calories"] or 0) * 100 / grams if grams > 0 else 0
        cal_score = score_calorie_fit(cal_100, expected[0], expected[1]) if expected else 0
        m_words = set(c["name"].replace(",", " ").lower().split())
        name_overlap = len(q_words & m_words) if q_words else 0
        c["_sort"] = (cal_score, -name_overlap)  # lower cal_score first, higher overlap first
    all_candidates.sort(key=lambda x: x["_sort"])
    for c in all_candidates:
        del c["_sort"]
    options = all_candidates[:max_options]
    # Exact branded match: query appears in matched name (e.g. "silk original" in "SILK Original, soymilk")
    has_exact = False
    for opt in options:
        m_lower = opt["name"].replace(",", " ").lower()
        mw = set(m_lower.split())
        if q_words and q_words <= mw:
            has_exact = True
            break
        if query_lower in m_lower:
            has_exact = True
            break
    return options, has_exact


_COMMON_WHOLE_FOODS = frozenset([
    "strawberry", "strawberries", "apple", "apples", "banana", "bananas",
    "kiwi", "kiwis", "orange", "oranges", "pear", "pears", "plum", "plums",
])


def resolve_usda_for_ingredient(
    name: str, quantity: float, unit: str
) -> tuple[dict | None, list, str, str | None]:
    """
    Shared USDA resolution used by both regression runner and parse API.
    Returns (usda_dict, scaled_nutrition, source, usda_matched_name).
    source is "usda" or "gpt"; usda_matched_name is set when source is usda.
    """
    name_lower = (name or "").lower().strip()
    unit_lower = (unit or "serving").lower().strip()
    scaled_nutrition = []
    source = "gpt"
    usda_matched_name = None

    usda = usda_lookup(name, quantity, unit)
    if not usda and name_lower in _COMMON_WHOLE_FOODS:
        usda = usda_lookup_valid_for_portion(name, quantity, unit)

    if usda:
        usda_matched_name = usda.get("name")
        serving_size = usda.get("serving_size_g", 100.0)
        piece_g = get_piece_grams(name)
        if use_piece_grams_for_portion(unit_lower, name_lower, quantity, piece_g):
            serving_size = piece_g
        scaled_nutrition = scale_nutrition(usda.get("nutrition", []), quantity, unit, serving_size)
        cal_val = next((n.get("value", 0) for n in scaled_nutrition if n.get("nutrientName") == "Energy"), 0)
        is_valid, _ = validate_scaled_calories(name, quantity, unit, cal_val)
        if not is_valid:
            usda = usda_lookup_valid_for_portion(name, quantity, unit)
            if usda:
                usda_matched_name = usda.get("name")
                serving_size = usda.get("serving_size_g", 100.0)
                if use_piece_grams_for_portion(unit_lower, name_lower, quantity, piece_g):
                    serving_size = piece_g
                scaled_nutrition = scale_nutrition(usda.get("nutrition", []), quantity, unit, serving_size)
                source = "usda"
        else:
            ok, _ = validate_scaled_protein(name, scaled_nutrition)
            if not ok:
                usda = usda_lookup_valid_for_portion(name, quantity, unit)
                if usda:
                    usda_matched_name = usda.get("name")
                    serving_size = usda.get("serving_size_g", 100.0)
                    if use_piece_grams_for_portion(unit_lower, name_lower, quantity, piece_g):
                        serving_size = piece_g
                    scaled_nutrition = scale_nutrition(usda.get("nutrition", []), quantity, unit, serving_size)
            source = "usda" if usda else "gpt"

    if not usda:
        scaled_nutrition = []  # Caller will use GPT fallback

    return usda, scaled_nutrition, source, usda_matched_name if usda else None


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
        usda = usda_lookup(q, quantity, unit)
        if not usda:
            continue
        fdc_id = usda.get("usdaCode")
        if fdc_id and fdc_id in seen_fdc:
            continue
        if fdc_id:
            seen_fdc.add(fdc_id)
        serving_size = usda.get("serving_size_g", 100.0)
        unit_lower = (unit or "").lower()
        name_lower = (ingredient_name or "").strip().lower()
        piece_g = get_piece_grams(ingredient_name)
        if use_piece_grams_for_portion(unit_lower, name_lower, quantity, piece_g):
            serving_size = piece_g
        scaled = scale_nutrition(
            usda.get("nutrition", []),
            quantity,
            unit,
            serving_size,
        )
        cal_val = next((n.get("value", 0) for n in scaled if n.get("nutrientName") == "Energy"), 0)
        is_valid, reason = validate_scaled_calories(ingredient_name, quantity, unit, cal_val)
        if is_valid:
            print(f"   ✅ Found valid USDA match for portion: '{usda.get('name')}' ({cal_val:.0f} cal)")
            return usda
        print(f"   ⏭️ USDA match '{usda.get('name')}' failed validation: {reason}")
    return None
