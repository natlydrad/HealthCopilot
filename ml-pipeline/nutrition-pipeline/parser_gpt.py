import os
import json
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def parse_ingredients(text: str, user_context: str = ""):
    """
    Parse ingredients from text description.
    
    Args:
        text: The meal description text
        user_context: Optional personal food profile context to inject
    """
    context_section = ""
    if user_context:
        context_section = f"""
    USER CONTEXT (use this to personalize your parsing):
    {user_context}
    
    """
    
    prompt = f"""
    Extract foods, drinks, supplements from: "{text}".
    {context_section}
    IMPORTANT: Also extract from portion descriptions. E.g. "ate 75%, only half the noodles" → noodles, quantity 0.5; "half the rice" → rice, quantity 0.5; "left a quarter" → scale quantity to 0.75. Always return at least one item if any food is mentioned.
    IMPORTANT: Decompose complex/composite foods into their base ingredients.
    Examples:
    - "burrito" → tortilla, rice, beans, cheese, salsa, sour cream
    - "omelette" → eggs, butter, cheese, [any fillings mentioned]
    - "sandwich" → bread, meat, cheese, lettuce, tomato, mayo
    - "smoothie" → list the fruits/ingredients
    - "salad" → greens, vegetables, dressing
    - "pad thai" → rice noodles, egg, tofu/shrimp, peanuts, bean sprouts
    
    DO NOT return composite foods like "burrito" or "sandwich" - break them down!
    AVOID vague terms: "pizza toppings", "salad stuff", "sandwich fillings", "leftover food". Prefer specific items: "pepperoni pizza slice", "2 slices cheese pizza", "lettuce, tomato, dressing", "turkey sandwich".
    Simple items stay as-is: "apple", "coffee", "eggs", "chicken breast"
    Single food/drink phrases must return one item: "iced matcha" → one drink (e.g. name "matcha", category "drink"); "green tea", "matcha latte", "oat milk" → one item each. Do NOT return [] when the input is clearly a single food or drink.
    
    Return ONLY a JSON array (no markdown, no explanation).
    Each item must have:
    - name (string) - specific ingredient name
    - quantity (float) - estimate realistic portions
    - unit (string) - use appropriate units:
        * Eggs: count (unit: "eggs")
        * Bread/tortillas: count (unit: "slice" or "piece")
        * Bacon: count (unit: "piece" or "slice" — 2 pieces = 2 slices bacon)
        * Meats: oz (chicken→4oz, steak→6oz)
        * Rice/beans/grains: cups (unit: "cup", typically 0.5-1)
        * Vegetables: cups (unit: "cup", typically 0.25-0.5)
        * Cheese: oz (typically 1-2oz)
        * Sauces/dressings: tbsp
        * Drinks: oz (coffee→8oz)
        * Supplements: count (unit: "pill" or "capsule")
    - category (string) - "food", "drink", "supplement", or "other"
    - reasoning (string) - brief explanation of why you identified this item and estimated this portion
      e.g., "standard coffee cup size" or "typical chicken breast portion"
    - foodGroupServings (object, optional) - serving equivalents for food-group counting.
      Format: {{ "grains": 0, "protein": 0, "vegetables": 0, "fruits": 0, "dairy": 0, "fats": 0 }}.
      Grains: 1 slice bread = 1. Vegetables: 1/2 cup = 1. Fruits: 1 piece/small fruit = 1. Dairy: 1 cup milk = 1.
      Protein uses OZ-EQUIVALENTS (MyPlate): 1 oz meat = 1, so 4 oz chicken = 4, 1 egg = 1, 1/4 cup beans = 1.
      E.g. broccoli 1 cup → {{ "vegetables": 2 }}; chicken breast 4 oz → {{ "protein": 4 }}; 1 egg → {{ "protein": 1 }}.
    
    Return empty array [] only if the input clearly contains no food/drink/supplement (e.g. empty, or only metadata like "tap to edit").
    """

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    raw = resp.choices[0].message.content.strip()

    # strip ```json ... ``` fences if present
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]  # remove 'json'
        raw = raw.strip()

    try:
        out = json.loads(raw)
        # #region agent log
        if not out and text:
            try:
                _path = "/Users/natalieradu/Desktop/HealthCopilot/.cursor/debug.log"
                _payload = {"timestamp": __import__("time").time()*1000, "location": "parser_gpt.py:parse_ingredients", "message": "gpt_returned_empty", "data": {"text_preview": (text or "")[:150], "raw_preview": (raw or "")[:300]}, "hypothesisId": "H2", "sessionId": "debug-session"}
                open(_path, "a").write(__import__("json").dumps(_payload) + "\n")
            except Exception:
                pass
        # #endregion
        if not out:
            print("Parser text returned [] for input:", repr(text[:60]) if text else "")
        return out
    except Exception as e:
        print("Parser error:", e, "RAW:", raw[:200] if raw else "")
        return []

