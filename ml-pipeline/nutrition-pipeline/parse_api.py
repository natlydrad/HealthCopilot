"""
Simple API server for on-demand meal parsing.
This allows the frontend to request parsing (including image parsing via GPT Vision).

Flow:
1. Classifier runs first (food vs non-food)
2. If non-food → save to non_food_logs, skip nutrition parsing
3. If food → GPT parses → USDA lookup → save ingredients
"""

import json
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
from pb_client import get_token, insert_ingredient, delete_ingredient, delete_non_food_logs_for_meal, build_user_context_prompt, add_learned_confusion, add_common_food, add_portion_preference, add_to_pantry, is_branded_or_specific, lookup_pantry_match, fetch_meals_for_user_on_date, fetch_meals_for_user_on_local_date, fetch_ingredients_by_meal_id, get_learned_patterns_for_user, remove_learned_pattern
from parser_gpt import parse_ingredients, parse_ingredients_from_image, correction_chat, get_image_base64, gpt_estimate_nutrition
from lookup_usda import usda_lookup, usda_lookup_by_fdc_id, usda_lookup_valid_for_portion, usda_search_options, scale_nutrition, get_piece_grams, validate_scaled_calories
from log_classifier import classify_log, classify_log_with_image
import requests
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app, allow_headers=["Authorization", "Content-Type", "X-User-Id"])  # Dashboard can send user token + id

PB_URL = os.getenv("PB_URL", "https://pocketbase-1j2x.onrender.com")

