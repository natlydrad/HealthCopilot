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
    IMPORTANT: Decompose complex/composite foods into their base ingredients.
    Examples:
    - "burrito" → tortilla, rice, beans, cheese, salsa, sour cream
    - "omelette" → eggs, butter, cheese, [any fillings mentioned]
    - "sandwich" → bread, meat, cheese, lettuce, tomato, mayo
    - "smoothie" → list the fruits/ingredients
    - "salad" → greens, vegetables, dressing
    - "pad thai" → rice noodles, egg, tofu/shrimp, peanuts, bean sprouts
    
    DO NOT return composite foods like "burrito" or "sandwich" - break them down!
    Simple items stay as-is: "apple", "coffee", "eggs", "chicken breast"
    
    Return ONLY a JSON array (no markdown, no explanation).
    Each item must have:
    - name (string) - specific ingredient name
    - quantity (float) - estimate realistic portions
    - unit (string) - use appropriate units:
        * Eggs: count (unit: "eggs")
        * Bread/tortillas: count (unit: "slice" or "piece")
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
    
    Return empty array [] if no food/drinks/supplements found.
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


def _parse_image_simple_fallback(image_b64: str, user_context: str = "") -> list:
    """Retry with a simpler prompt when main image parse returns [] or fails. Reduces false negatives."""
    prompt = """What food or drink is in this image? Return a JSON array of objects. Each object must have: "name" (string), "quantity" (number), "unit" (string, e.g. serving, cup, oz), "category" (string: food, drink, or supplement), "reasoning" (string, brief).
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


def parse_ingredients_from_image(meal: dict, pb_url: str, token: str | None = None, user_context: str = "", image_b64: str | None = None):
    """
    Parses ingredients from a PocketBase image record by downloading the file locally
    and sending it to GPT-4o-mini Vision as base64.
    
    Args:
        meal: The meal record with image field
        pb_url: PocketBase URL
        token: Auth token
        user_context: Optional personal food profile context to inject
        image_b64: Optional pre-fetched base64 image (avoids double fetch; pass from parse_api when already loaded)
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

        prompt = f"""
        STEP 1 — Decide what the user is logging:
        - If the image shows ONE packaged product (sandwich in a container, wrapped item, protein bar, bottle, etc.) with a visible Nutrition Facts label on the package → the user is logging THAT PRODUCT as one serving. Return exactly ONE item: the product name (e.g. "chicken salad sandwich" or the brand/product name). Do NOT list sub-ingredients like bread, chicken salad, etc. Read the label and fill nutritionFromLabel. Quantity = 1, unit = "serving".
        - If the image shows a homemade/composed meal (e.g. a plate with a burrito, a bowl of salad, multiple items on a plate) with NO single packaged product with a label → then decompose into ingredients (see below).
        
        DO NOT include: furniture, rugs, appliances, plates, mugs, utensils, or random items in the background. Do NOT add drinks just because a cup appears — only add a beverage if it is clearly what the user is logging.
        {context_section}
        
        When you must decompose (only for non-packaged, composed meals):
        - A burrito on a plate → tortilla, rice, beans, cheese, salsa, meat
        - A bowl of salad → greens, tomatoes, cucumber, dressing, croutons
        - Fried rice → rice, egg, vegetables, soy sauce
        List actual ingredients, not composite names.
        
        NUTRITION FACTS LABEL: When you return ONE packaged product (Step 1), only add "nutritionFromLabel" if the FULL label is visible and you can read at least Calories and Serving size. Use:
        - servingSizeG (number) - serving size in grams if shown (e.g. 30, 42)
        - calories (number) - Calories (required; if you cannot read it, omit nutritionFromLabel)
        - protein, totalCarb, totalFat, sodium, etc. (optional)
        If the label is cut off, folded, or only partially visible so you cannot read Calories, do NOT include nutritionFromLabel — leave it out so the system will use USDA instead. Do not guess or infer calories.
        
        Return ONLY a JSON array (no markdown, no explanation).
        Each item must have:
        - name (string) - specific ingredient name
        - quantity (float) - estimate realistic portions (or 1 serving if using label)
        - unit (string) - oz, cup, tbsp, piece, serving, etc.
        - category (string) - "food", "drink", or "supplement"
        - reasoning (string) - brief explanation
        - nutritionFromLabel (object, optional) - only when a Nutrition Facts label is visible for this item
        - foodGroupServings (object, optional) - estimated serving equivalents for food-group counting. Use when you can infer composition (e.g. sandwich = bread + protein + veg). Format: {{ "grains": 1, "protein": 1, "vegetables": 0.25, "fruits": 0, "dairy": 0, "fats": 0.5 }}. Use 0 for missing groups. One serving ≈ 1 slice bread, 1 oz meat, 1/2 cup veg, 1 piece fruit, 1 cup milk, 1 tsp oil.
        
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
            return _parse_image_simple_fallback(image_b64, user_context)
        return out
    except Exception as e:
        import traceback
        print("Parser image error:", e)
        print(traceback.format_exc())
        print("RAW:", (raw[:500] if raw else "(empty)"))
        # Retry with simpler prompt in case GPT returned non-JSON (e.g. explanation)
        if raw and ("[" in raw or "ingredient" in raw.lower()):
            try:
                return _parse_image_simple_fallback(image_b64, user_context)
            except Exception:
                pass
        return []


def correction_chat(
    meal: dict,
    ingredient: dict,
    user_message: str,
    conversation_history: list,
    pb_url: str,
    token: str | None = None
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
- Original reasoning: {ingredient.get('parsingMetadata', {}).get('reasoning', 'not recorded')}

Your job is to:
1. Understand what the user wants to correct
2. Determine WHY they're correcting - this is crucial for learning:
   - "misidentified": You got the food item wrong (e.g., mustard vs banana peppers) → SHOULD LEARN
   - "added_after": User added more food after the photo was taken → DON'T LEARN
   - "portion_estimate": The portion size looked different than it was → DON'T LEARN  
   - "brand_specific": User is specifying a particular brand → MAYBE LEARN (only if visually distinguishable)
   - "missing_item": User is ADDING something you missed (e.g. "add Frank's Red Hot Sauce") → the "correction" is the NEW item to add as a SEPARATE ingredient; we will NOT change the current ingredient. DON'T LEARN.
3. Have a natural conversation - if unclear, ask: "Just to make sure I learn the right thing - did I misidentify this, or are you adding something I missed?"
4. When the user says they are ADDING a missed item (e.g. "add X", "you missed X", "there was also X"), use correctionReason "missing_item" and put the NEW item in "correction" (name, quantity, unit). We will add it as a separate ingredient and leave the current one as-is.

IMPORTANT: Always end your response with a JSON block:
```json
{{
  "correction": {{"name": "corrected name or null", "quantity": number or null, "unit": "unit or null"}},
  "correctionReason": "misidentified" | "added_after" | "portion_estimate" | "brand_specific" | "missing_item",
  "shouldLearn": true/false,
  "learned": {{"mistaken": "what you thought", "actual": "what it is"}} or null,
  "complete": true/false
}}
```

RULES:
- Set "shouldLearn": true ONLY for "misidentified" (and sometimes "brand_specific" if visually distinct)
- Set "learned" ONLY when shouldLearn is true
- Set "complete": true when the correction is finalized
- Set correction fields to null if they shouldn't change
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


def gpt_estimate_nutrition(ingredient_name: str, quantity: float, unit: str) -> list | None:
    """
    Fallback when USDA lookup fails or returns unreasonable values.
    GPT estimates macros for the given portion.
    Returns nutrition array in USDA-style format: [{nutrientName, unitName, value}, ...]
    or None on error.
    """
    try:
        prompt = f"""Estimate nutrition for this food portion. Be conservative and realistic.

Food: {ingredient_name}
Quantity: {quantity} {unit}

Return ONLY a JSON object with these keys (numbers only, no units in values):
- calories (number, kcal)
- protein (number, grams)
- carbs (number, grams)
- fat (number, grams)

IMPORTANT: Include ALL four keys. Sandwiches, wraps, and bread-based items have carbs from bread.

Examples:
- 1 chicken salad sandwich: ~350 cal, 20g protein, 35g carbs, 15g fat
- 1 serving chicken salad (no bread): ~200 cal, 15g protein, 5g carbs, 14g fat
- 6 small chicken wings baked: ~280 cal, 25g protein, 0g carbs, 18g fat
- 1 egg: ~70 cal, 6g protein, 0.5g carbs, 5g fat
- 4 oz chicken breast: ~180 cal, 35g protein, 0g carbs, 4g fat

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
