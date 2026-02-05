"""
Meta common-sense check: one GPT call per meal to fix obvious errors
(e.g. water with calories -> 0 cal, matcha in oz -> 1 serving / 2g).
"""

import os
import json
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _calories_from_nutrition(nutrition: list) -> float | None:
    if not nutrition:
        return None
    for n in nutrition:
        if not isinstance(n, dict):
            continue
        name = (n.get("nutrientName") or "").lower()
        if "energy" in name or name == "calories":
            try:
                return float(n.get("value", 0))
            except (TypeError, ValueError):
                return None
    return None


def common_sense_check(meal_text: str, ingredients: list[dict]) -> list[dict]:
    """
    Review parsed ingredients for common-sense violations. Returns a list of corrections
    to apply (e.g. water/ice -> zero_calories; matcha/coffee -> 1 serving, 2g).

    Args:
        meal_text: The meal description (for context).
        ingredients: List of dicts with at least name, quantity, unit, nutrition.
                    Optional: calories (number) for the prompt.

    Returns:
        List of correction dicts: [{ "name": "water", "zero_calories": true },
        { "name": "matcha", "quantity": 1, "unit": "serving", "serving_size_g": 2 }, ...]
        Empty list if no corrections or on error.
    """
    if not ingredients:
        return []

    # Build minimal summary for the model
    summary = []
    for ing in ingredients:
        name = ing.get("name", "?")
        qty = ing.get("quantity", 1)
        unit = ing.get("unit", "serving")
        cal = ing.get("calories")
        if cal is None and isinstance(ing.get("nutrition"), list):
            cal = _calories_from_nutrition(ing["nutrition"])
        summary.append({
            "name": name,
            "quantity": qty,
            "unit": unit,
            "calories": cal,
        })

    prompt = f"""You are a nutrition common-sense checker. Given a meal description and a list of parsed ingredients with their current quantity, unit, and calories, output ONLY a JSON array of corrections for items that are clearly wrong.

Meal: "{meal_text}"

Current ingredients:
{json.dumps(summary, indent=2)}

Rules:
- Water, ice, black coffee, plain tea: should have 0 calories. If they have calories, add {{ "name": "<exact name>", "zero_calories": true }}.
- Matcha (powder or drink): people typically log one serving (~2g powder or one drink). If you see matcha with quantity in oz (e.g. 1 oz) or an absurd amount, add {{ "name": "matcha", "quantity": 1, "unit": "serving", "serving_size_g": 2 }}.
- Coffee/espresso (as a drink): one serving is typically one cup/shot. If quantity/unit is clearly wrong (e.g. 8 oz of coffee powder), suggest quantity 1, unit "serving", and serving_size_g if you know a reasonable gram weight.
- Only output corrections for clear violations. If everything looks reasonable, return [].
- Match "name" exactly to the ingredient name from the list (case-insensitive match is ok).
- Output ONLY a JSON array. No markdown, no explanation. Example: [{{"name": "water", "zero_calories": true}}] or []."""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
        )
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        out = json.loads(raw)
        if not isinstance(out, list):
            return []
        return out
    except Exception as e:
        print(f"   ⚠️ common_sense_check failed: {e}")
        return []
