"""
Simple API server for on-demand meal parsing.
This allows the frontend to request parsing (including image parsing via GPT Vision).

Flow:
1. Classifier runs first (food vs non-food)
2. If non-food → save to non_food_logs, skip nutrition parsing
3. If food → GPT parses → USDA lookup → save ingredients
"""

import json
from flask import Flask, request, jsonify
from flask_cors import CORS
from pb_client import get_token, insert_ingredient, delete_ingredient, delete_non_food_logs_for_meal, build_user_context_prompt, add_learned_confusion, add_common_food, add_portion_preference, fetch_meals_for_user_on_date, fetch_meals_for_user_on_local_date, fetch_ingredients_by_meal_id
from parser_gpt import parse_ingredients, parse_ingredients_from_image, correction_chat, get_image_base64, gpt_estimate_nutrition
from lookup_usda import usda_lookup, scale_nutrition, get_piece_grams, validate_scaled_calories
from log_classifier import classify_log, classify_log_with_image
import requests
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app, allow_headers=["Authorization", "Content-Type"])  # So dashboard can send user token

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
        user_id = meal.get("user")
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
        for cat in categories:
            if cat != "food":
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
        use_recent_meal = not image_field  # never override with recent meal when user sent a photo of something new
        # If mixed entry, use just the food portion for parsing
        if food_portion and len(categories) > 1:
            print(f"   🔀 Mixed entry, parsing food portion: {food_portion}")
            text = food_portion
            if use_recent_meal and recent_meals and len(recent_meals) > 0:
                source_meal_id = recent_meals[0].get("id")
        # If classifier inferred "same as before" from EXPLICIT caption ("second serving", etc.), use it — only when no image
        elif is_food and food_portion and food_portion.strip() and use_recent_meal and recent_meals:
            raw_caption = (text or "").strip().lower()
            if raw_caption in ("second serving", "same as before", "another one", "another", "repeat", "same again", "same"):
                print(f"   🔀 Using classifier food_portion for parsing: {food_portion}")
                text = food_portion
                source_meal_id = recent_meals[0].get("id")
        # Fallback: text-only, caption EXPLICITLY says "same as before" (not just "1 serving" or empty), use first real meal from context
        elif use_recent_meal and is_food and recent_meals_context:
            raw = (text or "").strip().lower()
            explicit_same_as_before = raw in ("second serving", "same as before", "another one", "another", "repeat", "same again", "same")
            if explicit_same_as_before:
                prefix = "Other meals logged today (most recent first): "
                if recent_meals_context.startswith(prefix):
                    rest = recent_meals_context[len(prefix):].strip()
                    for part in rest.split(";"):
                        first_meal = (part or "").strip()
                        if first_meal and first_meal != "(image only)":
                            text = f"{first_meal}, 1 serving"
                            print(f"   🔀 Fallback: using first recent meal for parsing: {text}")
                            if recent_meals and len(recent_meals) > 0:
                                source_meal_id = recent_meals[0].get("id")
                            break
        
        # Copy ingredients from source meal if we're "same as before" and that meal already has ingredients (no re-parse)
        if source_meal_id and source_meal_id != meal_id:
            existing = fetch_ingredients_by_meal_id(source_meal_id)
            if existing:
                print(f"   📋 Copying {len(existing)} ingredients from previous meal (no re-parse)")
                saved = []
                for ing in existing:
                    meta = ing.get("parsingMetadata") or {}
                    if isinstance(meta, str):
                        try:
                            meta = json.loads(meta) if meta else {}
                        except Exception:
                            meta = {}
                    payload = {
                        "mealId": meal_id,
                        "name": ing.get("name"),
                        "quantity": ing.get("quantity", 1),
                        "unit": ing.get("unit", "serving"),
                        "category": ing.get("category", ""),
                        "nutrition": ing.get("nutrition") if isinstance(ing.get("nutrition"), list) else [],
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
            ingredients_image = parse_ingredients_from_image(meal, PB_URL, token, user_context, image_b64=image_b64)
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
            parsed = parse_ingredients_from_image(meal, PB_URL, token, user_context, image_b64=image_b64)
            source = "gpt_image"
        elif image_field:
            print("🧠 GPT: Parsing image...")
            parsed = parse_ingredients_from_image(meal, PB_URL, token, user_context, image_b64=image_b64)
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
                # USDA lookup
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
        current_name = (original.get("name") or "").strip().lower()
        new_name_from_correction = (correction.get("name") or "").strip().lower()
        
        # Fallback: if user said "add X" anywhere in conversation but GPT returned wrong reason, treat as missing_item
        add_phrases = ("add ", "also ", "you missed ", "don't forget ", "there was also ", "and also ", "plus ", "include ", "add it", "yes add")
        all_user_text = " ".join((m.get("content") or "").lower() for m in (conversation or []) if m.get("role") == "user")
        looks_like_add = any(p in all_user_text for p in add_phrases)
        if correction_reason != "missing_item" and new_name_from_correction and new_name_from_correction != current_name and looks_like_add:
            correction_reason = "missing_item"
            print(f"   📌 Treating as missing_item (user said add; correction name differs from current)")
        
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
            new_ing = insert_ingredient(payload)
            if not new_ing:
                return jsonify({"error": "Failed to create new ingredient"}), 500
            print(f"   ✅ Added missing item as new ingredient: {new_name} (kept original unchanged)")
            usda_match_info = {"found": bool(usda), "searchedFor": new_name}
            if usda:
                usda_match_info["matchedName"] = usda.get("name")
                usda_match_info["isExactMatch"] = new_name.lower() in (usda.get("name") or "").lower()
            # Save correction record for audit (add_missing)
            correction_record = {
                "ingredientId": ingredient_id,
                "user": original.get("user"),
                "originalParse": {"name": original.get("name"), "quantity": original.get("quantity"), "unit": original.get("unit")},
                "userCorrection": correction,
                "correctionType": "add_missing",
                "correctionReason": correction_reason,
                "shouldLearn": False,
                "context": {"via": "correction_chat", "addedIngredientId": new_ing.get("id"), "conversation": conversation}
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

        # Learn portion preferences when quantity/unit changed (same food, different amount)
        quantity_changed = correction.get("quantity") is not None and correction.get("quantity") != original.get("quantity")
        unit_changed = correction.get("unit") is not None and correction.get("unit") != original.get("unit")
        name_unchanged = (correction.get("name") or original.get("name") or "").strip().lower() == (original.get("name") or "").strip().lower()
        if user_id and name_unchanged and (quantity_changed or unit_changed):
            food_name = original.get("name") or correction.get("name")
            new_qty = correction.get("quantity") if correction.get("quantity") is not None else original.get("quantity")
            new_unit = correction.get("unit") or original.get("unit") or "serving"
            if food_name and new_qty is not None and new_qty > 0:
                try:
                    add_portion_preference(user_id, food_name, new_qty, new_unit)
                    print(f"   📐 Learned portion: {food_name} → {new_qty} {new_unit}")
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
