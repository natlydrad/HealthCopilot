import os
import json
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def parse_ingredients(text: str):
    prompt = f"""
    Extract distinct foods from: "{text}".
    Return ONLY a JSON array (no markdown, no explanation).
    Each item must have:
    - name (string)
    - quantity (float or null)
    - unit (string or null)
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
        Look at this image of a meal and identify the distinct foods and approximate quantities.
        Return ONLY a JSON array (no markdown, no explanation).
        Each item must have:
        - name (string)
        - quantity (float or null)
        - unit (string or null)
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
