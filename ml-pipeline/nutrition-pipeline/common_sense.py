"""
Meta common-sense check: one GPT call per meal to fix obvious errors
(e.g. water with calories -> 0 cal, matcha in oz -> 1 serving / 2g).
"""

import os
import re
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


def _repair_json_array(raw: str) -> str:
    """Extract substring between first '[' and last ']', strip trailing commas before ']'."""
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return raw
    s = raw[start : end + 1]
    # Remove trailing comma before ] (invalid JSON but GPT sometimes emits it)
    s = re.sub(r",\s*\]", "]", s)
    return s


def _micros_from_nutrition(nutrition: list) -> dict:
    """Extract added_sugar_g, caffeine_mg, fiber_g, sodium_mg from nutrition array. Missing => null."""
    out = {"added_sugar_g": None, "caffeine_mg": None, "fiber_g": None, "sodium_mg": None}
    if not nutrition:
        return out
    for n in nutrition:
        if not isinstance(n, dict):
            continue
        name = (n.get("nutrientName") or "").strip().lower()
        try:
            val = float(n.get("value", 0))
        except (TypeError, ValueError):
            continue
        if "sugars" in name and "added" in name:
            out["added_sugar_g"] = val
        elif name == "caffeine":
            out["caffeine_mg"] = val
        elif "fiber" in name and "dietary" in name:
            out["fiber_g"] = val
        elif "sodium" in name or name == "sodium, na":
            out["sodium_mg"] = val
    return out


def common_sense_check(meal_text: str, ingredients: list[dict]) -> list[dict]:
    """
    Review parsed ingredients for common-sense violations. Returns a list of corrections
    to apply (e.g. water/ice -> zero_calories; matcha/coffee -> 1 serving, 2g; micronutrient fixes).

    Args:
        meal_text: The meal description (for context).
        ingredients: List of dicts with at least name, quantity, unit, nutrition.
                    Optional: calories (number) for the prompt.

    Returns:
        List of correction dicts. Each may include:
        - zero_calories (bool), quantity, unit, serving_size_g (portion fixes)
        - added_sugar_g, caffeine_mg, fiber_g, sodium_mg (optional micronutrient overrides, numbers)
        Empty list if no corrections or on error.
    """
    if not ingredients:
        return []

    # Build minimal summary for the model (include current micros)
    summary = []
    for ing in ingredients:
        name = ing.get("name", "?")
        qty = ing.get("quantity", 1)
        unit = ing.get("unit", "serving")
        cal = ing.get("calories")
        if cal is None and isinstance(ing.get("nutrition"), list):
            cal = _calories_from_nutrition(ing["nutrition"])
        micros = _micros_from_nutrition(ing.get("nutrition") or [])
        summary.append({
            "name": name,
            "quantity": qty,
            "unit": unit,
            "calories": cal,
            "added_sugar_g": micros["added_sugar_g"],
            "caffeine_mg": micros["caffeine_mg"],
            "fiber_g": micros["fiber_g"],
            "sodium_mg": micros["sodium_mg"],
        })

    prompt = f"""You are a nutrition common-sense checker. Given a meal description and a list of parsed ingredients with their current quantity, unit, calories, and micronutrients (added_sugar_g, caffeine_mg, fiber_g, sodium_mg), output ONLY a JSON array of corrections for items that are clearly wrong.

Meal: "{meal_text}"

Current ingredients:
{json.dumps(summary, indent=2)}

Rules:
- Water, ice, black coffee, plain tea: should have 0 calories. If they have calories, add {{ "name": "<exact name>", "zero_calories": true }}.
- Matcha (powder or drink): people typically log one serving (~2g powder or one drink). If you see matcha with quantity in oz (e.g. 1 oz) or an absurd amount, add {{ "name": "matcha", "quantity": 1, "unit": "serving", "serving_size_g": 2 }}.
- Coffee/espresso (as a drink): one serving is typically one cup/shot. If quantity/unit is clearly wrong (e.g. 8 oz of coffee powder), suggest quantity 1, unit "serving", and serving_size_g if you know a reasonable gram weight.
- Micronutrients: when an ingredient is clearly a source of a nutrient but current value is missing or 0, you may add one or more of: added_sugar_g (number), caffeine_mg (number), fiber_g (number), sodium_mg (number). Examples: matcha/coffee/tea with 0 caffeine -> add caffeine_mg (e.g. ~25-35 mg per gram matcha, ~80-100 mg per cup coffee); whole grain/legumes with 0 fiber -> add fiber_g; sweetened item with 0 added sugar -> add added_sugar_g; packaged/savory item with 0 sodium -> add sodium_mg. Only suggest when it is an obvious error and you can estimate reasonably from context/portion; otherwise omit.
- Only output corrections for clear violations. If everything looks reasonable, return [].
- Match "name" exactly to the ingredient name from the list (case-insensitive match is ok).
- Output ONLY a JSON array. No markdown, no explanation. Example: [{{"name": "water", "zero_calories": true}}] or [{{"name": "matcha", "caffeine_mg": 56}}] or []."""

    def _strip_markdown(s: str) -> str:
        s = (s or "").strip()
        if s.startswith("```"):
            s = s.strip("`")
            if s.lower().startswith("json"):
                s = s[4:]
            s = s.strip()
        return s

    def _parse_raw(raw: str):
        raw = _strip_markdown(raw)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            repaired = _repair_json_array(raw)
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                return None

    for attempt in range(2):
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
            )
            raw = (resp.choices[0].message.content or "").strip()
            out = _parse_raw(raw)
            if out is not None and isinstance(out, list):
                return out
            if attempt == 0:
                print(f"   ⚠️ common_sense_check parse failed (raw length={len(raw)}), retrying once...")
                if raw:
                    print(f"   Raw (first 500 chars): {raw[:500]!r}")
        except Exception as e:
            print(f"   ⚠️ common_sense_check failed: {e}")
            return []
    return []
