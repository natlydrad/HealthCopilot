"""
Simple API server for on-demand meal parsing.
This allows the frontend to request parsing (including image parsing via GPT Vision).

Flow:
1. Classifier runs first (food vs non-food)
2. If non-food → save to non_food_logs, skip nutrition parsing
3. If food → GPT parses → USDA lookup → save ingredients
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from pb_client import get_token, insert_ingredient, build_user_context_prompt, add_learned_confusion, add_common_food
from parser_gpt import parse_ingredients, parse_ingredients_from_image, correction_chat
from lookup_usda import usda_lookup, scale_nutrition
from log_classifier import classify_log
import requests
import os
from dotenv import load_dotenv

load_dotenv()

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


@app.route("/classify/<meal_id>", methods=["POST"])
def classify_meal(meal_id):
    """
    Classify a meal without parsing.
    Useful for testing the classifier.
    """
    try:
        token = get_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        # Fetch the meal
        resp = requests.get(f"{PB_URL}/api/collections/meals/records/{meal_id}", headers=headers)
        if resp.status_code != 200:
            return jsonify({"error": f"Meal not found: {meal_id}"}), 404
        
        meal = resp.json()
        text = meal.get("text", "").strip()
        
        if not text:
            return jsonify({"error": "Meal has no text to classify"}), 400
        
        # Classify
        classification = classify_log(text)
        categories = classification.get("categories", ["other"])
        is_food = "food" in categories
        
        return jsonify({
            "meal_id": meal_id,
            "text": text,
            "isFood": is_food,
            "categories": categories,
            "reasoning": classification.get("reasoning"),
            "food_portion": classification.get("food_portion"),
            "non_food_portions": classification.get("non_food_portions", {})
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/classify-text", methods=["POST"])
def classify_text():
    """
    Classify arbitrary text (for testing without a meal ID).
    POST body: {"text": "your log entry here"}
    """
    try:
        data = request.get_json()
        text = data.get("text", "").strip()
        
        if not text:
            return jsonify({"error": "No text provided"}), 400
        
        classification = classify_log(text)
        categories = classification.get("categories", ["other"])
        is_food = "food" in categories
        
        return jsonify({
            "text": text,
            "isFood": is_food,
            "categories": categories,
            "reasoning": classification.get("reasoning"),
            "food_portion": classification.get("food_portion"),
            "non_food_portions": classification.get("non_food_portions", {})
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/parse/<meal_id>", methods=["POST"])
def parse_meal(meal_id):
    """
    Parse a single meal by ID.
    
    Flow:
    1. Classify first (food vs non-food)
    2. If non-food → save to non_food_logs, return early
    3. If food → GPT parse → USDA → save ingredients
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
        user_id = meal.get("user")
        timestamp = meal.get("timestamp")
        
        if not text and not image_field:
            return jsonify({"error": "Meal has no text or image to parse"}), 400
        
        print(f"🍽️ Parsing meal: {meal_id}")
        print(f"   Text: {text or '[none]'}")
        print(f"   Image: {image_field or '[none]'}")
        
        # ============================================================
        # STEP 1: CLASSIFY (food vs non-food)
        # ============================================================
        if text:
            print("🏷️ Classifying...")
            classification = classify_log(text)
            categories = classification.get("categories", ["other"])
            is_food = "food" in categories
            food_portion = classification.get("food_portion")
            non_food_portions = classification.get("non_food_portions", {})
            
            print(f"   isFood: {is_food}")
            print(f"   Categories: {categories}")
            
            # Update meal with classification
            update_resp = requests.patch(
                f"{PB_URL}/api/collections/meals/records/{meal_id}",
                headers=headers,
                json={"isFood": is_food, "categories": categories}
            )
            if update_resp.status_code != 200:
                print(f"   ⚠️ Failed to update meal classification: {update_resp.text}")
            
            # Save non-food entries to non_food_logs
            for cat in categories:
                if cat != "food" and cat != "other":
                    content = non_food_portions.get(cat, text)
                    non_food_payload = {
                        "mealId": meal_id,
                        "user": user_id,
                        "category": cat,
                        "content": content,
                        "timestamp": timestamp
                    }
                    nf_resp = requests.post(
                        f"{PB_URL}/api/collections/non_food_logs/records",
                        headers=headers,
                        json=non_food_payload
                    )
                    if nf_resp.status_code == 200:
                        print(f"   📝 Saved non_food_log: {cat}")
                    else:
                        print(f"   ⚠️ Failed to save non_food_log: {nf_resp.text}")
            
            # If NOT food, we're done - no nutrition parsing needed
            if not is_food:
                print("   ⏭️ Non-food entry, skipping nutrition parsing")
                return jsonify({
                    "ingredients": [],
                    "count": 0,
                    "isFood": False,
                    "categories": categories,
                    "message": "Non-food entry - saved to non_food_logs"
                })
            
            # If mixed entry, use just the food portion for parsing
            if food_portion and len(categories) > 1:
                print(f"   🔀 Mixed entry, parsing food portion: {food_portion}")
                text = food_portion
        else:
            # Image-only: assume food, classify later if needed
            is_food = True
            categories = ["food"]
        
        # ============================================================
        # STEP 2: PARSE FOOD (only runs if isFood=True)
        # ============================================================
        
        # Get user context for personalized parsing
        user_context = ""
        if user_id:
            user_context = build_user_context_prompt(user_id)
            if user_context:
                print(f"👤 User context loaded:\n{user_context}")
        
        # Parse with GPT
        parsed = []
        
        if text and image_field:
            print("🧠 GPT: Parsing both text + image...")
            ingredients_text = parse_ingredients(text, user_context)
            ingredients_image = parse_ingredients_from_image(meal, PB_URL, token, user_context)
            parsed = ingredients_text + ingredients_image
            source = "gpt_both"
        elif image_field:
            print("🧠 GPT: Parsing image...")
            parsed = parse_ingredients_from_image(meal, PB_URL, token, user_context)
            source = "gpt_image"
        else:
            print("🧠 GPT: Parsing text...")
            parsed = parse_ingredients(text, user_context)
            source = "gpt_text"
        
        if not parsed:
            return jsonify({"ingredients": [], "message": "No ingredients detected"}), 200
        
        # Process and save ingredients
        saved = []
        print(f"📦 Processing {len(parsed)} parsed ingredients...")
        
        for ing in parsed:
            name = ing.get("name", "").lower().strip()
            
            # Skip banned items
            if name in BANNED_INGREDIENTS or len(name) < 2:
                print(f"   ⏭️ Skipping: {name}")
                continue
            
            ing = normalize_quantity(ing)
            
            # USDA lookup
            print(f"🔎 Looking up USDA nutrition for: '{name}'")
            usda = usda_lookup(name)
            
            # Get quantity and unit for scaling
            quantity = ing.get("quantity", 1)
            unit = ing.get("unit", "serving")
            
            if usda:
                print(f"   ✅ USDA match found: {usda.get('name')}")
                # Scale nutrition to actual portion size
                serving_size = usda.get("serving_size_g", 100.0)
                scaled_nutrition = scale_nutrition(
                    usda.get("nutrition", []),
                    quantity,
                    unit,
                    serving_size
                )
            else:
                print(f"   ⚠️ No USDA match for '{name}'")
                scaled_nutrition = []
            
            # Prepare payload with SCALED nutrition values
            payload = {
                "mealId": meal_id,
                "name": ing["name"],
                "quantity": quantity,
                "unit": unit,
                "category": ing.get("category", ""),
                "nutrition": scaled_nutrition,  # Now scaled to actual portion!
                "usdaCode": usda.get("usdaCode") if usda else None,
                "source": "usda" if usda else "gpt",
                "parsingSource": source,
                "parsingMetadata": {
                    "source": "usda" if usda else "gpt",
                    "usdaMatch": bool(usda),
                    "parsedVia": "parse_api",
                    "reasoning": ing.get("reasoning", ""),  # GPT's reasoning for this identification
                    "portionGrams": round(quantity * (usda.get("serving_size_g", 100) if usda and unit in ("serving", "piece") else 
                                          28.35 if unit == "oz" else 
                                          240 if unit == "cup" else 
                                          15 if unit == "tbsp" else 100), 1) if usda else None
                }
            }
            
            # Save to PocketBase
            result = insert_ingredient(payload)
            if result:
                saved.append(result)
                print(f"   ✅ Saved: {ing['name']}")
        
        return jsonify({
            "ingredients": saved,
            "count": len(saved),
            "source": source,
            "isFood": True,
            "categories": categories
        })
        
    except Exception as e:
        print(f"❌ Error parsing meal {meal_id}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/correct/<ingredient_id>", methods=["POST"])