import base64
import requests


def get_image_base64(meal: dict, pb_url: str, token: str | None = None) -> str | None:
    """
    Download and encode a meal image as base64.
    Returns None if no image or download fails.
    """
    try:
        image_field = meal.get("image")
        if not image_field:
            return None

        meal_id = meal["id"]
        image_url = f"{pb_url}/api/files/meals/{meal_id}/{image_field}"

        headers = {"Authorization": f"Bearer {token}"} if token else {}
        resp = requests.get(image_url, headers=headers)
        resp.raise_for_status()
        content_type = (resp.headers.get("Content-Type") or "").lower()
        if not content_type.startswith("image/"):
            print(f"Failed to get image: response is not an image (Content-Type: {content_type}, len={len(resp.content)})")
            return None
        if len(resp.content) < 100:
            print(f"Failed to get image: response too small ({len(resp.content)} bytes)")
            return None
        b64 = base64.b64encode(resp.content).decode("utf-8")
        print(f"   Image loaded: {len(resp.content)} bytes → base64 len {len(b64)}")
        return b64
    except Exception as e:
        print(f"Failed to get image: {e}")
        return None


def _parse_image_simple_fallback(image_b64: str, user_context: str = "", caption: str = "") -> list:
    """Retry with a simpler prompt when main image parse returns [] or fails. Reduces false negatives."""
    cap = f' The user said: "{caption}". Use this to identify foods and estimate portions.' if caption and caption.strip() else ""
    prompt = f"""What food or drink is in this image?{cap}
Return a JSON array of objects. Each object must have: "name" (string), "quantity" (number), "unit" (string, e.g. serving, cup, oz), "category" (string: food, drink, or supplement), "reasoning" (string, brief).
If you see any food, drink, or packaged product with a nutrition label, return at least one item. Return [] only if nothing edible is visible (e.g. empty plate, non-food photo).
Return ONLY the JSON array, no markdown or explanation."""
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    ],
                }
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        out = json.loads(raw)
        if out:
            print(f"   Simple fallback got {len(out)} item(s)")
        return out if isinstance(out, list) else []
    except Exception as e:
        print(f"   Simple fallback failed: {e}")
        return []


