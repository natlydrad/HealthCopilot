# Parse flow: from button to USDA/GPT matches and ingredients

Breakdown of every piece of code and adjustment in the flow from pressing **Parse** to the output with USDA/GPT matches and ingredients. Ordered from **True MVP** (minimal path) to **+3** (farthest refinements).

Each piece has a unique **3-digit ID** (e.g. `001`, `101`). Hundreds digit: `0` = True MVP, `1` = +1, `2` = +2, `3` = +3.

---

## Parse flow variants

**Current:** Only **name_first** is used. The day view and Parse API always use name_first. No flow toggle in the UI.

**Env:** `USE_PANTRY_AND_LEARNED` = set to `true` to enable learned corrections, pantry lookup, and add-to-pantry in the name-first path. When unset or false, parsing is "vanilla" name-first (USDA lookup + GPT fallback only).

- **name_first:** Text is parsed with `parse_ingredients` (names/portions only); then per ingredient: (if USE_PANTRY_AND_LEARNED) pantry → label → USDA lookup → validate → GPT fallback; else USDA lookup → validate → GPT fallback directly. This is the only active path.

**Archived (not selectable):** `gpt_first` was archived. Logic preserved in `parse_api_archived_gpt_first.py` for possible future restore. Previously: one GPT call for parse+nutrition, then `usda_closest_match_to_estimate` per ingredient.

---

## True MVP

Minimal path: button → call Parse API → classify → GPT parse → USDA or GPT nutrition → save → show ingredients with source.

| ID   | Piece | File(s) | Role |
|------|-------|---------|------|
| **001** | Parse button & handler | `web-dashboard/dashboard/src/DayDetail.jsx` | "Parse Now" calls `handleParse()` (~988–1030); clears errors, sets `parsing` true, calls `parseAndSaveMeal(meal)`, then `setIngredients(result.ingredients)`; handles `classificationResult`, empty-parse message, errors. |
| **002** | Parse API call | `web-dashboard/dashboard/src/api.js` | `parseAndSaveMeal(meal)` (~396–469): checks text/image, POSTs to `/parse-api/parse/${meal.id}` with auth and optional `timezone`; on success returns `{ ingredients, classificationResult, reason, source }`; on Parse API failure falls back to `parseMealSimple(meal.text)` + client-side USDA + `createIngredient`. |
| **003** | Fetch ingredients for display | `web-dashboard/dashboard/src/api.js` | `fetchIngredients(mealId)` (~126–172): prefers `GET /parse-api/ingredients/${mealId}` (full nutrition); fallback to PocketBase filter by `mealId`. |
| **004** | Show source (USDA vs GPT) | `web-dashboard/dashboard/src/DayDetail.jsx` | Uses `ing.source` for badge (~1401–1410): `usda` → "USDA", `gpt` → "GPT", `simple` → "Parsed"; uses `ing.parsingMetadata` (e.g. `partialLabel`, `foodGroupServings`) for tooltips. |
| **005** | Parse route entry | `ml-pipeline/nutrition-pipeline/parse_api.py` | `@app.route("/parse/<meal_id>", methods=["POST"])`, `parse_meal(meal_id)` (~1300): fetch meal, require text or image, then classify → if food, parse → lookup → save → return JSON. |
| **006** | Auth & meal fetch | `parse_api.py`, `pb_client.py` | `get_token()` in `pb_client.py`; Parse API uses it to GET meal from PocketBase and for clear/insert. |
| **007** | Classification (food vs non-food) | `ml-pipeline/nutrition-pipeline/log_classifier.py` | `classify_log(text)` or `classify_log_with_image(...)`; returns `categories`, `food_portion`, `non_food_portions`. If not food, API updates meal `isFood`/`categories`, writes `non_food_logs`, returns early with no ingredients. |
| **008** | GPT text parsing | `ml-pipeline/nutrition-pipeline/parser_gpt.py` | `parse_ingredients(text, user_context)` calls GPT with structured prompt; returns list of `{ name, quantity, unit, category, reasoning, ... }`. |
| **009** | USDA lookup (single match) | `ml-pipeline/nutrition-pipeline/lookup_usda.py` | `usda_lookup(ingredient_name, quantity, unit)`: USDA FDC search, pick one valid match, return `{ usdaCode, name, nutrition, serving_size_g }` or `None`. |
| **010** | Scale nutrition to portion | `ml-pipeline/nutrition-pipeline/lookup_usda.py` | `scale_nutrition(nutrients, quantity, unit, serving_size_g, ...)` converts per-100g to actual portion (`convert_to_grams` / `get_grams_for_scaling`). |
| **011** | GPT fallback when no USDA | `ml-pipeline/nutrition-pipeline/parser_gpt.py` | `gpt_estimate_nutrition(name, quantity, unit)` used when USDA lookup fails or is rejected. |
| **012** | Insert ingredient | `ml-pipeline/nutrition-pipeline/pb_client.py` | `insert_ingredient(payload)` POSTs to PocketBase `ingredients` (mealId, name, quantity, unit, nutrition, usdaCode, source, parsingMetadata, etc.). |
| **013** | GET ingredients for meal | `ml-pipeline/nutrition-pipeline/parse_api.py` | `@app.route("/ingredients/<meal_id>", methods=["GET"])` uses admin token to `fetch_ingredients_by_meal_id(meal_id)` and returns `{ items: ingredients }`. |