def correct_ingredient_chat(ingredient_id):
    """
    Conversational correction endpoint.
    
    POST body: {
        message: "that's banana peppers not mustard",
        conversation: [{role: "user", content: "..."}, {role: "assistant", content: "..."}, ...]
    }
    
    Response: {
        reply: "I see - those pickled banana peppers do look similar...",
        correction: { name: "pickled banana peppers", quantity: 1, unit: "oz" } or null,
        learned: { mistaken: "yellow mustard", actual: "pickled banana peppers" } or null,
        complete: true/false
    }
    """
    try:
        token = get_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get request data
        data = request.get_json()
        user_message = data.get("message", "").strip()
        conversation = data.get("conversation", [])
        
        if not user_message:
            return jsonify({"error": "No message provided"}), 400
        
        # Fetch the ingredient
        ing_resp = requests.get(
            f"{PB_URL}/api/collections/ingredients/records/{ingredient_id}",
            headers=headers
        )
        if ing_resp.status_code != 200:
            return jsonify({"error": f"Ingredient not found: {ingredient_id}"}), 404
        
        ingredient = ing_resp.json()
        meal_id = ingredient.get("mealId")
        
        # Fetch the meal (for image access)
        meal_resp = requests.get(
            f"{PB_URL}/api/collections/meals/records/{meal_id}",
            headers=headers
        )
        if meal_resp.status_code != 200:
            return jsonify({"error": f"Meal not found: {meal_id}"}), 404
        
        meal = meal_resp.json()
        
        print(f"💬 Correction chat for ingredient: {ingredient.get('name')}")
        print(f"   User: {user_message}")
        
        # Call the correction chat function
        result = correction_chat(
            meal=meal,
            ingredient=ingredient,
            user_message=user_message,
            conversation_history=conversation,
            pb_url=PB_URL,
            token=token
        )
        
        print(f"   AI: {result.get('reply', '')[:100]}...")
        if result.get("correction"):
            print(f"   Correction: {result['correction']}")
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Error in correction chat: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/correct/<ingredient_id>/save", methods=["POST"])
def save_correction(ingredient_id):
    """
    Save a correction and update the ingredient.
    Also saves to learned patterns if applicable (only when shouldLearn=true).
    
    POST body: {
        correction: { name: "...", quantity: ..., unit: "..." },
        learned: { mistaken: "...", actual: "..." } or null,
        correctionReason: "misidentified" | "added_after" | "portion_estimate" | "brand_specific" | "missing_item",
        shouldLearn: true/false
    }
    """
    try:
        token = get_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        data = request.get_json()
        correction = data.get("correction", {})
        learned = data.get("learned")
        correction_reason = data.get("correctionReason", "unknown")
        should_learn = data.get("shouldLearn", False)
        conversation = data.get("conversation", [])  # Chat history for reference
        
        if not correction:
            return jsonify({"error": "No correction provided"}), 400
        
        print(f"📝 Saving correction: reason={correction_reason}, shouldLearn={should_learn}")
        
        # Fetch original ingredient
        ing_resp = requests.get(
            f"{PB_URL}/api/collections/ingredients/records/{ingredient_id}",
            headers=headers
        )
        if ing_resp.status_code != 200:
            return jsonify({"error": f"Ingredient not found: {ingredient_id}"}), 404
        
        original = ing_resp.json()
        
        # Build update payload
        update = {}
        if correction.get("name"):
            update["name"] = correction["name"]
        if correction.get("quantity") is not None:
            update["quantity"] = correction["quantity"]
        if correction.get("unit"):
            update["unit"] = correction["unit"]
        
        # Check if we need to re-lookup or re-scale nutrition
        usda_match_info = None  # Track what USDA returned for user feedback
        name_changed = correction.get("name") and correction["name"] != original.get("name")
        quantity_changed = correction.get("quantity") is not None and correction["quantity"] != original.get("quantity")
        unit_changed = correction.get("unit") and correction["unit"] != original.get("unit")
        force_recalc = correction.get("forceRecalculate", False)
        
        if name_changed or force_recalc:
            # Name changed or force recalc - do fresh USDA lookup
            corrected_name = correction.get("name", original.get("name"))
            if name_changed:
                print(f"📝 Name changed: {original.get('name')} → {corrected_name}")
            else:
                print(f"🔄 Force recalculating nutrition for: {corrected_name}")
            usda = usda_lookup(corrected_name)
            if usda:
                quantity = correction.get("quantity", original.get("quantity", 1))
                unit = correction.get("unit", original.get("unit", "serving"))
                scaled_nutrition = scale_nutrition(
                    usda.get("nutrition", []),
                    quantity,
                    unit,
                    usda.get("serving_size_g", 100.0)
                )
                update["nutrition"] = scaled_nutrition
                update["usdaCode"] = usda.get("usdaCode")
                update["source"] = "usda"
                
                # Check if USDA match is exact or a fallback
                usda_name = usda.get("name", "").lower()
                corrected_lower = corrected_name.lower()
                is_exact_match = corrected_lower in usda_name or usda_name in corrected_lower
                
                usda_match_info = {
                    "found": True,
                    "matchedName": usda.get("name"),
                    "isExactMatch": is_exact_match,
                    "searchedFor": corrected_name
                }
                print(f"   ✅ Found USDA match: {usda.get('name')} (exact: {is_exact_match})")
            else:
                update["source"] = "corrected"
                usda_match_info = {
                    "found": False,
                    "searchedFor": corrected_name
                }
                print(f"   ⚠️ No USDA match for corrected name")
        
        elif quantity_changed or unit_changed:
            # Quantity/unit changed but name same - re-scale existing nutrition
            print(f"📐 Quantity/unit changed: {original.get('quantity')} {original.get('unit')} → {correction.get('quantity', original.get('quantity'))} {correction.get('unit', original.get('unit'))}")
            
            # Get original nutrition and serving info
            original_nutrition = original.get("nutrition", [])
            original_quantity = original.get("quantity", 1)
            original_unit = original.get("unit", "serving")
            new_quantity = correction.get("quantity", original_quantity)
            new_unit = correction.get("unit", original_unit)
            
            if original_nutrition and original_quantity:
                # Calculate the multiplier: new_amount / original_amount
                # First, convert to a common base (grams) if possible
                from lookup_usda import UNIT_TO_GRAMS
                
                orig_grams = original_quantity * UNIT_TO_GRAMS.get(original_unit, 100)
                new_grams = new_quantity * UNIT_TO_GRAMS.get(new_unit, 100)
                
                if orig_grams > 0:
                    multiplier = new_grams / orig_grams
                    print(f"   📊 Scaling nutrition by {multiplier:.2f}x")
                    
                    # Scale each nutrient value
                    scaled_nutrition = []
                    for nutrient in original_nutrition:
                        scaled = nutrient.copy()
                        if "value" in scaled:
                            scaled["value"] = round(scaled["value"] * multiplier, 2)
                        scaled_nutrition.append(scaled)
                    
                    update["nutrition"] = scaled_nutrition
        
        # Update the ingredient
        update_resp = requests.patch(
            f"{PB_URL}/api/collections/ingredients/records/{ingredient_id}",
            headers=headers,
            json=update
        )
        
        if update_resp.status_code != 200:
            return jsonify({"error": f"Failed to update: {update_resp.text}"}), 500
        
        updated = update_resp.json()
        
        # Get user ID and meal info (needed for both learning and logging)
        meal_id = original.get("mealId")
        user_id = None
        meal_text = None
        meal_data = None
        if meal_id:
            try:
                meal_resp = requests.get(
                    f"{PB_URL}/api/collections/meals/records/{meal_id}",
                    headers=headers
                )
                if meal_resp.status_code == 200:
                    meal_data = meal_resp.json()
                    user_id = meal_data.get("user")
                    meal_text = meal_data.get("text", "")
            except:
                pass
        
        # Save learned pattern ONLY if shouldLearn is true
        if should_learn and learned and learned.get("mistaken") and learned.get("actual"):
            print(f"🧠 Learning (shouldLearn=true): {learned['mistaken']} → {learned['actual']}")
            
            # Extract context for smarter learning
            visual_context = original.get("parsingMetadata", {}).get("reasoning", "")
            meal_context = meal_text[:50] if meal_text else None  # First 50 chars of meal description
            
            # Save to user_food_profile (the new learning system)
            if user_id:
                try:
                    add_learned_confusion(
                        user_id, 
                        learned["mistaken"], 
                        learned["actual"],
                        visual_context=visual_context,
                        meal_context=meal_context
                    )
                    add_common_food(user_id, learned["actual"])
                    print(f"   ✅ Updated user food profile (with context: {visual_context[:30]}...)")
                except Exception as e:
                    print(f"   ⚠️ Could not update user food profile: {e}")
        elif learned:
            print(f"📝 Correction logged but NOT learning (reason: {correction_reason})")
        
        # Always save to ingredient_corrections for history/audit trail
        correction_record = {
            "ingredientId": ingredient_id,
            "user": user_id or meal_id,
            "originalParse": {
                "name": original.get("name"),
                "quantity": original.get("quantity"),
                "unit": original.get("unit"),
            },
            "userCorrection": correction,
            "correctionType": "name_change" if correction.get("name") else "quantity_change",
            "correctionReason": correction_reason,
            "shouldLearn": should_learn,
            "context": {
                "learned": learned if should_learn else None,
                "via": "correction_chat",
                "conversation": conversation  # Full chat history for reference
            }
        }
        
        # Try to save correction record (don't fail if collection doesn't exist)
        try:
            corr_resp = requests.post(
                f"{PB_URL}/api/collections/ingredient_corrections/records",
                headers=headers,
                json=correction_record
            )
            if corr_resp.status_code in (200, 201):
                print(f"   ✅ Saved correction record")
            else:
                print(f"   ⚠️ Correction record save failed: {corr_resp.status_code} - {corr_resp.text[:200]}")
        except Exception as e:
            print(f"   ⚠️ Could not save correction record: {e}")
        
        return jsonify({
            "success": True,
            "ingredient": updated,
            "learned": learned if should_learn else None,
            "shouldLearn": should_learn,
            "correctionReason": correction_reason,
            "usdaMatch": usda_match_info  # Info about USDA lookup result
        })
        
    except Exception as e:
        print(f"❌ Error saving correction: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PARSE_API_PORT", 5001))
    print(f"🚀 Parse API starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=True)
