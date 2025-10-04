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