def parse_ingredients_from_image(meal: dict, pb_url: str, token: str | None = None, user_context: str = "", image_b64: str | None = None, caption: str = ""):
    """
    Parses ingredients from a PocketBase image record by downloading the file locally
    and sending it to GPT-4o-mini Vision as base64.
    
    Args:
        meal: The meal record with image field
        pb_url: PocketBase URL
        token: Auth token
        user_context: Optional personal food profile context to inject
        image_b64: Optional pre-fetched base64 image (avoids double fetch; pass from parse_api when already loaded)
        caption: Optional user caption (e.g. "ate 75%, only half the noodles") — use to identify foods and estimate portions
    """
    raw = ""
    try:
        if image_b64 is None:
            image_b64 = get_image_base64(meal, pb_url, token)
        if not image_b64:
            print("Parser image: get_image_base64 failed (no image data)")
            return []

        context_section = ""
        if user_context:
            context_section = f"""
        USER CONTEXT (use this to personalize your parsing):
        {user_context}
        
        """

        caption_section = ""
        if caption and caption.strip():
            caption_section = f"""
        USER CAPTION: "{caption.strip()}"
        Use this to identify what's in the photo and to estimate portions. E.g. "only half the noodles" → noodles with quantity 0.5; "ate 75%" → scale portions down accordingly.
        
        """

        prompt = f"""
        STEP 1 — Decide what the user is logging:
        - If the image shows ONE packaged product (sandwich in a container, wrapped item, protein bar, bottle, etc.) with a visible Nutrition Facts label on the package → the user is logging THAT PRODUCT as one serving. Return exactly ONE item: the product name (e.g. "chicken salad sandwich" or the brand/product name). Do NOT list sub-ingredients like bread, chicken salad, etc. Read the label and fill nutritionFromLabel. Quantity = 1, unit = "serving".
        - If the image shows a homemade/composed meal (e.g. a plate with a burrito, a bowl of salad, multiple items on a plate) with NO single packaged product with a label → then decompose into ingredients (see below).
        
        DO NOT include: furniture, rugs, appliances, plates, mugs, utensils, or random items in the background. Do NOT add drinks just because a cup appears — only add a beverage if it is clearly what the user is logging.
        {context_section}{caption_section}
        
        When you must decompose (only for non-packaged, composed meals):
        - A burrito on a plate → tortilla, rice, beans, cheese, salsa, meat
        - A bowl of salad → greens, tomatoes, cucumber, dressing, croutons
        - Fried rice → rice, egg, vegetables, soy sauce
        - Pizza → "pepperoni pizza slice", "2 slices cheese pizza", "veggie pizza", etc. — NEVER "pizza toppings"
        - Bacon: use unit "piece" or "slice" (e.g. 2 pieces bacon), NOT cup
        AVOID vague terms: "pizza toppings", "salad stuff", "sandwich fillings", "leftover food". Prefer specific items.
        List actual ingredients, not composite names.
        
        NUTRITION FACTS LABEL: When you return ONE packaged product (Step 1), only add "nutritionFromLabel" if the FULL label is visible and you can read at least Calories and Serving size. Use:
        - servingSizeG (number) - serving size in grams if shown (e.g. 30, 42)
        - calories (number) - Calories (required; if you cannot read it, omit nutritionFromLabel)
        - protein, totalCarb, totalFat, sodium, caffeine (mg), etc. (optional)
        If the label is cut off, folded, or only partially visible so you cannot read Calories, do NOT include nutritionFromLabel — leave it out so the system will use USDA instead. Do not guess or infer calories.
        
        Return ONLY a JSON array (no markdown, no explanation).
        Each item must have:
        - name (string) - specific ingredient name
        - quantity (float) - estimate realistic portions (or 1 serving if using label)
        - unit (string) - oz, cup, tbsp, piece, serving, etc.
        - category (string) - "food", "drink", or "supplement"
        - reasoning (string) - brief explanation
        - nutritionFromLabel (object, optional) - only when a Nutrition Facts label is visible for this item
        - foodGroupServings (object, optional) - estimated serving equivalents. Format: {{ "grains": 1, "protein": 4, "vegetables": 0.5, "fruits": 0, "dairy": 0, "fats": 0.5 }}. Protein = OZ-EQUIVALENTS: 4 oz chicken = 4, 1 egg = 1. Vegetables: 1/2 cup = 1. Grains: 1 slice = 1. Dairy: 1 cup = 1.
        
        If no edible items are visible, return an empty array [].
        """

        print(f"   Calling GPT Vision with image (len={len(image_b64)})...")
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                        },
                    ],
                }
            ],
        )

        raw = (resp.choices[0].message.content or "").strip()
        print(f"   GPT Vision raw length={len(raw)}, preview={repr(raw[:200])}")

        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        out = json.loads(raw)
        if not out:
            print("   GPT returned empty array [] — retrying with simpler prompt...")
            return _parse_image_simple_fallback(image_b64, user_context, caption)
        return out
    except Exception as e:
        import traceback
        print("Parser image error:", e)
        print(traceback.format_exc())
        print("RAW:", (raw[:500] if raw else "(empty)"))
        # Retry with simpler prompt in case GPT returned non-JSON (e.g. explanation)
        if raw and ("[" in raw or "ingredient" in raw.lower()):
            try:
                return _parse_image_simple_fallback(image_b64, user_context, caption)
            except Exception:
                pass
        return []


