import os
import json
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def parse_ingredients(text: str):
    prompt = f"""
    Extract foods, drinks, supplements from: "{text}".
    
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
        return json.loads(raw)
    except Exception as e:
        print("Parser error:", e, "RAW:", raw)
        return []

import base64
import requests

def parse_ingredients_from_image(meal: dict, pb_url: str, token: str | None = None):
    """
    Parses ingredients from a PocketBase image record by downloading the file locally
    and sending it to GPT-4o-mini Vision as base64.
    """
    raw = ""
    try:
        image_field = meal.get("image")
        if not image_field:
            return []

        meal_id = meal["id"]
        image_url = f"{pb_url}/api/files/meals/{meal_id}/{image_field}"

        # Download image data
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        resp = requests.get(image_url, headers=headers)
        resp.raise_for_status()
        image_bytes = resp.content

        # Encode to base64 for GPT
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        prompt = """
        Look at this image and identify ONLY edible items: foods, drinks, or supplements.
        DO NOT include: furniture, rugs, appliances, plates, mugs, utensils, household items.
        
        IMPORTANT: Decompose visible dishes into their component ingredients.
        Examples:
        - A burrito → tortilla, rice, beans, cheese, salsa, meat
        - A salad → greens, tomatoes, cucumber, dressing, croutons
        - A sandwich → bread slices, meat, cheese, lettuce, condiments
        - Fried rice → rice, egg, vegetables, soy sauce
        - Pizza slice → crust, cheese, sauce, toppings
        
        DO NOT return "burrito" or "salad" - list the actual ingredients you can see/infer!
        Simple items stay as-is: apple, coffee, eggs, chicken breast
        
        Return ONLY a JSON array (no markdown, no explanation).
        Each item must have:
        - name (string) - specific ingredient name
        - quantity (float) - estimate realistic portions:
            * Meats: oz (chicken→4, steak→6)
            * Rice/grains: cups (0.5-1)
            * Vegetables: cups (0.25-0.5)
            * Cheese: oz (1-2)
            * Sauces: tbsp (1-2)
            * Drinks: oz (8-12)
            * Supplements: count visible
        - unit (string) - oz, cup, tbsp, piece, pill, etc.
        - category (string) - "food", "drink", or "supplement"
        
        If no edible items are visible, return an empty array [].
        """

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

        raw = resp.choices[0].message.content.strip()

        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        return json.loads(raw)
    except Exception as e:
        print("Parser image error:", e, "RAW:", raw)
        return []