---

## +1 (first level of specificity)

Classification context, image parsing, basic learned/pantry, label, and core USDA validation.

| ID   | Piece | File(s) | Role |
|------|-------|---------|------|
| **101** | Image-aware classification | `log_classifier.py` | `classify_log_with_image(...)` when meal has image; uses caption + image so non-food (e.g. medication, rug) is not parsed as food. |
| **102** | Recent-meals context | `parse_api.py` | Builds `recent_meals_context` from `fetch_meals_for_user_on_local_date` / `fetch_meals_for_user_on_date` (timezone-aware) and passes to classifier. |
| **103** | Mixed entry / food_portion | `parse_api.py`, `log_classifier.py` | For mixed entries (e.g. food + symptom), only the `food_portion` string is sent to the parser instead of full log text. |
| **104** | "Same as before" / copy from previous | `parse_api.py` | `_parse_repeat_intent(raw)`; when classifier or fallback says repeat, sets `source_meal_id` and copies that meal's ingredients (with optional multiplier) instead of re-parsing. |
| **105** | User context for parsing | `parse_api.py`, `pb_client.py` | `build_user_context_prompt(user_id)`; passed as `user_context` into `parse_ingredients` so GPT can use learned names, brands, etc. |
| **106** | Image parsing | `parser_gpt.py` | `parse_ingredients_from_image(meal, PB_URL, token, ..., image_b64=..., caption=...)`; when meal has image, API loads image once and uses text-only, image-only, or both. |
| **107** | Hybrid text + image | `parse_api.py` | Logic (~1662–1690): generic caption ("1 serving", etc.) → image-only parse; else text + image, then merge/dedupe; fallback to text-only if both return 0. |
| **108** | Recipe expansion | `parser_gpt.py`, `parse_api.py` | For single composite (e.g. "banana bread") in `RECIPE_DISH_PHRASES`, `expand_recipe(text, single)` returns typical recipe; API expands to multiple ingredients and runs USDA per ingredient. |
| **109** | Quantity/unit alignment from meal text | `parse_api.py` | `_align_quantity_from_meal_text(meal_text, parsed)` aligns "N cup X" in meal text to parsed ingredient quantity/unit. |
| **110** | Merge/dedupe parsed list | `parse_api.py` | `_merge_ingredients_by_name(parsed)`; then dedupe by `(name, quantity, unit)` to avoid duplicate DB rows from text+image merge. |
| **111** | Banned ingredients filter | `parse_api.py`, `enrich_meals.py` | Skip vague or non-food parser outputs (e.g. "smoothie", "plate", "rug") via `BANNED_INGREDIENTS`. |
| **112** | Normalize quantity | `parse_api.py` | `normalize_quantity(ing)` so missing/0 quantity becomes 1 with unit "serving". |
| **113** | Learned name/portion | `parse_api.py`, `pb_client.py` | `check_learned_correction(name, user_id)`; if learned correction exists and portion is not "specific", apply corrected name and optionally quantity/unit before USDA. |
| **114** | Substring fallback for learned | `parse_api.py` | If no direct learned match, match parsed name as substring of a learned "actual" (e.g. "wegmans bone broth" → "wegmans organic chicken bone broth"). |
| **115** | Don't overwrite explicit portions | `parse_api.py` | `_has_specific_portion(ing)` (cup, oz, piece, eggs, etc.); learned portion only applied when parsed portion is generic (e.g. "1 serving"). |
| **116** | Pantry lookup | `parse_api.py`, `pb_client.py` | `lookup_pantry_match(user_id, name)` before USDA; if pantry has nutrition, scale and use it; if pantry has `usdaCode`, use `usda_lookup_by_fdc_id`. |
| **117** | Add to pantry after save | `parse_api.py` | After insert, for branded/specific or USDA-matched ingredients, `add_to_pantry(...)` so next parse can reuse. |
| **118** | Nutrition from label (GPT Vision) | `parser_gpt.py`, `parse_api.py` | Parsed ingredient may have `nutritionFromLabel`; if it has calories and enough macros, use `nutrition_from_label_to_array(...)` and set `source_ing = "label"`, `portion_grams` from `servingSizeG`. |
| **119** | Partial label overlay | `parse_api.py` | If label has some but not all (e.g. no calories), keep `partial_label_array` and later `merge_label_onto_usda(scaled_nutrition, partial_label_array)`. |
| **120** | Match validation (USDA) | `lookup_usda.py` | `validate_usda_match(ingredient_name, matched_name, macros, quantity, unit)` (and keyword-overlap check) rejects nonsensical matches (e.g. wrong form, wrong unit). |
| **121** | Calorie fit scoring | `lookup_usda.py` | `score_calorie_fit`, `get_expected_cal_range`; prefer matches whose cal/100g fits expected range for that food. |

