import os
import json
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def parse_ingredients(text: str):
    prompt = f"""
    Extract distinct foods, drinks, supplements, and vitamins from: "{text}".
    Return ONLY a JSON array (no markdown, no explanation).
    Each item must have:
    - name (string) - be specific (e.g. "vitamin D3" not just "vitamin")
    - quantity (float or null) - estimate if not specified (e.g. "steak" → 6, "chicken breast" → 150)
    - unit (string or null) - use "oz" for meats, "grams" for other proteins, "cup" for liquids when not specified
    - category (string) - one of: "food", "drink", "supplement", "other"
    
    If the text contains no food/drinks/supplements (e.g. mood notes, random text), return an empty array [].
    If someone says "second serving" or "same as before", include it as a single item with name "second serving" and quantity 1.
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
        Look at this image and identify any foods, drinks, or supplements visible.
        Return ONLY a JSON array (no markdown, no explanation).
        Each item must have:
        - name (string) - be specific (e.g. "grilled chicken breast" not just "chicken")
        - quantity (float or null) - estimate portions (e.g. chicken breast → 150, steak → 6)
        - unit (string or null) - use "grams" for proteins, "oz" for steaks, "cup" for sides/liquids
        - category (string) - one of: "food", "drink", "supplement", "other"
        
        For supplements/vitamins, identify the specific type if visible on the label.
        For non-food items (screenshots, receipts), use category "other" and describe briefly.
        If no food is visible, return an empty array [].
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