def correction_chat(
    meal: dict,
    ingredient: dict,
    user_message: str,
    conversation_history: list,
    pb_url: str,
    token: str | None = None,
    recent_meals_context: str = "",
) -> dict:
    """
    Have a conversational correction chat about an ingredient.
    
    Args:
        meal: The meal record (for image access)
        ingredient: The ingredient being corrected
        user_message: The user's latest message
        conversation_history: List of previous messages [{role, content}, ...]
        pb_url: PocketBase URL
        token: Auth token
    
    Returns:
        {
            reply: str,  # AI's conversational response
            correction: dict | None,  # {name, quantity, unit} if correction identified
            learned: dict | None,  # {mistaken, actual} if this is a learning opportunity
            correctionReason: str,  # why the correction is needed
            shouldLearn: bool,  # whether to save this for future learning
        }
    """
    try:
        # Build the system prompt
        system_prompt = f"""You are a helpful food logging assistant. The user is correcting an ingredient identification.

CURRENT INGREDIENT:
- Name: {ingredient.get('name')}
- Quantity: {ingredient.get('quantity')} {ingredient.get('unit')}
- Source: {ingredient.get('source', 'unknown')}
- Original reasoning: {(ingredient.get('parsingMetadata') or {}).get('reasoning', 'not recorded')}
""" + (f"""
OTHER MEALS LOGGED TODAY (most recent first) — use this when user says "same as earlier", "same meal", "50% of what I had", etc.:
{recent_meals_context}
""" if recent_meals_context else "") + """

Your job is to:
1. Understand what the user wants to correct
2. Determine WHY they're correcting - this is crucial for learning:
   - "misidentified": You got the food item wrong (e.g., mustard vs banana peppers) → SHOULD LEARN
   - "added_after": User added more food after the photo was taken → DON'T LEARN
   - "portion_estimate": The portion size looked different than it was → DON'T LEARN  
   - "brand_specific": User is specifying a particular brand → MAYBE LEARN (only if visually distinguishable)
   - "missing_item": User is ADDING a WHOLE NEW item you missed (e.g. "there was also a banana", "you missed the coffee") → the "correction" is the NEW item to add as a SEPARATE ingredient; we will NOT change the current ingredient. Only use this when they explicitly say they're adding something that was NOT the item you're correcting. DON'T LEARN.
   - "brand_specific" or similar: User is adding INFO to the current item (brand, type, e.g. "it's oat milk" or "unsweetened soy milk") → UPDATE the current ingredient with the new name/info. NOT missing_item.
   - "poor_usda_match": The USDA nutrition data is wrong (e.g. "450 cal for 1 orange is crazy", "replace USDA with ~2 cal for black coffee", "that's way too many calories") → use GPT estimate instead. Set correction with "forceUseGptEstimate": true. If user specifies target calories (e.g. "~2 cal", "about 5 calories"), add "targetCalories": number to correction. DON'T LEARN.
3. Have a natural conversation - if unclear, ask: "Just to make sure I learn the right thing - did I misidentify this, or are you adding something I missed?"
4. "Add info" vs "add new ingredient": If user is clarifying/adding info TO the current item (brand, type: "it's soy milk", "oat milk", "unsweetened") → use "brand_specific", correction updates the CURRENT ingredient name. If user says they're adding something ELSE you missed ("there was also X", "you forgot the banana") → use "missing_item", correction is the NEW separate ingredient.
5. "Same as earlier" / portion scaling: When user says "same meal as earlier but 50%", "half of what I had", "quarter of the pizza", "same as the egg noodles meal", etc., use the OTHER MEALS LOGGED TODAY context to find the matching meal and its ingredients. Replace the current ingredient with that meal's ingredients scaled by the given factor. Portion factors: half/50% → 0.5; quarter/25% → 0.25; third/33% → 0.33; three quarters/75% → 0.75. For "quarter of [food]" or "a quarter of the [food]" when referring to the current item, use quantity 0.25 (with same name/unit). Use correctionReason "portion_estimate" and set correction with the correct name, quantity (scaled), unit from the referenced meal.

IMPORTANT: Always end your response with a JSON block:
```json
{{
  "correction": {{"name": "corrected name or null", "quantity": number or null, "unit": "unit or null", "forceUseGptEstimate": true or omit, "targetCalories": number or omit, "targetProtein": number or omit}},
  "correctionReason": "misidentified" | "added_after" | "portion_estimate" | "brand_specific" | "missing_item" | "poor_usda_match",
  "shouldLearn": true/false,
  "learned": {{"mistaken": "what you thought", "actual": "what it is"}} or null,
  "complete": true/false
}}
```

RULES:
- Set "shouldLearn": true for "misidentified" AND for "brand_specific" when user specifies a brand or specific type (e.g. "Wegmans bone broth", "steel cut oats", "focaccia"). Also for corrections that refine a generic term to a specific type (e.g. bread -> focaccia, oatmeal -> steel cut oats, sauce -> Frank's RedHot).
- Set "learned" ONLY when shouldLearn is true
- Set "complete": true when the correction is finalized
- Set correction fields to null if they shouldn't change
- When correctionReason is "poor_usda_match", ALWAYS set correction.forceUseGptEstimate = true. If user says "~2 cal", "about 2 calories", "replace with 2 cal", etc., add correction.targetCalories = 2. If user says "20g protein", "should be ~20g protein", etc., add correction.targetProtein = 20
- If unsure about the reason, ASK before setting complete=true"""

        # Build messages
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add image if available
        image_b64 = get_image_base64(meal, pb_url, token)
        
        # Add conversation history
        for msg in conversation_history:
            messages.append(msg)
        
        # Add user's new message (with image on first message if available)
        if image_b64 and len(conversation_history) == 0:
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": user_message},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                ],
            })
        else:
            messages.append({"role": "user", "content": user_message})
        
        # Call GPT
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
        )
        
        raw = resp.choices[0].message.content.strip()
        
        # Parse the response - extract JSON block
        reply = raw
        correction = None
        learned = None
        complete = False
        correction_reason = None
        should_learn = False
        
        # Look for JSON block at the end
        if "```json" in raw:
            parts = raw.split("```json")
            reply = parts[0].strip()
            json_part = parts[1].split("```")[0].strip()
            try:
                data = json.loads(json_part)
                correction = data.get("correction")
                learned = data.get("learned")
                complete = data.get("complete", False)
                correction_reason = data.get("correctionReason")
                should_learn = data.get("shouldLearn", False)
                
                # Clean up null values from correction
                if correction:
                    correction = {k: v for k, v in correction.items() if v is not None}
                    if not correction:
                        correction = None
                
                # If shouldLearn is false, don't include learned data
                if not should_learn:
                    learned = None
                    
            except json.JSONDecodeError:
                pass
        
        return {
            "reply": reply,
            "correction": correction,
            "learned": learned,
            "complete": complete,
            "correctionReason": correction_reason,
            "shouldLearn": should_learn,
        }
        
    except Exception as e:
        print(f"Correction chat error: {e}")
        return {
            "reply": f"Sorry, I had trouble processing that. Could you try again? (Error: {str(e)})",
            "correction": None,
            "learned": None,
            "correctionReason": None,
            "shouldLearn": False,
            "complete": False,
        }


