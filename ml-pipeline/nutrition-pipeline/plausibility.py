"""
Per-ingredient plausibility check: GPT assesses whether logged macros pass a "smell test"
(e.g. protein density for meat, macro–calorie consistency, raw vs cooked / unit issues).
Returns status (ok | suspicious | likely_wrong), why, whatToVerify, confidence, suggestedCorrection.
"""

import os
import re
import json
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _macros_from_nutrition(nutrition: list) -> dict:
    """Extract calories, protein_g, carbs_g, fat_g, fiber_g from nutrition array. Missing => None."""
    out = {
        "calories": None,
        "protein_g": None,
        "carbs_g": None,
        "fat_g": None,
        "fiber_g": None,
    }
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
        if "energy" in name or name == "calories":
            unit = (n.get("unitName") or "").upper()
            if unit == "KCAL" or "kcal" in (n.get("unitName") or "").lower():
                out["calories"] = val
            elif out["calories"] is None:
                out["calories"] = val  # fallback
        elif "protein" in name:
            out["protein_g"] = val
        elif "carbohydrate" in name and "fiber" not in name and "sugar" not in name:
            out["carbs_g"] = val
        elif "lipid" in name or name == "fat" or "total lipid" in name:
            out["fat_g"] = val
        elif "fiber" in name and "dietary" in name:
            out["fiber_g"] = val
    return out


def _strip_markdown(s: str) -> str:
    s = (s or "").strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
        s = s.strip()
    return s


def _repair_json_object(raw: str) -> str:
    """Extract substring between first '{' and last '}', strip trailing commas before '}'."""
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return raw
    s = raw[start : end + 1]
    s = re.sub(r",\s*}", "}", s)
    return s


def plausibility_check_one(
    name: str,
    quantity: float,
    unit: str,
    nutrition: list,
) -> dict | None:
    """
    Run a single GPT-based plausibility check on one ingredient.

    Args:
        name: Food name (e.g. "ground beef").
        quantity: Amount (e.g. 0.75).
        unit: Unit (e.g. "cup", "oz", "g").
        nutrition: Array of { nutrientName, value, unitName } (e.g. from payload["nutrition"]).

    Returns:
        Dict with keys: status ("ok" | "suspicious" | "likely_wrong"), why, whatToVerify (list),
        confidence (float 0–1), suggestedCorrection (str or null).
        Returns None on parse failure or exception (caller should treat as neutral).
    """
    macros = _macros_from_nutrition(nutrition or [])
    calories = macros["calories"]
    protein_g = macros["protein_g"]
    carbs_g = macros["carbs_g"]
    fat_g = macros["fat_g"]
    fiber_g = macros["fiber_g"]

    prompt = f"""You are a nutrition plausibility checker. For ONE logged ingredient, decide if the macros pass a "smell test" or suggest a unit/raw-cooked/database error.

Ingredient:
- name: "{name}"
- quantity: {quantity}
- unit: "{unit}"
- calories: {calories}
- protein_g: {protein_g}
- carbs_g: {carbs_g}
- fat_g: {fat_g}
- fiber_g: {fiber_g}

Tasks:
A) Identify food type from the name (e.g. meat, legume, pure fat, veggie condiment).
B) Infer typical macro profile for that food (e.g. meat: high protein per calorie; pure fats: calories, near-zero protein/carbs; legumes: raw vs cooked differs).
C) Run plausibility checks:
   - Protein density: for meat/protein-dense foods, protein per calorie should not be implausibly low (e.g. 277 kcal with 15g protein for cooked ground beef → likely_wrong; should be ~25–30g).
   - Macro–calorie consistency: expected_cal ≈ 4×protein + 4×carbs + 9×fat. Large drift → wrong serving or missing fields.
   - Unit reasonableness: volume (cups, tbsp) for dense foods (meat, cheese, nut butter) often cause errors; suggest "Consider weighing in grams" in whatToVerify.
D) If volume units, mentally estimate typical weight and check if macros are wildly off.
E) Output exactly one JSON object (no array, no markdown, no explanation):

{{"status": "ok" | "suspicious" | "likely_wrong", "why": "Human-readable reason", "whatToVerify": ["item1", "item2"], "confidence": 0.0-1.0, "suggestedCorrection": "Optional short suggestion or null"}}

Rules:
- status "ok" when macros look reasonable for the food type and portion.
- status "suspicious" when something may be off (e.g. raw vs cooked ambiguity, volume unit for dense food).
- status "likely_wrong" when macros clearly fail the smell test (e.g. meat with very low protein for that calorie amount).
- whatToVerify: list of short strings (e.g. "raw vs cooked", "fat % of USDA entry", "unit conversion (cups → grams)").
- suggestedCorrection: one sentence or null.
- Output ONLY the JSON object, nothing else."""

    def _parse_raw(raw: str) -> dict | None:
        raw = _strip_markdown(raw)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            repaired = _repair_json_object(raw)
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                return None

    for attempt in range(2):
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
            )
            raw = (resp.choices[0].message.content or "").strip()
            out = _parse_raw(raw)
            if out is not None and isinstance(out, dict):
                status = out.get("status")
                if status in ("ok", "suspicious", "likely_wrong"):
                    return {
                        "status": status,
                        "why": out.get("why") or "",
                        "whatToVerify": out.get("whatToVerify") if isinstance(out.get("whatToVerify"), list) else [],
                        "confidence": float(out.get("confidence", 0.5)) if out.get("confidence") is not None else 0.5,
                        "suggestedCorrection": out.get("suggestedCorrection"),
                    }
            if attempt == 0:
                print(f"   ⚠️ plausibility_check_one parse failed for '{name}' (raw length={len(raw)}), retrying once...")
        except Exception as e:
            print(f"   ⚠️ plausibility_check_one failed for '{name}': {e}")
            return None
    return None
