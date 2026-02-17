"""
Parse fidelity check: verify each parsed ingredient name is a plausible interpretation
of the original meal text (not a different product). One batch GPT call per parse.
Returns per-ingredient: status (ok | mismatch | ambiguous), why, suggestedName.
"""

import os
import re
import json
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _strip_markdown(s: str) -> str:
    s = (s or "").strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
        s = s.strip()
    return s


def _repair_json_array(raw: str) -> str:
    """Extract substring between first '[' and last ']', strip trailing commas before ']'."""
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return raw
    s = raw[start : end + 1]
    s = re.sub(r",\s*]", "]", s)
    return s


def parse_fidelity_check(meal_text: str, parsed: list, parsed_from_image: bool = False) -> list[dict]:
    """
    For each parsed ingredient, verify the parsed name is a plausible interpretation
    of the meal text (not a different product). One batch GPT call.

    Args:
        meal_text: Original meal description (or caption when parsed_from_image).
        parsed: List of parsed items, each with name, quantity, unit.
        parsed_from_image: If True, ingredients were parsed from an image (and optionally
            a caption). Use image-aware rules: do not mark mismatch solely because the
            caption does not mention the ingredient.

    Returns:
        List of dicts, same length and order as parsed. Each dict:
        {"status": "ok" | "mismatch" | "ambiguous", "why": str, "suggestedName": str | None}.
        On parse failure or exception, returns list of {"status": "ok", "why": "", "suggestedName": None}.
    """
    if not parsed:
        return []

    ingredients_blob = "\n".join(
        f"- name: \"{ing.get('name', '')}\", quantity: {ing.get('quantity', 1)}, unit: \"{ing.get('unit', 'serving')}\""
        for ing in parsed
    )

    if parsed_from_image:
        prompt = f"""You are a parse fidelity checker. The meal was parsed from an image. The caption (if any) may be generic (e.g. "1 serving") or empty.

Caption (optional):
"{meal_text or '(none)'}"

Parsed ingredients (one per line):
{ingredients_blob}

Rules:
- "ok": The parsed name plausibly describes food that could be visible in a photo. Do NOT mark mismatch just because the caption does not mention that ingredient.
- "mismatch": The ingredient clearly does not belong (e.g. parser hallucination, wrong product that could not be in the photo).
- "ambiguous": You truly cannot tell whether the ingredient could be in the photo.

When status is "mismatch" or "ambiguous", set "suggestedName" to a better name (or null if unclear). When "ok", set "suggestedName" to null.

Output ONLY a JSON array with exactly {len(parsed)} objects, in the same order as the parsed ingredients. No markdown, no explanation.
Each object: {{"status": "ok" | "mismatch" | "ambiguous", "why": "one sentence", "suggestedName": "string or null"}}
"""
    else:
        prompt = f"""You are a parse fidelity checker. The user wrote a meal description, and a parser produced a list of ingredients. For EACH parsed ingredient, decide whether the PARSED NAME is a reasonable interpretation of what the user wrote—or whether the parser substituted a DIFFERENT product.

Meal text (what the user wrote):
"{meal_text}"

Parsed ingredients (one per line):
{ingredients_blob}

Rules:
- "ok": The parsed name is a plausible interpretation of the meal text. Synonyms and normalizations are fine (e.g. "veggie" → "vegetable", "chicken breast" → "chicken").
- "mismatch": The parser substituted a DIFFERENT product than what the user wrote. Examples: user wrote "chunky salsa dip" but parser returned "salsa con queso" (cheese dip is different); "almond milk" → "whole milk"; "veggie chips" → "potato chips"; a specific brand/variety replaced by a generic or different variety.
- "ambiguous": You cannot tell from the text whether the parsed name matches (e.g. user said "salsa" and parser said "salsa con queso"—could be same or different).

When status is "mismatch" or "ambiguous", set "suggestedName" to a name that would be faithful to the meal text (or null if unclear). When "ok", set "suggestedName" to null.

Output ONLY a JSON array with exactly {len(parsed)} objects, in the same order as the parsed ingredients. No markdown, no explanation.
Each object: {{"status": "ok" | "mismatch" | "ambiguous", "why": "one sentence", "suggestedName": "string or null"}}
"""

    def _parse_raw(raw: str) -> list | None:
        raw = _strip_markdown(raw)
        try:
            out = json.loads(raw)
            if isinstance(out, list) and len(out) == len(parsed):
                return out
            return None
        except json.JSONDecodeError:
            repaired = _repair_json_array(raw)
            try:
                out = json.loads(repaired)
                if isinstance(out, list) and len(out) == len(parsed):
                    return out
            except json.JSONDecodeError:
                pass
            return None

    default_result = {"status": "ok", "why": "", "suggestedName": None}
    default_list = [dict(default_result) for _ in parsed]

    for attempt in range(2):
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
            )
            raw = (resp.choices[0].message.content or "").strip()
            out = _parse_raw(raw)
            if out is not None:
                result = []
                for i, item in enumerate(out):
                    if not isinstance(item, dict):
                        result.append(dict(default_result))
                        continue
                    status = item.get("status")
                    if status not in ("ok", "mismatch", "ambiguous"):
                        status = "ok"
                    result.append({
                        "status": status,
                        "why": str(item.get("why") or "").strip(),
                        "suggestedName": item.get("suggestedName") if item.get("suggestedName") is not None else None,
                    })
                return result
            if attempt == 0:
                print(f"   ⚠️ parse_fidelity_check parse failed (raw length={len(raw)}), retrying once...")
        except Exception as e:
            print(f"   ⚠️ parse_fidelity_check failed: {e}")
            return default_list
    return default_list