---

## +2 (second level of specificity)

USDA sanity checks, drink/tea logic, portion scaling, display name, post-parse corrections, and merging.

| ID   | Piece | File(s) | Role |
|------|-------|---------|------|
| **201** | Per-piece calorie sanity | `lookup_usda.py` | `validate_scaled_calories(name, quantity, unit, scaled_calories)` with per-item bounds (wings, eggs, strawberries, etc.); if over bound, API rejects that USDA match and tries `usda_lookup_valid_for_portion`. |
| **202** | Scaled protein sanity (e.g. drinks) | `lookup_usda.py` | `validate_scaled_protein(name, scaled_nutrition)`; reject concentrate/serving-size mismatches (e.g. broth with huge protein); retry with `usda_lookup_valid_for_portion`. |
| **203** | Drink/tea logic | `lookup_usda.py` | `_is_drink_like_query`, `_query_implies_caffeine`, `_query_implies_decaf_or_herbal`, `_tea_type_mismatch`, `_drink_match_has_query_overlap`, `_score_drink_match_for_ordering`; reject wrong tea type (e.g. Oolong for "sleepy tea"), prefer caffeine/calorie-appropriate drink matches. |
| **204** | Alternative USDA queries | `lookup_usda.py` | `_alternative_usda_queries(ingredient_name)` (e.g. "matcha" → "matcha beverage"); used when first query has results but none pass validation. |
| **205** | Common-whole-food retry | `parse_api.py` | For items in `_is_common_whole_food(name)`, if first `usda_lookup` fails, call `usda_lookup_valid_for_portion(name, quantity, unit)`. |
| **206** | USDA display name vs parsed name | `parse_api.py` | `_usda_display_name_ok(parsed_name, usda_name)` requires word overlap; if USDA name is wrong (e.g. "Oolong tea" for "pork"), keep parsed name and use GPT estimate instead of that USDA. |
| **207** | Food-specific piece weights | `lookup_usda.py` | `PIECE_GRAMS_BY_FOOD`, `get_piece_grams(name)`, `use_piece_grams_for_portion(...)` so "7 strawberries", "2 eggs", etc. use per-piece grams. |
| **208** | Cooked oats dry equivalent | `lookup_usda.py` | `_cooked_oats_dry_grams`, `DRY_GRAMS_PER_CUP_COOKED_OATS`; "1 cup cooked steel cut oats" → 40g dry for scaling against raw USDA oats. |
| **209** | portionGrams in metadata | `parse_api.py` | Stored in `parsingMetadata.portionGrams` for display/analytics (effective grams used for scaling). |
| **210** | Deterministic rules | `enrich_common_sense.py`, YAML | `apply_deterministic_rules(minimal)` from `common_sense_rules.yaml`: zero-cal (water, ice), caffeine for tea/coffee, fiber/sodium, portion fixes, etc., applied before GPT common-sense. |
| **211** | GPT common-sense | `common_sense.py` | `common_sense_check(meal_text, minimal)` one GPT call per meal to fix obvious errors (e.g. water with calories → 0, matcha in oz → 1 serving / 2g). |
| **212** | Applying corrections to pending | `parse_api.py` | `_apply_single_correction(pending, corr, scale_nutrition, zero_calorie_nutrition_array, merge_micro_overrides_into_nutrition, trace, source)`; rebuilds `minimal` after deterministic so GPT sees corrected state (including `foodGroupServings`). |
| **213** | Merge by same USDA product | `parse_api.py` | `_merge_pending_by_usda(pending)` so "frank's red hot" and "red hot sauce" that map to same USDA become one ingredient. |
| **214** | Merge by similar name intent | `parse_api.py` | `_merge_pending_by_similar_name_intent(pending)` (e.g. same user phrase → keep sauce, drop pickles). |
| **215** | Clear before parse / duplicate safety | `parse_api.py` | `_clear_meal_ingredients_internal(meal_id)` before adding (copy or parse); re-check remaining and retry clear once to avoid duplicates. |
| **216** | Parse fidelity check | `parse_api.py`, `parse_fidelity.py` | After merge/dedupe/align, one GPT call (`parse_fidelity_check(meal_text, parsed, parsed_from_image=...)`) to verify each parsed name matches meal text; when source is image or both, fidelity uses an image-aware rule so caption-only mismatches are not flagged; result attached to each `ing` and stored on ingredient; mismatch/ambiguous override plausibility to `parse_mismatch`. |