def gpt_estimate_nutrition(ingredient_name: str, quantity: float, unit: str, target_cal: float | None = None, target_protein: float | None = None) -> list | None:
    """
    Fallback when USDA lookup fails or returns unreasonable values.
    GPT estimates macros for the given portion.
    Optional target_cal/target_protein: when user specified (e.g. "~2 cal for black coffee"), use as hint.
    Returns nutrition array in USDA-style format: [{nutrientName, unitName, value}, ...]
    or None on error.
    """
    try:
        hint = ""
        if target_cal is not None and target_cal > 0:
            hint = f"\nUSER SPECIFIED: Use approximately {target_cal:.0f} calories."
            if target_protein is not None and target_protein >= 0:
                hint += f" Target protein: ~{target_protein:.0f}g."
        prompt = f"""Estimate nutrition for this food portion. Be conservative and realistic.
{hint}

Food: {ingredient_name}
Quantity: {quantity} {unit}

Return ONLY a JSON object with these keys (numbers only, no units in values):
- calories (number, kcal)
- protein (number, grams)
- carbs (number, grams)
- fat (number, grams)

IMPORTANT: Include ALL four keys. Sandwiches, wraps, and bread-based items have carbs from bread.

Examples:
- 8 oz black coffee: ~2 cal, 0g protein, 0g carbs, 0g fat
- 1 chicken salad sandwich: ~350 cal, 20g protein, 35g carbs, 15g fat
- 1 serving chicken salad (no bread): ~200 cal, 15g protein, 5g carbs, 14g fat
- 6 small chicken wings baked: ~280 cal, 25g protein, 0g carbs, 18g fat
- 1 egg: ~70 cal, 6g protein, 0.5g carbs, 5g fat
- 4 oz chicken breast: ~180 cal, 35g protein, 0g carbs, 4g fat
- 1 orange: ~50 cal, 1g protein, 12g carbs, 0g fat
- 1 apple: ~95 cal, 0.5g protein, 25g carbs, 0.3g fat

Return ONLY valid JSON, no markdown."""

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        raw = resp.choices[0].message.content.strip().strip("`").strip()
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
        data = json.loads(raw)
        cal = data.get("calories") or 0
        prot = data.get("protein") or 0
        carbs = data.get("carbs") or 0
        fat = data.get("fat") or 0
        # Convert to USDA-style nutrient array
        return [
            {"nutrientName": "Energy", "unitName": "KCAL", "value": round(cal, 2)},
            {"nutrientName": "Protein", "unitName": "G", "value": round(prot, 2)},
            {"nutrientName": "Carbohydrate, by difference", "unitName": "G", "value": round(carbs, 2)},
            {"nutrientName": "Total lipid (fat)", "unitName": "G", "value": round(fat, 2)},
        ]
    except Exception as e:
        print(f"GPT nutrition estimate error: {e}")
        return None