def _resolve_id(value) -> str | None:
    """Resolve record ID from PocketBase relation field (string or expanded object)."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and value.get("id"):
        return str(value["id"])
    return None


def _base_food_term(name: str) -> str | None:
    """Extract base food term for broader portion matching. E.g. 'chicken breast' -> 'chicken'."""
    if not name or len(name) < 3:
        return None
    words = name.lower().strip().split()
    modifiers = {"grilled", "fried", "baked", "roasted", "steamed", "boiled", "raw", "cooked", "sautéed", "sauté", "braised", "broiled"}
    for w in words:
        if w not in modifiers and len(w) >= 3:
            return w
    return words[0] if words else None


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


def _parse_repeat_intent(raw: str) -> tuple[bool, float]:
    """
    Detect 'repeat previous meal' intent from caption. Returns (is_repeat, multiplier).
    Pattern-based — no explicit phrase list.
    """
    raw = (raw or "").strip().lower()
    if not raw:
        return False, 1.0
    # "another N" or "another" / "another one"
    m = re.match(r"^another\s+(\d+)\s*$", raw)
    if m:
        return True, float(m.group(1))
    if re.match(r"^another(\s+one)?\s*$", raw):
        return True, 1.0
    # "N more"
    m = re.match(r"^(\d+)\s+more\s*$", raw)
    if m:
        return True, float(m.group(1))
    # "two more", "three more", etc.
    m = re.match(r"^(one|two|three|four|five|six|seven|eight|nine|ten)\s+more\s*$", raw)
    if m:
        n = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
             "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}.get(m.group(1), 1)
        return True, float(n)
    # Short caption starting with repeat keyword (catches "same", "same as before", "second serving", etc.)
    if len(raw) <= 25 and re.match(r"^(same|repeat|again|second|third)\b", raw):
        return True, 1.0
    return False, 1.0


def nutrition_from_label_to_array(label: dict, quantity: float, serving_size_g: float) -> list:
    """
    Convert GPT-extracted nutritionFromLabel (per serving) to our nutrition array format,
    scaled by quantity (e.g. 2 servings). Label values are per serving; serving_size_g is per serving.
    Returns list of { nutrientName, unitName, value } for storage.
    """
    if not label or serving_size_g <= 0:
        return []
    scale = quantity  # e.g. 2 servings => 2x values
    out = []
    if label.get("calories") is not None:
        out.append({"nutrientName": "Energy", "unitName": "KCAL", "value": round((label["calories"] or 0) * scale, 2)})
    if label.get("protein") is not None:
        out.append({"nutrientName": "Protein", "unitName": "G", "value": round((label["protein"] or 0) * scale, 2)})
    carbs_val = label.get("totalCarb") if label.get("totalCarb") is not None else label.get("carbs")
    if carbs_val is not None:
        out.append({"nutrientName": "Carbohydrate, by difference", "unitName": "G", "value": round((carbs_val or 0) * scale, 2)})
    if label.get("dietaryFiber") is not None:
        out.append({"nutrientName": "Fiber, total dietary", "unitName": "G", "value": round((label["dietaryFiber"] or 0) * scale, 2)})
    if label.get("totalSugars") is not None:
        out.append({"nutrientName": "Total Sugars", "unitName": "G", "value": round((label["totalSugars"] or 0) * scale, 2)})
    fat_val = label.get("totalFat") if label.get("totalFat") is not None else label.get("fat")
    if fat_val is not None:
        out.append({"nutrientName": "Total lipid (fat)", "unitName": "G", "value": round((fat_val or 0) * scale, 2)})
    if label.get("saturatedFat") is not None:
        out.append({"nutrientName": "Fatty acids, total saturated", "unitName": "G", "value": round((label["saturatedFat"] or 0) * scale, 2)})
    if label.get("sodium") is not None:
        out.append({"nutrientName": "Sodium, Na", "unitName": "MG", "value": round((label["sodium"] or 0) * scale, 2)})
    return out


def merge_label_onto_usda(usda_nutrition: list, label_nutrition: list) -> list:
    """
    Overlay label values on top of USDA nutrition. For each nutrient present in label_nutrition,
    replace the value in usda_nutrition (match by nutrientName + unitName). Returns a new list.
    """
    if not label_nutrition:
        return list(usda_nutrition) if usda_nutrition else []
    by_key = {}
    for n in usda_nutrition:
        key = (n.get("nutrientName"), n.get("unitName"))
        by_key[key] = {**n, "value": n.get("value")}
    for n in label_nutrition:
        key = (n.get("nutrientName"), n.get("unitName"))
        if key in by_key:
            by_key[key]["value"] = n.get("value")
        else:
            by_key[key] = dict(n)
    return list(by_key.values())


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


def _user_id_from_bearer():
    """Extract user id from Authorization Bearer JWT. Returns None if invalid."""
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return None
    token = auth[7:].strip()
    if not token:
        return None
    # X-User-Id header (frontend can send it as fallback when JWT payload differs)
    uid_header = request.headers.get("X-User-Id", "").strip()
    if uid_header and len(uid_header) >= 10:
        return uid_header
    try:
        import base64
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        # PocketBase and others may use "id", "userId", "sub", or nested "record.id"
        uid = payload.get("id") or payload.get("userId") or payload.get("sub")
        if uid:
            return str(uid)
        rec = payload.get("record") or payload.get("model")
        if isinstance(rec, dict) and rec.get("id"):
            return str(rec["id"])
    except Exception:
        pass
    return None


@app.route("/learning/patterns", methods=["GET"])
def learning_patterns():
    """
    Get learned patterns for the logged-in user. Uses admin token internally
    so it works even when PocketBase API rules block direct access.
    Requires Authorization: Bearer <user_jwt>.
    """
    user_id = _user_id_from_bearer()
    if not user_id:
        return jsonify({"error": "Authorization required"}), 401
    try:
        patterns = get_learned_patterns_for_user(user_id)
        return jsonify({"patterns": patterns})
    except Exception as e:
        print(f"❌ Learning patterns error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/learning/unlearn", methods=["POST"])
def learning_unlearn():
    """
    Remove a learned pattern. Uses admin token so it works even when
    PocketBase API rules block direct user updates.
    Body: { original, learned, correctionIds?: string[] }
    """
    user_id = _user_id_from_bearer()
    if not user_id:
        return jsonify({"error": "Authorization required"}), 401
    data = request.get_json() or {}
    original = data.get("original", "").strip()
    learned = data.get("learned", "").strip()
    correction_ids = data.get("correctionIds") or []
    if not original or not learned:
        return jsonify({"error": "original and learned required"}), 400
    try:
        remove_learned_pattern(user_id, original, learned, correction_ids)
        return jsonify({"success": True})
    except Exception as e:
        print(f"❌ Learning unlearn error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/clear/<meal_id>", methods=["POST", "DELETE"])
def clear_meal_ingredients(meal_id):
    """
    Delete all ingredients for a meal. Uses service token so it bypasses
    PocketBase API rules (which block delete for regular users).
    Requires Authorization header (user must be logged in).
    """
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return jsonify({"error": "Authorization required"}), 401
    try:
        total_deleted = 0
        max_rounds = 20  # prevent infinite loop if deletes fail
        for _ in range(max_rounds):
            ingredients = fetch_ingredients_by_meal_id(meal_id)
            if not ingredients:
                break
            deleted_this_round = 0
            for ing in ingredients:
                ing_id = ing.get("id")
                if not ing_id:
                    print(f"   ⚠️ Ingredient missing id: {ing.get('name', '?')}")
                    continue
                if delete_ingredient(ing_id):
                    deleted_this_round += 1
                else:
                    print(f"   ⚠️ Could not delete id={ing_id} name={ing.get('name', '?')}")
            total_deleted += deleted_this_round
            if deleted_this_round == 0 and ingredients:
                print(f"   ⚠️ No deletes succeeded for {len(ingredients)} ingredients (403?)")
                break
        print(f"   🗑️ Cleared {total_deleted} ingredients for meal {meal_id}")
        return jsonify({"deleted": total_deleted}), 200
    except Exception as e:
        print(f"   ❌ Clear failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/delete-ingredient/<ingredient_id>", methods=["POST", "DELETE"])
def delete_single_ingredient(ingredient_id):
    """
    Delete one ingredient. Uses service token. Verifies the ingredient's meal belongs to the requesting user.
    """
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return jsonify({"error": "Authorization required"}), 401
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    user_id = _user_id_from_bearer()
    if not user_id:
        return jsonify({"error": "Invalid or missing user token"}), 401
    try:
        headers = {"Authorization": f"Bearer {get_token()}"}
        ing_resp = requests.get(
            f"{PB_URL}/api/collections/ingredients/records/{ingredient_id}",
            headers=headers
        )
        if ing_resp.status_code != 200:
            return jsonify({"error": "Ingredient not found"}), 404
        ingredient = ing_resp.json()
        meal_id = _resolve_id(ingredient.get("mealId"))
        if not meal_id:
            return jsonify({"error": "Ingredient has no meal"}), 400
        meal_resp = requests.get(
            f"{PB_URL}/api/collections/meals/records/{meal_id}",
            headers=headers
        )
        if meal_resp.status_code != 200:
            return jsonify({"error": "Meal not found"}), 404
        meal = meal_resp.json()
        meal_user = _resolve_id(meal.get("user"))
        if meal_user != user_id:
            return jsonify({"error": "Not authorized to delete this ingredient"}), 403
        if delete_ingredient(ingredient_id):
            print(f"   🗑️ Deleted ingredient: {ingredient.get('name', '?')}")
            return jsonify({"deleted": True, "id": ingredient_id}), 200
        return jsonify({"error": "Delete failed"}), 500
    except Exception as e:
        print(f"   ❌ Delete ingredient failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/update-portion/<ingredient_id>", methods=["POST", "PATCH"])
def update_ingredient_portion(ingredient_id):
    """
    Quick-edit: change only quantity/unit of an ingredient. Scales nutrition and records
    portion preference for learning (so future parses use your typical amounts).
    Body: { quantity: number, unit: string }
    """
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return jsonify({"error": "Authorization required"}), 401
    user_id = _user_id_from_bearer()
    if not user_id:
        return jsonify({"error": "Invalid or missing user token"}), 401
    data = request.get_json() or {}
    new_qty = data.get("quantity")
    new_unit = (data.get("unit") or "serving").strip()
    if new_qty is None or (isinstance(new_qty, (int, float)) and new_qty <= 0):
        return jsonify({"error": "quantity must be a positive number"}), 400
    new_qty = float(new_qty)
    try:
        headers = {"Authorization": f"Bearer {get_token()}"}
        ing_resp = requests.get(
            f"{PB_URL}/api/collections/ingredients/records/{ingredient_id}",
            headers=headers
        )
        if ing_resp.status_code != 200:
            return jsonify({"error": "Ingredient not found"}), 404
        original = ing_resp.json()
        meal_id = _resolve_id(original.get("mealId"))
        if not meal_id:
            return jsonify({"error": "Ingredient has no meal"}), 400
        meal_resp = requests.get(
            f"{PB_URL}/api/collections/meals/records/{meal_id}",
            headers=headers
        )
        if meal_resp.status_code != 200:
            return jsonify({"error": "Meal not found"}), 404
        meal = meal_resp.json()
        meal_user = _resolve_id(meal.get("user"))
        if meal_user != user_id:
            return jsonify({"error": "Not authorized to edit this ingredient"}), 403

        orig_qty = original.get("quantity", 1)
        orig_unit = (original.get("unit") or "serving").strip()
        food_name = (original.get("name") or "").strip()
        from lookup_usda import UNIT_TO_GRAMS, get_piece_grams
        unit_lower_o = orig_unit.lower()
        unit_lower_n = new_unit.lower()
        piece_weight_estimated = False  # True when we used generic 50g (food not in our list)
        # Use food-specific piece weights when unit is piece/pieces (not generic 50g)
        if unit_lower_o in ("piece", "pieces"):
            pg = get_piece_grams(food_name)
            if pg is None:
                piece_weight_estimated = True
            orig_grams = orig_qty * (pg if pg is not None else UNIT_TO_GRAMS.get(unit_lower_o, 50))
        else:
            orig_grams = orig_qty * UNIT_TO_GRAMS.get(unit_lower_o, 100)
        if unit_lower_n in ("piece", "pieces"):
            pg = get_piece_grams(food_name)
            if pg is None:
                piece_weight_estimated = True
            new_grams = new_qty * (pg if pg is not None else UNIT_TO_GRAMS.get(unit_lower_n, 50))
        else:
            new_grams = new_qty * UNIT_TO_GRAMS.get(unit_lower_n, 100)
        if orig_grams <= 0:
            orig_grams = 100
        multiplier = new_grams / orig_grams

        update = {"quantity": new_qty, "unit": new_unit}
        orig_nutrition = original.get("nutrition") or []
        if isinstance(orig_nutrition, str):
            try:
                orig_nutrition = json.loads(orig_nutrition)
            except Exception:
                orig_nutrition = []
        if orig_nutrition and isinstance(orig_nutrition, list):
            scaled = []
            for n in orig_nutrition:
                s = dict(n)
                if "value" in s and s["value"] is not None:
                    s["value"] = round(float(s["value"]) * multiplier, 2)
                scaled.append(s)
            update["nutrition"] = scaled

        patch_resp = requests.patch(
            f"{PB_URL}/api/collections/ingredients/records/{ingredient_id}",
            headers=headers,
            json=update
        )
        if patch_resp.status_code != 200:
            return jsonify({"error": f"Update failed: {patch_resp.text}"}), 500
        updated = patch_resp.json()

        if food_name and new_qty > 0:
            try:
                add_portion_preference(user_id, food_name, new_qty, new_unit)
                print(f"   📐 Learned portion: {food_name} → {new_qty} {new_unit}")
            except Exception as e:
                print(f"   ⚠️ Could not save portion preference: {e}")

        return jsonify({
            "success": True,
            "ingredient": updated,
            "pieceWeightEstimated": piece_weight_estimated,
        }), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def _process_and_insert_parsed_ingredient(ing, meal_id, user_context, source="add_ingredients"):
    """Process one parsed ingredient (USDA lookup, GPT fallback) and insert. Returns created record or None."""
    name = ing.get("name", "").lower().strip()
    if name in BANNED_INGREDIENTS or len(name) < 2:
        print(f"   ⏭️ Skipping banned/short: {name}")
        return None
    ing = normalize_quantity(ing)
    quantity = ing.get("quantity", 1)
    unit = ing.get("unit", "serving")
    usda = None
    scaled_nutrition = []
    source_ing = "gpt"
    portion_grams = None
    print(f"🔎 Looking up USDA for: '{name}'")
    usda = usda_lookup(name)
    if usda:
        serving_size = usda.get("serving_size_g", 100.0)
        unit_lower = (unit or "").lower()
        if unit_lower in ("piece", "pieces"):
            piece_g = get_piece_grams(name)
            if piece_g is not None:
                serving_size = piece_g
        scaled_nutrition = scale_nutrition(usda.get("nutrition", []), quantity, unit, serving_size)
        cal_val = next((n.get("value", 0) for n in scaled_nutrition if n.get("nutrientName") == "Energy"), 0)
        is_valid, _ = validate_scaled_calories(name, quantity, unit, cal_val)
        if not is_valid:
            usda = None
            scaled_nutrition = []
            usda = usda_lookup_valid_for_portion(name, quantity, unit)
            if usda:
                serving_size = usda.get("serving_size_g", 100.0)
                if unit_lower in ("piece", "pieces"):
                    piece_g = get_piece_grams(name)
                    if piece_g is not None:
                        serving_size = piece_g
                scaled_nutrition = scale_nutrition(usda.get("nutrition", []), quantity, unit, serving_size)
                source_ing = "usda"
                portion_grams = round(quantity * serving_size, 1)
        else:
            source_ing = "usda"
            portion_grams = round(quantity * (serving_size if unit_lower in ("serving", "piece", "pieces") else
                                      28.35 if unit == "oz" else 240 if unit == "cup" else 15 if unit == "tbsp" else 100), 1)
    if not scaled_nutrition:
        gpt_nutrition = gpt_estimate_nutrition(name, quantity, unit)
        if gpt_nutrition:
            scaled_nutrition = gpt_nutrition
            source_ing = "gpt"
    payload = {
        "mealId": meal_id,
        "name": ing["name"],
        "quantity": quantity,
        "unit": unit,
        "category": ing.get("category", "food"),
        "nutrition": scaled_nutrition,
        "usdaCode": usda.get("usdaCode") if usda else None,
        "source": source_ing,
        "parsingStrategy": "gpt",
        "parsingMetadata": {
            "source": source_ing,
            "parsingSource": source,
            "usdaMatch": bool(usda),
            "parsedVia": "parse_api",
            "reasoning": ing.get("reasoning", "User added via add-ingredients"),
            "portionGrams": portion_grams,
            "fromLabel": False,
            "partialLabel": False,
            "foodGroupServings": ing.get("foodGroupServings") if isinstance(ing.get("foodGroupServings"), dict) else None,
        }
    }
    result = insert_ingredient(payload)
    return result


@app.route("/ingredients/<meal_id>", methods=["GET"])
def get_ingredients(meal_id):
    """
    Fetch ingredients for a meal using admin token (bypasses PocketBase user rules).
    Verifies the requesting user owns the meal. Use when direct PocketBase fetch
    returns incomplete data (e.g. missing nutrition field).
    """
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return jsonify({"error": "Authorization required"}), 401
    user_id = _user_id_from_bearer()
    if not user_id:
        return jsonify({"error": "Invalid or missing user token"}), 401
    try:
        token = get_token()
        headers = {"Authorization": f"Bearer {token}"}
        meal_resp = requests.get(f"{PB_URL}/api/collections/meals/records/{meal_id}", headers=headers)
        if meal_resp.status_code != 200:
            return jsonify({"error": "Meal not found"}), 404
        meal = meal_resp.json()
        meal_user = _resolve_id(meal.get("user"))
        if meal_user != user_id:
            return jsonify({"error": "Not authorized to view this meal's ingredients"}), 403
        ingredients = fetch_ingredients_by_meal_id(meal_id)
        return jsonify({"items": ingredients})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/add-ingredients/<meal_id>", methods=["POST"])
def add_ingredients(meal_id):
    """
    Add multiple ingredients from natural text.
    Body: { text: "sardines 1 can, marinara 2 tbsp, olives 5" }
    Uses parse_ingredients (GPT) then USDA lookup + insert for each.
    """
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return jsonify({"error": "Authorization required"}), 401
    user_id = _user_id_from_bearer()
    if not user_id:
        return jsonify({"error": "Invalid or missing user token"}), 401
    data = request.get_json() or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text required"}), 400
    try:
        token = get_token()
        headers = {"Authorization": f"Bearer {token}"}
        meal_resp = requests.get(
            f"{PB_URL}/api/collections/meals/records/{meal_id}",
            headers=headers
        )
        if meal_resp.status_code != 200:
            return jsonify({"error": "Meal not found"}), 404
        meal = meal_resp.json()
        meal_user = _resolve_id(meal.get("user"))
        if meal_user != user_id:
            return jsonify({"error": "Not authorized to add ingredients to this meal"}), 403
        user_context = build_user_context_prompt(user_id) if user_id else ""
        parsed = parse_ingredients(text, user_context)
        if not parsed:
            return jsonify({
                "ingredients": [],
                "count": 0,
                "message": "No ingredients detected in that text."
            }), 200
        saved = []
        print(f"📦 Adding {len(parsed)} ingredients to meal {meal_id}...")
        for ing in parsed:
            result = _process_and_insert_parsed_ingredient(ing, meal_id, user_context)
            if result:
                saved.append(result)
                print(f"   ✅ Added: {ing.get('name', '?')}")
                # Record as user-added food for future parsing hints
                try:
                    name = (ing.get("name") or "").strip()
                    qty = ing.get("quantity", 1)
                    unit = (ing.get("unit") or "serving").strip()
                    if name and len(name) >= 2:
                        default_portion = f"{qty} {unit}" if qty and unit else None
                        add_common_food(meal_user, name, default_portion=default_portion)
                        print(f"   📝 Learned: user added '{name}'")
                        if is_branded_or_specific(name) and meal_user:
                            add_to_pantry(
                                meal_user,
                                name,
                                usda_code=result.get("usdaCode"),
                                nutrition=result.get("nutrition"),
                                source="add_ingredients",
                            )
                            print(f"   🏪 Added to pantry: {name}")
                except Exception as e:
                    print(f"   ⚠️ Could not record user-added food: {e}")
        return jsonify({
            "ingredients": saved,
            "count": len(saved),
            "message": f"Added {len(saved)} ingredient(s)."
        }), 200
    except Exception as e:
        print(f"❌ Add ingredients failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


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
        # Use service token (PB_EMAIL/PB_PASSWORD) so meal + image fetch are consistent with original working behavior
        token = get_token()
        
        # Fetch the meal
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(f"{PB_URL}/api/collections/meals/records/{meal_id}", headers=headers)
        
        if resp.status_code != 200:
            return jsonify({"error": f"Meal not found: {meal_id}"}), 404
        
        meal = resp.json()
        text = meal.get("text", "").strip()
        image_field = meal.get("image")
        user_id = _resolve_id(meal.get("user"))
        timestamp = meal.get("timestamp")
        
        if not text and not image_field:
            return jsonify({"error": "Meal has no text or image to parse"}), 400
        
        print(f"🍽️ Parsing meal: {meal_id}")
        print(f"   Text: {repr((text or '')[:80])}")
        print(f"   Image: {image_field or '[none]'}")
        
        # Recent meals *today* (user's local calendar day when timezone sent; else UTC day)
        body = request.get_json(silent=True) or {}
        timezone_iana = (body.get("timezone") or "").strip()
        recent_meals_context = ""
        try:
            ts = (timestamp or "").strip()
            if ts and user_id:
                # Only meals with timestamp < current meal so "first" = immediately previous
                if timezone_iana:
                    recent_meals = fetch_meals_for_user_on_local_date(user_id, ts, timezone_iana, exclude_meal_id=meal_id, before_timestamp=ts, limit=15)
                    if recent_meals:
                        print(f"   📅 Recent meals (local day, before this): {len(recent_meals)}")
                else:
                    date_iso = (ts[:10] if len(ts) >= 10 else "").strip()
                    recent_meals = fetch_meals_for_user_on_date(user_id, date_iso, exclude_meal_id=meal_id, before_timestamp=ts, limit=15) if (date_iso and len(date_iso) == 10) else []
                    if recent_meals:
                        print(f"   📅 Recent meals (UTC day, before this): {len(recent_meals)}")
                if recent_meals:
                    # Debug: log exact order we send (first = most recent by -timestamp)
                    for i, m in enumerate(recent_meals):
                        t = (m.get("text") or "").strip() or "(image only)"
                        ts = m.get("timestamp") or ""
                        print(f"      recent[{i}] ts={ts} | {t[:60]}")
                    parts = [str(m.get("text", "") or "").strip() or "(image only)" for m in recent_meals]
                    if parts:
                        recent_meals_context = "Other meals logged today (most recent first): " + "; ".join(parts[:10])
                else:
                    # before_timestamp may have filtered out all meals (e.g. same-second or order) — refetch same day without before filter so we have context
                    if ts and user_id:
                        if timezone_iana:
                            recent_meals = fetch_meals_for_user_on_local_date(user_id, ts, timezone_iana, exclude_meal_id=meal_id, before_timestamp=None, limit=15)
                        else:
                            date_iso = (ts[:10] if len(ts) >= 10 else "").strip()
                            recent_meals = fetch_meals_for_user_on_date(user_id, date_iso, exclude_meal_id=meal_id, before_timestamp=None, limit=15) if (date_iso and len(date_iso) == 10) else []
                        if recent_meals:
                            parts = [str(m.get("text", "") or "").strip() or "(image only)" for m in recent_meals]
                            if parts:
                                recent_meals_context = "Other meals logged today (most recent first): " + "; ".join(parts[:10])
                                print(f"   📅 Recent meals (same day, no before filter): {len(recent_meals)}")
        except Exception as e:
            print(f"   ⚠️ Recent meals context failed: {e}")
        
        # ============================================================
        # STEP 1: CLASSIFY (food vs non-food) — use text + image when both present
        # ============================================================
        if image_field:
            print("🏷️ Classifying (text + image)...")
            classification = classify_log_with_image(text or "", meal, PB_URL, token, recent_meals_context=recent_meals_context)
        elif text:
            print("🏷️ Classifying (text only)...")
            classification = classify_log(text, recent_meals_context=recent_meals_context)
        else:
            classification = {"categories": ["other"], "food_portion": None, "non_food_portions": {}}

        categories = classification.get("categories", ["other"])
        is_food = "food" in categories
        food_portion = classification.get("food_portion")
        non_food_portions = classification.get("non_food_portions", {})

        print(f"   isFood: {is_food}")
        print(f"   Categories: {categories}")
        print(f"   food_portion from classifier: {repr(food_portion)}")

        # Update meal with classification
        update_resp = requests.patch(
            f"{PB_URL}/api/collections/meals/records/{meal_id}",
            headers=headers,
            json={"isFood": is_food, "categories": categories}
        )
        if update_resp.status_code != 200:
            print(f"   ⚠️ Failed to update meal classification: {update_resp.text}")

        # Replace (not append) non_food_logs: delete existing first to avoid duplicates on re-parse
        delete_non_food_logs_for_meal(meal_id)

        # Save non-food entries to non_food_logs (so UI can remember "parsed as non-food" on refresh)
        # Requires user_id — listRule hides records where user != request.auth.id
        for cat in categories:
            if cat != "food" and user_id:
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

        # If NOT food, do not parse ingredients — return clear "not_food" result
        if not is_food:
            print("   ⏭️ Classified as non-food, skipping nutrition parsing")
            if not user_id:
                print("   ⚠️ No user_id for non_food_logs — records may not be visible to user")
            return jsonify({
                "ingredients": [],
                "count": 0,
                "isFood": False,
                "classificationResult": "not_food",
                "categories": categories,
                "source": "classifier",
                "message": "Classified as not food — no ingredients added"
            })

        # When we're using "first recent meal" (from classifier or fallback), we can copy that meal's ingredients instead of re-parsing.
        # Only do this when there is NO image — if there's an image, the image is the source of truth (e.g. chips label, not "same as before").
        source_meal_id = None  # id of the meal we're referencing (same as before)
        copy_multiplier = 1.0  # e.g. "another 2" -> 2x quantities
        use_recent_meal = not image_field  # never override with recent meal when user sent a photo of something new
        # If mixed entry, use just the food portion for parsing
        if food_portion and len(categories) > 1:
            print(f"   🔀 Mixed entry, parsing food portion: {food_portion}")
            text = food_portion
            if use_recent_meal and recent_meals and len(recent_meals) > 0:
                source_meal_id = recent_meals[0].get("id")
        # If classifier inferred "same as before" from caption, use it — only when no image
        elif is_food and food_portion and food_portion.strip() and use_recent_meal and recent_meals:
            is_repeat_c, copy_multiplier = _parse_repeat_intent(text or "")
            if is_repeat_c:
                print(f"   🔀 Using classifier food_portion for parsing: {food_portion}")
                text = food_portion
                source_meal_id = recent_meals[0].get("id")
        # Fallback: text-only, caption suggests "repeat previous meal" — pattern-based, no phrase list
        elif use_recent_meal and is_food and recent_meals_context:
            raw = (text or "").strip().lower()
            is_repeat, copy_multiplier = _parse_repeat_intent(raw)
            if is_repeat:
                if recent_meals and len(recent_meals) > 0:
                    source_meal_id = recent_meals[0].get("id")
                prefix = "Other meals logged today (most recent first): "
                if recent_meals_context and recent_meals_context.startswith(prefix):
                    rest = recent_meals_context[len(prefix):].strip()
                    for part in rest.split(";"):
                        first_meal = (part or "").strip()
                        if first_meal and first_meal != "(image only)":
                            text = f"{first_meal}, 1 serving"
                            print(f"   🔀 Fallback: using first recent meal for parsing: {text}")
                            break
                else:
                    print(f"   🔀 Fallback: matched 'same as before' phrase, copying from most recent meal")
        
        # Copy ingredients from source meal if we're "same as before" and that meal already has ingredients (no re-parse)
        if source_meal_id and source_meal_id != meal_id:
            existing = fetch_ingredients_by_meal_id(source_meal_id)
            if existing:
                mult = copy_multiplier
                print(f"   📋 Copying {len(existing)} ingredients from previous meal (no re-parse)" + (f" x{mult}" if mult != 1.0 else ""))
                saved = []
                for ing in existing:
                    meta = ing.get("parsingMetadata") or {}
                    if isinstance(meta, str):
                        try:
                            meta = json.loads(meta) if meta else {}
                        except Exception:
                            meta = {}
                    orig_qty = float(ing.get("quantity", 1) or 1)
                    new_qty = orig_qty * mult
                    orig_nutrition = ing.get("nutrition") if isinstance(ing.get("nutrition"), list) else []
                    scaled_nutrition = []
                    for n in orig_nutrition:
                        if isinstance(n, dict) and "value" in n:
                            scaled_nutrition.append({**n, "value": (n["value"] or 0) * mult})
                        else:
                            scaled_nutrition.append(n)
                    payload = {
                        "mealId": meal_id,
                        "name": ing.get("name"),
                        "quantity": new_qty,
                        "unit": ing.get("unit", "serving"),
                        "category": ing.get("category", ""),
                        "nutrition": scaled_nutrition if scaled_nutrition else orig_nutrition,
                        "usdaCode": ing.get("usdaCode"),
                        "source": ing.get("source", "gpt"),
                        "parsingStrategy": "history",  # schema allows: template, brand_db, history, gpt, manual, cached
                        "parsingMetadata": {
                            **meta,
                            "parsingSource": "copied",
                            "copiedFromMealId": source_meal_id,
                            "parsedVia": "parse_api",
                        }
                    }
                    result = insert_ingredient(payload)
                    if result:
                        saved.append(result)
                        print(f"   ✅ Copied: {ing.get('name')}")
                if saved:
                    return jsonify({
                        "ingredients": saved,
                        "count": len(saved),
                        "source": "copied",
                        "isFood": True,
                        "categories": categories,
                        "message": f"Copied {len(saved)} ingredients from previous meal (no re-parse)"
                    })
        
        # ============================================================
        # STEP 2: PARSE FOOD (only runs if isFood=True)
        # ============================================================
        
        # Get user context for personalized parsing
        user_context = ""
        if user_id:
            user_context = build_user_context_prompt(user_id)
            if user_context:
                print(f"👤 User context loaded:\n{user_context}")
        
        # When we have an image, load it once and reuse (avoids second fetch failing inside parse_ingredients_from_image)
        image_b64 = None
        if image_field:
            image_b64 = get_image_base64(meal, PB_URL, token)
            if not image_b64:
                print("⚠️ Could not load meal image (check file access / token)")
                return jsonify({
                    "ingredients": [],
                    "count": 0,
                    "source": "gpt_image",
                    "message": "Could not load image (check file access). Add a caption to parse by text, or try again."
                }), 200
        
        # Parse with GPT
        parsed = []
        no_parse_reason = None  # for "No ingredients detected" response so dashboard can show why
        print(f"   📝 Text used for parse: {repr((text or '')[:100])}")
        
        # Caption "1 serving" etc. is not a food name — parse image only so we don't get [] from text and waste a call
        generic_caption = (text or "").strip().lower() in ("1 serving", "serving", "one serving", "")
        if text and image_field and not generic_caption:
            print("🧠 GPT: Parsing both text + image...")
            ingredients_text = parse_ingredients(text, user_context)
            ingredients_image = parse_ingredients_from_image(meal, PB_URL, token, user_context, image_b64=image_b64, caption=text)
            print(f"   from text: {len(ingredients_text)}, from image: {len(ingredients_image)}")
            parsed = ingredients_text + ingredients_image
            source = "gpt_both"
            if not parsed:
                no_parse_reason = f"from text: {len(ingredients_text)}, from image: {len(ingredients_image)}"
            # Fallback: if both returned 0, retry text-only once (in case image path failed)
            if not parsed and text:
                print("   gpt_both returned 0, retrying text-only...")
                parsed = parse_ingredients(text, user_context)
                if parsed:
                    source = "gpt_text"
                    no_parse_reason = None
                    print(f"   text-only fallback got {len(parsed)} ingredients")
        elif image_field and (generic_caption or not text):
            print("🧠 GPT: Parsing image only (caption generic or empty)...")
            parsed = parse_ingredients_from_image(meal, PB_URL, token, user_context, image_b64=image_b64, caption=text or "")
            source = "gpt_image"
        elif image_field:
            print("🧠 GPT: Parsing image...")
            parsed = parse_ingredients_from_image(meal, PB_URL, token, user_context, image_b64=image_b64, caption=text or "")
            source = "gpt_image"
        else:
            print("🧠 GPT: Parsing text...")
            parsed = parse_ingredients(text, user_context)
            source = "gpt_text"
        
        if not parsed:
            print(f"⚠️ No ingredients detected: had_text={bool(text)}, had_image={bool(image_field)}, source={source}")
            msg = "No ingredients detected"
            if source == "gpt_image":
                msg = "No ingredients detected from the image. Add a caption (e.g. 'chicken salad') or check the Parse API terminal for errors."
            elif source == "gpt_both":
                msg = "No ingredients from text or image. Check the Parse API terminal for errors, or try a clearer caption (e.g. 'chicken salad')."
            reason = no_parse_reason or f"source: {source}"
            if recent_meals_context:
                reason += "; had recent_meals context"
            else:
                reason += "; no recent_meals today (or fetch failed)"
            return jsonify({
                "ingredients": [],
                "count": 0,
                "source": source,
                "message": msg,
                "reason": reason
            }), 200
        
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
            quantity = ing.get("quantity", 1)
            unit = ing.get("unit", "serving")
            
            # Prefer nutrition from visible label when GPT read it
            label_nutrition = ing.get("nutritionFromLabel")
            usda = None
            scaled_nutrition = []
            source_ing = "gpt"
            portion_grams = None
            
            partial_label = False  # set when we had label but fell back to USDA (e.g. missing calories)
            partial_label_array = []  # values we read from label to overlay onto USDA
            if label_nutrition and isinstance(label_nutrition, dict):
                serving_size_g = label_nutrition.get("servingSizeG") or 100.0
                scaled_nutrition = nutrition_from_label_to_array(label_nutrition, quantity, serving_size_g)
                has_calories = any(n.get("nutrientName") == "Energy" and (n.get("value") or 0) > 0 for n in scaled_nutrition)
                has_macros = len(scaled_nutrition) >= 3  # need calories + at least 2 of protein/carb/fat
                if scaled_nutrition and has_calories and has_macros:
                    print(f"   📋 Using nutrition from label for: '{ing.get('name')}'")
                    source_ing = "label"
                    portion_grams = round(quantity * serving_size_g, 1) if serving_size_g else None
                    label_used = True
                else:
                    if scaled_nutrition:
                        partial_label = True
                        partial_label_array = scaled_nutrition
                        reason = "no calories" if not has_calories else "incomplete macros (need protein/carb/fat)"
                        print(f"   ⚠️ Label partial ({reason}) for '{ing.get('name')}' — using USDA/GPT + overlay")
                    label_nutrition = None
                    scaled_nutrition = []
                    label_used = False
            else:
                label_used = False
            
            if not scaled_nutrition:
                # Pantry: check if user has logged this before with a specific USDA match
                usda = None
                if user_id:
                    pantry_match = lookup_pantry_match(user_id, name)
                    if pantry_match and pantry_match.get("usdaCode"):
                        usda = usda_lookup_by_fdc_id(pantry_match["usdaCode"])
                        if usda:
                            print(f"   🏪 Pantry match: using USDA for '{pantry_match.get('name', name)}'")
                if not usda:
                    print(f"🔎 Looking up USDA nutrition for: '{name}'")
                    usda = usda_lookup(name)
                if usda:
                    # Use food-specific piece weight when unit is piece/pieces (fixes chicken wings etc.)
                    serving_size = usda.get("serving_size_g", 100.0)
                    unit_lower = (unit or "").lower()
                    if unit_lower in ("piece", "pieces"):
                        piece_g = get_piece_grams(name)
                        if piece_g is not None:
                            serving_size = piece_g
                            print(f"   📐 Using {serving_size}g per piece for '{name}'")
                    scaled_nutrition = scale_nutrition(
                        usda.get("nutrition", []),
                        quantity,
                        unit,
                        serving_size
                    )
                    # Calorie sanity check - reject absurd values (e.g. 6 wings = 1500 cal)
                    cal_val = next((n.get("value", 0) for n in scaled_nutrition if n.get("nutrientName") == "Energy"), 0)
                    is_valid, reason = validate_scaled_calories(name, quantity, unit, cal_val)
                    if not is_valid:
                        print(f"   ⚠️ Rejected USDA (calorie sanity): {reason}")
                        usda = None
                        scaled_nutrition = []
                        # Try alternative USDA queries (e.g. "orange raw") before GPT
                        usda = usda_lookup_valid_for_portion(name, quantity, unit)
                        if usda:
                            serving_size = usda.get("serving_size_g", 100.0)
                            unit_lower = (unit or "").lower()
                            if unit_lower in ("piece", "pieces"):
                                piece_g = get_piece_grams(name)
                                if piece_g is not None:
                                    serving_size = piece_g
                            scaled_nutrition = scale_nutrition(
                                usda.get("nutrition", []),
                                quantity,
                                unit,
                                serving_size
                            )
                            source_ing = "usda"
                            portion_grams = round(quantity * (serving_size if unit_lower in ("serving", "piece", "pieces") else
                                                      28.35 if unit == "oz" else
                                                      240 if unit == "cup" else
                                                      15 if unit == "tbsp" else 100), 1)
                            print(f"   ✅ Better USDA match: {usda.get('name')}")
                    else:
                        print(f"   ✅ USDA match found: {usda.get('name')}")
                        # If we had partial label, overlay label values onto USDA (label overrides where present)
                        if partial_label and partial_label_array:
                            scaled_nutrition = merge_label_onto_usda(scaled_nutrition, partial_label_array)
                            print(f"   📋 Overlaid {len(partial_label_array)} label values onto USDA")
                        source_ing = "usda"
                        portion_grams = round(quantity * (serving_size if unit_lower in ("serving", "piece", "pieces") else
                                              28.35 if unit == "oz" else
                                              240 if unit == "cup" else
                                              15 if unit == "tbsp" else 100), 1)
                if not scaled_nutrition:
                    # USDA failed or rejected - fall back to GPT estimate
                    print(f"   🤖 GPT fallback: estimating nutrition for '{name}' ({quantity} {unit})")
                    gpt_nutrition = gpt_estimate_nutrition(name, quantity, unit)
                    if gpt_nutrition:
                        scaled_nutrition = gpt_nutrition
                        source_ing = "gpt"
                        usda = None
                        portion_grams = None
                        print(f"   ✅ GPT estimate: {next((n.get('value') for n in scaled_nutrition if n.get('nutrientName') == 'Energy'), 0):.0f} cal")
                    else:
                        print(f"   ⚠️ GPT estimate failed for '{name}'")
                        usda = None
                        portion_grams = None
            
            # Prepare payload — only send fields that exist on ingredients collection
            # (no parsingSource; use parsingMetadata.parsingSource and parsingStrategy instead)
            payload = {
                "mealId": meal_id,
                "name": ing["name"],
                "quantity": quantity,
                "unit": unit,
                "category": ing.get("category", ""),
                "nutrition": scaled_nutrition,
                "usdaCode": usda.get("usdaCode") if usda else None,
                "source": source_ing if source_ing in ("usda", "gpt") else "gpt",  # avoid unknown enum "label"
                "parsingStrategy": "gpt",
                "parsingMetadata": {
                    "source": source_ing,
                    "parsingSource": source,
                    "usdaMatch": bool(usda),
                    "parsedVia": "parse_api",
                    "reasoning": ing.get("reasoning", ""),
                    "portionGrams": portion_grams,
                    "fromLabel": label_used,
                    "partialLabel": partial_label,
                    "foodGroupServings": ing.get("foodGroupServings") if isinstance(ing.get("foodGroupServings"), dict) else None,
                }
            }
            
            # Save to PocketBase
            result = insert_ingredient(payload)
            if result:
                saved.append(result)
                print(f"   ✅ Saved: {ing['name']}")
                if user_id and is_branded_or_specific(ing.get("name", "")):
                    try:
                        add_to_pantry(
                            user_id,
                            result.get("name", ing["name"]),
                            usda_code=result.get("usdaCode"),
                            nutrition=result.get("nutrition"),
                            source="parse",
                        )
                        print(f"   🏪 Added to pantry: {ing['name']}")
                    except Exception as e:
                        print(f"   ⚠️ Could not add to pantry: {e}")
        
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
        user_id = _resolve_id(meal.get("user"))
        meal_ts = meal.get("timestamp", "")
        meal_id_for_ctx = _resolve_id(ingredient.get("mealId"))

        # Build recent meals context (other meals today with their ingredients) for "same as earlier" / "50%" corrections
        recent_meals_context = ""
        if user_id and meal_ts and meal_id_for_ctx:
            try:
                date_iso = meal_ts.strip()[:10] if len(meal_ts.strip()) >= 10 else ""
                if date_iso:
                    recent_meals = fetch_meals_for_user_on_date(
                        user_id, date_iso, exclude_meal_id=meal_id_for_ctx,
                        before_timestamp=meal_ts, limit=10
                    )
                    parts = []
                    for m in recent_meals:
                        mid = m.get("id")
                        mtext = (m.get("text") or "").strip() or "(image)"
                        ings = fetch_ingredients_by_meal_id(mid) if mid else []
                        ing_strs = [f"{i.get('name','?')} ({i.get('quantity',1)} {i.get('unit','serving')})" for i in ings]
                        parts.append(f"- \"{mtext}\": {', '.join(ing_strs) if ing_strs else '(no ingredients)'}")
                    if parts:
                        recent_meals_context = "\n".join(parts)
                        print(f"   📅 Recent meals context: {len(recent_meals)} meals")
            except Exception as e:
                print(f"   ⚠️ Recent meals context failed: {e}")

        print(f"💬 Correction chat for ingredient: {ingredient.get('name')}")
        print(f"   User: {user_message}")

        # Call the correction chat function
        result = correction_chat(
            meal=meal,
            ingredient=ingredient,
            user_message=user_message,
            conversation_history=conversation,
            pb_url=PB_URL,
            token=token,
            recent_meals_context=recent_meals_context,
        )
        
        print(f"   AI: {result.get('reply', '')[:100]}...")
        if result.get("correction"):
            print(f"   Correction: {result['correction']}")
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Error in correction chat: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/usda-options", methods=["POST"])
def fetch_usda_options():
    """
    Search USDA and return options for user to choose.
    POST body: { query: str, quantity: float, unit: str }
    Returns: { options: [...], hasExactMatch: bool }
    """
    try:
        data = request.get_json() or {}
        q = (data.get("query") or "").strip()
        quantity = float(data.get("quantity", 1))
        unit = data.get("unit") or "serving"
        if not q:
            return jsonify({"error": "query required"}), 400
        opts, has_exact = usda_search_options(q, quantity, unit, max_options=8)
        return jsonify({"options": opts, "hasExactMatch": has_exact})
    except Exception as e:
        print(f"❌ usda-options error: {e}")
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
        
        data = request.get_json() or {}
        correction = data.get("correction", {})
        learned = data.get("learned")
        correction_reason = data.get("correctionReason", "unknown")
        should_learn = data.get("shouldLearn", False)
        conversation = data.get("conversation", [])  # Chat history for reference
        preview = data.get("preview", False)  # If true, return what would be saved without persisting

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
        current_name = (original.get("name") or "").strip().lower()
        new_name_from_correction = (correction.get("name") or "").strip().lower()
        
        # Fallback: only treat as missing_item when user clearly said they're adding a NEW item to the meal
        # NOT when they're adding info/clarifying the current item (e.g. "it's soy milk", "oat milk")
        add_new_phrases = ("add a new", "add new", "you missed ", "don't forget ", "there was also ", "you forgot ", "add it as", "add another")
        all_user_text = " ".join((m.get("content") or "").lower() for m in (conversation or []) if m.get("role") == "user")
        looks_like_add_new = any(p in all_user_text for p in add_new_phrases)
        if correction_reason != "missing_item" and new_name_from_correction and new_name_from_correction != current_name and looks_like_add_new:
            correction_reason = "missing_item"
            print(f"   📌 Treating as missing_item (user said add new item)")
        
        # missing_item = ADD a new ingredient (the correction), do NOT change the current one
        if correction_reason == "missing_item":
            meal_id = original.get("mealId")
            if not meal_id:
                return jsonify({"error": "Ingredient has no mealId"}), 400
            new_name = correction.get("name") or "unknown"
            new_qty = correction.get("quantity", 1)
            new_unit = correction.get("unit", "serving")
            usda = usda_lookup(new_name)
            scaled_nutrition = []
            if usda:
                serving_size = usda.get("serving_size_g", 100.0)
                if (new_unit or "").lower() in ("piece", "pieces"):
                    piece_g = get_piece_grams(new_name)
                    if piece_g is not None:
                        serving_size = piece_g
                scaled_nutrition = scale_nutrition(
                    usda.get("nutrition", []),
                    new_qty,
                    new_unit,
                    serving_size
                )
                cal_val = next((n.get("value", 0) for n in scaled_nutrition if n.get("nutrientName") == "Energy"), 0)
                is_valid, _ = validate_scaled_calories(new_name, new_qty, new_unit, cal_val)
                if not is_valid:
                    usda = None
                    scaled_nutrition = []
            if not scaled_nutrition:
                gpt_nutrition = gpt_estimate_nutrition(new_name, new_qty, new_unit)
                if gpt_nutrition:
                    scaled_nutrition = gpt_nutrition
            payload = {
                "mealId": meal_id,
                "name": new_name,
                "quantity": new_qty,
                "unit": new_unit,
                "category": "food",
                "nutrition": scaled_nutrition,
                "usdaCode": usda.get("usdaCode") if usda else None,
                "source": "usda" if usda and scaled_nutrition else "gpt",
                "parsingStrategy": "gpt",
                "parsingMetadata": {
                    "source": "corrected_missing",
                    "addedVia": "correction_chat",
                    "reasoning": f"User added missing item: {new_name}",
                }
            }
            usda_match_info = {"found": bool(usda), "searchedFor": new_name}
            if usda:
                usda_match_info["matchedName"] = usda.get("name")
                usda_match_info["isExactMatch"] = new_name.lower() in (usda.get("name") or "").lower()
            if preview:
                return jsonify({
                    "success": True, "preview": True,
                    "ingredient": original,
                    "addedIngredient": payload,  # Would-be new ingredient
                    "correctionReason": correction_reason,
                    "usdaMatch": usda_match_info,
                })
            new_ing = insert_ingredient(payload)
            if not new_ing:
                return jsonify({"error": "Failed to create new ingredient"}), 500
            print(f"   ✅ Added missing item as new ingredient: {new_name} (kept original unchanged)")
            correction_record = {
                "ingredientId": ingredient_id, "user": original.get("user"),
                "originalParse": {"name": original.get("name"), "quantity": original.get("quantity"), "unit": original.get("unit")},
                "userCorrection": correction, "correctionType": "add_missing", "correctionReason": correction_reason,
                "shouldLearn": False, "context": {"via": "correction_chat", "addedIngredientId": new_ing.get("id"), "conversation": conversation}
            }
            try:
                requests.post(f"{PB_URL}/api/collections/ingredient_corrections/records", headers=headers, json=correction_record)
            except Exception:
                pass
            return jsonify({
                "success": True,
                "ingredient": original,
                "addedIngredient": new_ing,
                "correctionReason": correction_reason,
                "usdaMatch": usda_match_info,
                "message": f"Added {new_name} as a new ingredient (kept {original.get('name')} unchanged)"
            })
        
        # Build update payload (for non–missing_item corrections)
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
        force_use_gpt = correction.get("forceUseGptEstimate", False)
        corrected_name = correction.get("name", original.get("name"))
        quantity = correction.get("quantity", original.get("quantity", 1))
        unit = correction.get("unit", original.get("unit", "serving"))
        
        # User selected a USDA option — always use it (for any correction type including poor_usda_match)
        chosen = correction.get("chosenUsdaOption")
        if chosen and chosen.get("usdaCode") and chosen.get("nutrition"):
            usda = {
                "usdaCode": chosen["usdaCode"],
                "name": chosen.get("name", corrected_name),
                "nutrition": chosen["nutrition"],
                "serving_size_g": chosen.get("serving_size_g", 100),
            }
            update["nutrition"] = chosen["nutrition"]
            update["usdaCode"] = chosen["usdaCode"]
            update["source"] = "usda"
            usda_match_info = {"found": True, "matchedName": chosen.get("name"), "userChose": True, "searchedFor": corrected_name}
            print(f"   ✅ Using user-chosen USDA: {chosen.get('name')}")
        elif force_use_gpt:
            # User said USDA is wrong — try better USDA first, then GPT fallback
            print(f"📐 Poor USDA match — trying better USDA for: {corrected_name} ({quantity} {unit})")
            usda = usda_lookup_valid_for_portion(corrected_name, quantity, unit)
            if usda:
                scaled_nutrition = scale_nutrition(
                    usda.get("nutrition", []),
                    quantity,
                    unit,
                    usda.get("serving_size_g", 100.0),
                )
                update["nutrition"] = scaled_nutrition
                update["usdaCode"] = usda.get("usdaCode")
                update["source"] = "usda"
                usda_match_info = {
                    "found": True,
                    "matchedName": usda.get("name"),
                    "usedBetterMatch": True,
                    "searchedFor": corrected_name,
                }
                cal_val = next((n.get("value", 0) for n in scaled_nutrition if n.get("nutrientName") == "Energy"), 0)
                print(f"   ✅ Better USDA match: {usda.get('name')} ({cal_val:.0f} cal)")
            else:
                target_cal = correction.get("targetCalories")
                target_protein = correction.get("targetProtein")
                print(f"   ⏭️ No valid USDA — using GPT estimate")
                gpt_nutrition = gpt_estimate_nutrition(corrected_name, quantity, unit, target_cal=target_cal, target_protein=target_protein)
                if gpt_nutrition:
                    update["nutrition"] = gpt_nutrition
                    update["source"] = "gpt"
                    update["usdaCode"] = None
                    usda_match_info = {"found": False, "usedGptInstead": True, "searchedFor": corrected_name}
                    cal_val = next((n.get("value") for n in gpt_nutrition if n.get("nutrientName") == "Energy"), 0)
                    print(f"   ✅ GPT estimate: {cal_val:.0f} cal")
                else:
                    print("   ⚠️ GPT estimate failed, keeping existing nutrition")
        
        elif name_changed or force_recalc:
                if name_changed:
                    print(f"📝 Name changed: {original.get('name')} → {corrected_name}")
                else:
                    print(f"🔄 Force recalculating nutrition for: {corrected_name}")
                usda = usda_lookup(corrected_name)
                if usda:
                    scaled_nutrition = scale_nutrition(
                        usda.get("nutrition", []),
                        quantity,
                        unit,
                        usda.get("serving_size_g", 100.0)
                    )
                    update["nutrition"] = scaled_nutrition
                    update["usdaCode"] = usda.get("usdaCode")
                    update["source"] = "usda"
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

        # Preview: return what would be saved without persisting
        if preview:
            merged = {**original, **update}
            payload = {
                "success": True, "preview": True,
                "ingredient": merged,
                "addedIngredient": None,
                "correctionReason": correction_reason,
                "usdaMatch": usda_match_info,
            }
            # Fetch USDA options so user can pick a better match (when name changed OR poor USDA)
            if not correction.get("chosenUsdaOption") and (name_changed or correction_reason == "poor_usda_match"):
                qty = correction.get("quantity", original.get("quantity", 1))
                u = correction.get("unit", original.get("unit", "serving"))
                try:
                    opts, has_exact = usda_search_options(corrected_name, qty, u, max_options=8)
                    payload["usdaOptions"] = opts
                    payload["hasExactUsdaMatch"] = has_exact
                except Exception as e:
                    print(f"   ⚠️ Could not fetch USDA options: {e}")
            return jsonify(payload)

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
                    user_id = _resolve_id(meal_data.get("user"))
                    meal_text = meal_data.get("text", "")
            except:
                pass
        
        # Save learned pattern ONLY if shouldLearn is true
        if should_learn and learned and learned.get("mistaken") and learned.get("actual"):
            print(f"🧠 Learning (shouldLearn=true): {learned['mistaken']} → {learned['actual']}")
            
            # Extract context for smarter learning
            visual_context = (original.get("parsingMetadata") or {}).get("reasoning", "")
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

        # Broaden profile: add_common_food for brand_specific and poor_usda_match (e.g. soy milk -> unsweetened)
        if user_id and correction_reason in ("brand_specific", "poor_usda_match") and correction.get("name"):
            try:
                add_common_food(user_id, correction["name"])
                print(f"   📝 Added to common foods (reason: {correction_reason}): {correction['name']}")
            except Exception as e:
                print(f"   ⚠️ Could not add to common foods: {e}")

        # Add to pantry when name changed (any correction that refines the ingredient name)
        name_changed_for_pantry = (correction.get("name") or "").strip().lower() != (original.get("name") or "").strip().lower()
        if user_id and name_changed_for_pantry:
            final_name = updated.get("name") or correction.get("name")
            if final_name:
                try:
                    add_to_pantry(
                        user_id,
                        final_name,
                        usda_code=updated.get("usdaCode"),
                        nutrition=updated.get("nutrition"),
                        source="correction",
                    )
                    print(f"   🏪 Added to pantry: {final_name}")
                except Exception as e:
                    print(f"   ⚠️ Could not add to pantry: {e}")

        # Learn portion preferences when quantity/unit changed (same food, different amount)
        quantity_changed = correction.get("quantity") is not None and correction.get("quantity") != original.get("quantity")
        unit_changed = correction.get("unit") is not None and correction.get("unit") != original.get("unit")
        orig_name = (original.get("name") or "").strip().lower()
        corr_name = (correction.get("name") or orig_name or "").strip().lower()
        # Same food: exact match, or one contains the other (e.g. "chicken" vs "chicken breast")
        name_unchanged = orig_name == corr_name or (orig_name and corr_name and (orig_name in corr_name or corr_name in orig_name))
        if user_id and name_unchanged and (quantity_changed or unit_changed):
            food_name = original.get("name") or correction.get("name")
            new_qty = correction.get("quantity") if correction.get("quantity") is not None else original.get("quantity")
            new_unit = correction.get("unit") or original.get("unit") or "serving"
            if food_name and new_qty is not None and new_qty > 0:
                try:
                    add_portion_preference(user_id, food_name, new_qty, new_unit)
                    print(f"   📐 Learned portion: {food_name} → {new_qty} {new_unit}")
                    # Also learn base term for broader matching (e.g. "chicken breast" → also "chicken")
                    base = _base_food_term(food_name)
                    if base and base != food_name.lower():
                        add_portion_preference(user_id, base, new_qty, new_unit)
                        print(f"   📐 Learned portion (base): {base} → {new_qty} {new_unit}")
                except Exception as e:
                    print(f"   ⚠️ Could not save portion preference: {e}")
        
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