---

## +3 (third level of specificity)

Diagnostics, UX feedback, and regression.

| ID   | Piece | File(s) | Role |
|------|-------|---------|------|
| **301** | Trace in response | `parse_api.py` | `trace` list with steps (meal_fetched, classify_done, parse_done, usda_lookup, saved_ingredient, etc.); dashboard `flowLog.add` from `data.trace`. |
| **302** | Empty-parse reason | `parse_api.py`, `DayDetail.jsx` | API returns `reason` (e.g. "from text: 0, from image: 0"); UI shows `emptyParseMessage` and `emptyParseReason` so user is not stuck. |
| **303** | Regression mode | `parser_gpt.py` | `REGRESSION_MODE=true` sets temperature 0 for reproducible parsing in regression suite. |

---

## ID index (quick lookup)

| ID   | Tier   | Piece (short) |
|------|--------|----------------|
| 001  | MVP    | Parse button & handler |
| 002  | MVP    | parseAndSaveMeal |
| 003  | MVP    | fetchIngredients |
| 004  | MVP    | Show source (USDA/GPT) |
| 005  | MVP    | Parse route entry |
| 006  | MVP    | Auth & meal fetch |
| 007  | MVP    | Classification (food vs non-food) |
| 008  | MVP    | GPT text parsing |
| 009  | MVP    | USDA lookup (single match) |
| 010  | MVP    | Scale nutrition to portion |
| 011  | MVP    | GPT fallback when no USDA |
| 012  | MVP    | Insert ingredient |
| 013  | MVP    | GET ingredients for meal |
| 101  | +1     | Image-aware classification |
| 102  | +1     | Recent-meals context |
| 103  | +1     | Mixed entry / food_portion |
| 104  | +1     | "Same as before" / copy from previous |
| 105  | +1     | User context for parsing |
| 106  | +1     | Image parsing |
| 107  | +1     | Hybrid text + image |
| 108  | +1     | Recipe expansion |
| 109  | +1     | Quantity/unit alignment from meal text |
| 110  | +1     | Merge/dedupe parsed list |
| 111  | +1     | Banned ingredients filter |
| 112  | +1     | Normalize quantity |
| 113  | +1     | Learned name/portion |
| 114  | +1     | Substring fallback for learned |
| 115  | +1     | Don't overwrite explicit portions |
| 116  | +1     | Pantry lookup |
| 117  | +1     | Add to pantry after save |
| 118  | +1     | Nutrition from label |
| 119  | +1     | Partial label overlay |
| 120  | +1     | Match validation (USDA) |
| 121  | +1     | Calorie fit scoring |
| 201  | +2     | Per-piece calorie sanity |
| 202  | +2     | Scaled protein sanity |
| 203  | +2     | Drink/tea logic |
| 204  | +2     | Alternative USDA queries |
| 205  | +2     | Common-whole-food retry |
| 206  | +2     | USDA display name vs parsed name |
| 207  | +2     | Food-specific piece weights |
| 208  | +2     | Cooked oats dry equivalent |
| 209  | +2     | portionGrams in metadata |
| 210  | +2     | Deterministic rules |
| 211  | +2     | GPT common-sense |
| 212  | +2     | Applying corrections to pending |
| 213  | +2     | Merge by same USDA product |
| 214  | +2     | Merge by similar name intent |
| 215  | +2     | Clear before parse / duplicate safety |
| 216  | +2     | Parse fidelity check |
| 301  | +3     | Trace in response |
| 302  | +3     | Empty-parse reason |
| 303  | +3     | Regression mode |
