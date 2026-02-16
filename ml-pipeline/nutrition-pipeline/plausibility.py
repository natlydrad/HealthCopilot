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

    prompt = f"""You are a nutrition plausibility checker. For ONE logged ingredient, YOU perform the checks below and report the result of each. The user does not verify manually—you decide.

Ingredient:
- name: "{name}"
- quantity: {quantity}
- unit: "{unit}"
- calories: {calories}
- protein_g: {protein_g}
- carbs_g: {carbs_g}
- fat_g: {fat_g}
- fiber_g: {fiber_g}

Perform these checks yourself and report each result:

1) Unit conversion / portion: For this quantity and unit, are the resulting calories and macros plausible for this food? For volume portions (cups, tbsp) of dense or variable-density foods (meat, cheese, nut butter, legumes), consider whether the stated calories and macros fit that volume; if they are inconsistent with typical cooked vs raw or serving size, flag and suggest verifying cooked vs raw or weighing in grams. Result: "ok" or "suspicious" or "fail", and a one-line reason.
2) Macro–calorie consistency: expected_cal ≈ 4×protein + 4×carbs + 9×fat (within ~15%). Is the logged calorie count consistent? Result: "ok" or "fail", reason.
3) Fat / serving: For this food type and portion, is the fat amount plausible? Result: "ok" or "suspicious" or "fail", reason.
4) Protein density (only for meat, fish, poultry, eggs, high-protein dairy): Protein per calorie must be plausible for that food. If calories look reasonable for the portion but protein is implausibly low (or vice versa), treat as fail or suspicious and mention possible raw vs cooked, wrong USDA serving, or unit/portion. Do not rely on a single numeric example—apply the same logic to any implausible combo. Result: "ok" or "na" or "fail", reason.

Only set status to "suspicious" or "likely_wrong" if at least one check is "suspicious" or "fail". If all checks are "ok" (or "na" where applicable), set status to "ok".

Output exactly one JSON object (no array, no markdown, no explanation):

{{"status": "ok" | "suspicious" | "likely_wrong", "why": "One sentence summary of why this status (or 'All checks passed' if ok).", "whatToVerify": ["only include items that actually failed or were suspicious"], "confidence": 0.0-1.0, "suggestedCorrection": "One sentence or null", "checks": [{{"name": "Unit conversion", "result": "ok"|"suspicious"|"fail"|"na", "reason": "one line"}}, {{"name": "Macro–calorie consistency", "result": "ok"|"fail", "reason": "one line"}}, {{"name": "Fat / serving", "result": "ok"|"suspicious"|"fail"|"na", "reason": "one line"}}, {{"name": "Protein density", "result": "ok"|"na"|"fail", "reason": "one line"}}]}}

Rules:
- You MUST perform each check and report result and reason. "na" only when the check does not apply (e.g. protein density for non-protein-dense foods).
- status "likely_wrong" when any check is "fail" and the error is severe (e.g. macros clearly wrong). status "suspicious" when any check is "suspicious" or "fail" but not severe.
- Use general principles only; do not encode or rely on a single numeric example (e.g. one specific kcal/protein pair). Apply protein-density and portion reasonableness to all meat/volume entries.
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
                max_tokens=600,
            )
            raw = (resp.choices[0].message.content or "").strip()
            out = _parse_raw(raw)
            if out is not None and isinstance(out, dict):
                status = out.get("status")
                if status in ("ok", "suspicious", "likely_wrong"):
                    checks_raw = out.get("checks")
                    checks = []
                    if isinstance(checks_raw, list):
                        for c in checks_raw:
                            if isinstance(c, dict) and c.get("name"):
                                checks.append({
                                    "name": str(c.get("name", "")),
                                    "result": c.get("result") if c.get("result") in ("ok", "suspicious", "fail", "na") else "ok",
                                    "reason": str(c.get("reason") or ""),
                                })
                    return {
                        "status": status,
                        "why": out.get("why") or "",
                        "whatToVerify": out.get("whatToVerify") if isinstance(out.get("whatToVerify"), list) else [],
                        "confidence": float(out.get("confidence", 0.5)) if out.get("confidence") is not None else 0.5,
                        "suggestedCorrection": out.get("suggestedCorrection"),
                        "checks": checks,
                    }
            if attempt == 0:
                print(f"   ⚠️ plausibility_check_one parse failed for '{name}' (raw length={len(raw)}), retrying once...")
        except Exception as e:
            print(f"   ⚠️ plausibility_check_one failed for '{name}': {e}")
            return None
    return None
