"""
ARCHIVED: GPT-first parse flow.

Not used in the main parse path. Restore by re-integrating into parse_api.py:
1. In parse_api.py, add flow parsing from body/query and honor flow=gpt_first.
2. Use parse_ingredients_with_nutrition when parse_flow == "gpt_first".
3. In the per-ingredient nutrition lookup loop, add the gpt_first block below
   when parse_flow == "gpt_first" and scaled_nutrition is still empty.
4. Re-add imports: parse_ingredients_with_nutrition, usda_closest_match_to_estimate.
"""

# Text parse: use parse_ingredients_with_nutrition instead of parse_ingredients
# _parse_text_fn = parse_ingredients_with_nutrition if parse_flow == "gpt_first" else parse_ingredients

# Per-ingredient block when no label, no pantry nutrition, and parse_flow == "gpt_first":
#
# if not scaled_nutrition and parse_flow == "gpt_first" and any(ing.get(k) is not None for k in ("calories", "protein", "carbs", "fat")):
#     gpt_cal = float(ing.get("calories") or 0)
#     gpt_protein = float(ing.get("protein") or 0)
#     gpt_carbs = float(ing.get("carbs") or 0)
#     gpt_fat = float(ing.get("fat") or 0)
#     usda, scaled_nutrition, source_ing = usda_closest_match_to_estimate(
#         name, quantity, unit, gpt_cal, gpt_protein, gpt_carbs, gpt_fat
#     )
#     if source_ing == "gpt":
#         scaled_nutrition = [
#             {"nutrientName": "Energy", "unitName": "KCAL", "value": round(gpt_cal, 2)},
#             {"nutrientName": "Protein", "unitName": "G", "value": round(gpt_protein, 2)},
#             {"nutrientName": "Carbohydrate, by difference", "unitName": "G", "value": round(gpt_carbs, 2)},
#             {"nutrientName": "Total lipid (fat)", "unitName": "G", "value": round(gpt_fat, 2)},
#         ]
#         portion_grams = None
#     else:
#         if usda:
#             serving_size_g_used = usda.get("serving_size_g", 100)
#         portion_grams = round(get_grams_for_scaling(name, quantity, unit, usda.get("serving_size_g", 100) if usda else 100), 1)
