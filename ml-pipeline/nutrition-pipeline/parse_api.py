"""
Simple API server for on-demand meal parsing.
This allows the frontend to request parsing (including image parsing via GPT Vision).
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from pb_client import get_token, insert_ingredient
from parser_gpt import parse_ingredients, parse_ingredients_from_image
from lookup_usda import usda_lookup
import requests
import os

app = Flask(__name__)
CORS(app)  # Allow frontend requests

PB_URL = os.getenv("PB_URL", "https://pocketbase-1j2x.onrender.com")

# Items to skip
BANNED_INGREDIENTS = {
    "smoothie", "salad", "sandwich", "bowl", "dish", "meal", "food", "snack",
    "breakfast", "lunch", "dinner", "unknown item", "unknown", "item",
    "serving", "1 serving", "portion",
    "knife", "fork", "spoon", "plate", "napkin", "cup", "glass", "table",
    "cutting board", "pan", "pot", "utensil", "container", "wrapper",
    "plate with food", "bowl with food", "dish with food",
    "rug", "round rug", "grey round rug", "thermo mug", 
    "counter", "countertop", "kitchen", "placemat", "towel",
}


def normalize_quantity(ing):
    """Ensure ingredient has valid quantity."""
    if not ing.get("quantity") or ing["quantity"] == 0:
        ing["quantity"] = 1
        ing["unit"] = ing.get("unit") or "serving"
    return ing


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/parse/<meal_id>", methods=["POST"])
def parse_meal(meal_id):
    """
    Parse a single meal by ID.
    Returns the parsed ingredients.
    """
    try:
        token = get_token()
        
        # Fetch the meal
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(f"{PB_URL}/api/collections/meals/records/{meal_id}", headers=headers)
        
        if resp.status_code != 200:
            return jsonify({"error": f"Meal not found: {meal_id}"}), 404
        
        meal = resp.json()
        text = meal.get("text", "").strip()
        image_field = meal.get("image")
        
        if not text and not image_field:
            return jsonify({"error": "Meal has no text or image to parse"}), 400
        
        print(f"🍽️ Parsing meal: {meal_id}")
        print(f"   Text: {text or '[none]'}")
        print(f"   Image: {image_field or '[none]'}")
        
        # Parse with GPT
        parsed = []
        
        if text and image_field:
            print("🧠 GPT: Parsing both text + image...")
            ingredients_text = parse_ingredients(text)
            ingredients_image = parse_ingredients_from_image(meal, PB_URL, token)
            parsed = ingredients_text + ingredients_image
            source = "gpt_both"
        elif image_field:
            print("🧠 GPT: Parsing image...")
            parsed = parse_ingredients_from_image(meal, PB_URL, token)
            source = "gpt_image"
        else:
            print("🧠 GPT: Parsing text...")
            parsed = parse_ingredients(text)
            source = "gpt_text"
        
        if not parsed:
            return jsonify({"ingredients": [], "message": "No ingredients detected"}), 200
        
        # Process and save ingredients
        saved = []
        for ing in parsed:
            name = ing.get("name", "").lower().strip()
            
            # Skip banned items
            if name in BANNED_INGREDIENTS or len(name) < 2:
                print(f"   ⏭️ Skipping: {name}")
                continue
            
            ing = normalize_quantity(ing)
            
            # USDA lookup
            usda = usda_lookup(name)
            
            # Prepare payload
            payload = {
                "mealId": meal_id,
                "name": ing["name"],
                "quantity": ing.get("quantity", 1),
                "unit": ing.get("unit", "serving"),
                "category": ing.get("category", ""),
                "nutrition": usda if usda else [],
                "parsingSource": source,
                "parsingMetadata": {
                    "source": "usda" if usda else "gpt",
                    "usdaMatch": bool(usda),
                    "parsedVia": "parse_api"
                }
            }
            
            # Save to PocketBase
            result = insert_ingredient(payload, token)
            if result:
                saved.append(result)
                print(f"   ✅ Saved: {ing['name']}")
        
        return jsonify({
            "ingredients": saved,
            "count": len(saved),
            "source": source
        })
        
    except Exception as e:
        print(f"❌ Error parsing meal {meal_id}: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PARSE_API_PORT", 5001))
    print(f"🚀 Parse API starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=True)
