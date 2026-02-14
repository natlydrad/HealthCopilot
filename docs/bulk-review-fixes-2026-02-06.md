# Bulk Review Fixes (2026-02-06) — General, Non–Hardcoded

This doc maps issues from the bulk review to **general** code/behavior changes so the same classes of errors are prevented across the board.

---

## 1. Tea / caffeinated beverages: wrong item or “not a food item”

**Review quotes:**  
- *"0 caffeine ??? also, why is it saying the earl grey tea is not a food item, it is tea and has caffeine?"*  
- *"so, oolong tea definitely has caffeine. this is the wrong item ... not the right tea ... wrong usda nutrition wise"*

**Root causes (general):**

- **Classifier:** Tea (and similar drinks) are sometimes not classified as food, so the entry is treated as non-food → no parsing → UI shows “Non-food item” and no ingredients.
- **USDA selection:** We pick a USDA result without considering “does this match the user’s intent?” for drinks (e.g. decaf vs caffeinated, or wrong tea type). We also don’t use caffeine (or other discriminators) when ranking drink matches.

**General fixes (no hardcoded “earl grey” / “oolong”):**

| Area | Action | Where |
|------|--------|--------|
| **Classifier** | Treat **all beverage entries** (tea, coffee, matcha, etc.) as having a food component so they are parsed and get ingredients. Clarify that “hydration” = plain water only; any named drink (tea, coffee, soda, etc.) is food. | `log_classifier.py`: prompts `CLASSIFICATION_PROMPT`, `CLASSIFICATION_WITH_IMAGE_PROMPT` |
| **Parser** | Already says single drink → one item; ensure **tea/coffee/cold brew** etc. are never returned as `[]`. Optional: add one line that “tea, coffee, matcha, soda, etc. are drinks and must return exactly one item when the input is only that.” | `parser_gpt.py`: `parse_ingredients` prompt |
| **USDA lookup** | For **drinks** (tea, coffee, etc.): when multiple results pass validation, **prefer the one whose nutrition matches the drink type** (e.g. prefer results with non-zero caffeine when the user did not say “decaf”). Prefer “brewed” / “beverage” forms over powder/concentrate when the query implies a prepared drink. | `lookup_usda.py`: in `usda_lookup` (and alt-query path), after building `valid` list, add a **generic** drink-aware re-rank: if query looks like a beverage (e.g. has tea/coffee/matcha/soda), score candidates by caffeine presence and/or “brewed”/“beverage” in the name, then pick best. No hardcoding of specific tea names. |
| **Validation** | Already reject keyword mismatch (e.g. pork → tea). Keep that. Optionally: **reject** a drink match when the user’s query clearly implies caffeine (e.g. “tea” without “decaf”/“herbal”) and the USDA match has 0 caffeine and 0 calories (likely decaf/herbal), so we try the next candidate. | `lookup_usda.py`: `validate_usda_match` or a small helper used only when the query is drink-like |
| **USDA re-rank** | Prefer candidates whose name shares key descriptors with the query (e.g. “green” in query → “green tea” in match; “earl grey” → black tea, not Oolong). Avoid defaulting all teas to one type. | `lookup_usda.py`: `_score_drink_match` |
| **Fallback** | When no USDA match fits the tea type (e.g. raspberry hibiscus, earl grey), prefer GPT fallback with estimated caffeine over a mismatched USDA match. Reject drink matches with negative tea-type score. | `lookup_usda.py`, `parse_api.py` |

---

## 2. Quantity wrong (e.g. “said 1 cup, not 3/4 cup”)

**Review quote:** *"said 1 cup, not 3/4 cup"*

**Root cause:** Parser or downstream logic changes an explicitly stated quantity (e.g. “1 cup”) to something else (e.g. 0.75 cup). No single place hardcodes 3/4; the issue is **fidelity to user-stated amounts**.

**General fixes:**

| Area | Action | Where |
|------|--------|--------|
| **Parser** | Add an explicit instruction: **“When the user states an exact amount (e.g. ‘1 cup’, ‘2 eggs’, ‘half’), use that exact quantity and unit. Do not substitute a different fraction or amount unless the user clearly described a portion modifier (e.g. ‘ate half of it’).”** | `parser_gpt.py`: `parse_ingredients` (and image prompt if it outputs quantity) |
| **Normalization** | **Do not overwrite** quantity/unit when they are already set and reasonable. Today we only default when quantity is missing or 0; keep that and avoid any logic that “corrects” 1 → 0.75. | `enrich_meals.py` / `parse_api.py`: `normalize_quantity` and any place that sets `ing["quantity"]` or `ing["unit"]` — ensure we never replace a valid user-stated value. |
| **Learned corrections** | When applying learned portion, only apply if the **current** parsed quantity/unit is unset or clearly generic (e.g. “1 serving”). Don’t overwrite a specific “1 cup” with a learned “0.75 cup”. | `parse_api.py` (and `enrich_meals.py` if it applies learned): where `corrected_quantity` / `corrected_unit` are applied, add a guard: if the parsed ingredient already has a specific unit (e.g. “cup”, “oz”) and a stated quantity, only apply learned portion when it’s a **name** correction, or when parsed quantity is 1 and unit is “serving”. |

---

## 2a. Count vs volume (“7 strawberries is not 1.75 cups”)

**Review quote:** *"7 strawberries is not 1.75 cups"*

**Root cause:** When the user states a discrete count (e.g. “7 strawberries”, “2 eggs”), the parser or downstream logic converts it to volume (cups), changing the meaning.

**General fixes:**

| Area | Action | Where |
|------|--------|--------|
| **Parser** | Add instruction: “When the user states a count (e.g. ‘7 strawberries’, ‘2 eggs’, ‘3 slices’), use that exact quantity and unit. Do not convert counts to volume (cups, etc.) unless the user explicitly stated volume.” | `parser_gpt.py` (text and image prompts) |
| **Unit handling** | Ensure `_has_specific_portion` and learned-correction guards treat count units (piece, pieces, strawberries, eggs, etc.) as specific; never overwrite with a volume conversion. | `parse_api.py`, `enrich_meals.py` |

---

## 3. Duplicate ingredients in the same meal

**Review quotes:** *"duplicate???", "duplicate ???", "duplicate??"* (multiple meals)

**Root cause:** Same ingredient appears twice in one meal (e.g. two lines for the same item). Current dedup is by `(name, quantity, unit)`; if the parser returns the same item with a slightly different quantity or unit, both rows are kept.

**General fixes:**

| Area | Action | Where |
|------|--------|--------|
| **Dedup** | **Merge by normalized name** (and optionally unit): when two parsed ingredients refer to the same food (same name after normalizing: lowercased, trimmed), merge into one row: keep one name, **sum** quantities if the unit is the same, or keep the larger quantity and prefer the more specific unit. Then run existing (name, quantity, unit) dedup so we don’t insert two DB rows for the same ingredient. | `parse_api.py`: where `parsed_deduped` is built (~1363), add a **pre-merge** step: group by normalized name (e.g. `name.strip().lower()`); within each group, if units are compatible (same or both “serving”), sum quantities and keep one ingredient; else keep the first. Then apply current `_ing_key` dedup. |
| **Parser** | Optional: one line in the prompt: “Do not list the same ingredient twice; combine into one line with the total quantity.” | `parser_gpt.py`: `parse_ingredients` prompt |

---

## 4. Missing nutrition data (“no data???”)

**Review quote:** *"no data???"*

**Root cause:** We matched an ingredient to a USDA (or other) source that has no or empty nutrition, and we still show it, so the user sees “no data”.

**General fixes:**

| Area | Action | Where |
|------|--------|--------|
| **USDA validation** | Already we reject when `total_macros <= 0` in `validate_usda_match`. Ensure we **never return** a USDA match that has no nutrients (or all zeros). If the best candidate has no data, try the next or return None. | `lookup_usda.py`: in `usda_lookup`, after choosing `best`, if that food’s `raw_nutrients` are empty or all zero, exclude it and pick the next valid candidate (or return None). |
| **Nutrient extraction** | Handle varied USDA response formats: nested `nutrient.amount`, top-level `value`, and `amount` in foodNutrient. Treat null for one nutrient as “unknown” for that nutrient only, not “no data” for the whole food. | `lookup_usda.py`: `_normalize_usda_nutrient`, `extract_macros` |
| **Display / API** | When we have an ingredient with no nutrition (e.g. GPT fallback with no USDA), consider showing a short “Estimated only” or “No nutrition data” so the user understands it’s not from a database. (Product decision; can be a small UI/API change.) | Dashboard / `DayDetail.jsx` or API response schema |

---

## 5. Pantry / history (“or pantry; im always eating franks red hot sauce”)

**Review quote:** *"or pantry; im always eating franks red hot sauce, as per past entries"*

**Root cause:** User expects recurring items to be recognized from history or pantry so the same product is used again. Not a bug in one place; we need to **use history/pantry more consistently** for matching.

**General fixes:**

| Area | Action | Where |
|------|--------|--------|
| **Parse API flow** | When we have a **user_id**, always consider **pantry** (and optionally **history**) **before** or in parallel with USDA: if the parsed name matches a pantry item (fuzzy or learned), use that item’s USDA/nutrition first. | `parse_api.py`: before or alongside `usda_lookup`, call `lookup_pantry_match` when user_id is present; if match and it has `usdaCode`, use that. (Similar to `enrich_meals.py`.) |
| **Learned patterns** | When the user corrects “X” → “Y” (e.g. “franks red hot” → “Frank’s Red Hot sauce”), we learn it. Ensure **pantry** is updated so the next time they say “franks red hot” we resolve to the same product. | `pb_client.py` / pantry logic: when applying a learned correction that points to a branded/specific food, add or update pantry so future parses of the same phrase hit pantry first. |

---

## 5a. USDA-first for common whole foods (“why is this a gpt ?? its literally a kiwi”)

**Review quote:** *"why is this a gpt ?? its literally a kiwi"*

**Root cause:** Simple, common whole foods (kiwi, apple, banana, etc.) fall through to GPT when USDA has valid matches.

**General fixes:**

| Area | Action | Where |
|------|--------|--------|
| **Parse API / lookup flow** | Before GPT fallback: for parsed names that look like common whole foods (short, single-word, no brand), try USDA more aggressively via `usda_lookup_valid_for_portion` (alt queries like “kiwi raw”). | `parse_api.py` |
| **Alternative queries** | Add kiwi, pear, plum to raw_foods so “kiwi raw” etc. are tried when primary USDA fails. | `lookup_usda.py`: `_alternative_usda_queries` |

---

## 5b. Preparation state (“is this cooked or raw? should be cooked”)

**Review quote:** *"is this cooked or raw? should be cooked, if not"* (ground turkey)

**Root cause:** For meat, poultry, and grains, we don’t infer or prefer preparation state. “Ground turkey” in a meal context usually means cooked.

**General fixes:**

| Area | Action | Where |
|------|--------|--------|
| **USDA selection** | When the query implies cooked (e.g. “ground turkey”, “cooked oats”, “steel cut oats”) and doesn’t say “raw”, prefer USDA matches that are cooked over raw. Add “cooked” as alternative query for meats. | `lookup_usda.py`: `_alternative_usda_queries`, `_prefer_cooked_for_meat` |
| **Ranking** | Give cooked meat matches a ranking bonus when query doesn’t say “raw”. | `lookup_usda.py` |

---

## 5c. Icon/emoji by category (“why is this a meat emoji in the tea?”)

**Review quote:** *"why is this a meat emoji in the tea? but chamomile is a great guess!!!"*

**Root cause:** Icon assignment uses keyword matching; beverages can incorrectly get the Protein (animal) / meat emoji.

**General fixes:**

| Area | Action | Where |
|------|--------|--------|
| **Framework attribution** | Ensure beverage terms are checked before Protein assignment. Never assign “Protein (animal)” / meat emoji to items whose name contains beverage keywords. | `web-dashboard/dashboard/src/utils/foodFrameworks.js`: `matchedFromKeywords` |

---

## 6. Custom / recipe items (future)

**Review quote:** *"i think i did put in a custom cookie in recently, my own recipe. we talked about gpt making a recipe and referencing that"*

**Recommendation:** This is a **feature** (custom recipes + referencing them), not a one-off fix. Leave as product/backlog; no code change in this pass.

---

## 7. Positive / no change

**Review quote:** *"perfect!!!!!"* — No change.

---

## Summary: Modify / Delete / Add

| Priority | Change | Files |
|----------|--------|--------|
| High | Classifier: beverages (tea, coffee, etc.) = food | `log_classifier.py` |
| High | USDA: prefer caffeinated / brewed match for drinks when user didn’t say decaf | `lookup_usda.py` |
| High | Parser: preserve exact stated quantity/unit | `parser_gpt.py` |
| High | USDA: tea-type consistency; reject bad tea match; GPT fallback when no good match | `lookup_usda.py`, `parse_api.py` |
| High | Parser: preserve count (do not convert to volume) | `parser_gpt.py` |
| High | Dedup: merge by normalized name, sum quantities | `parse_api.py` |
| Medium | USDA: don't return match with no nutrition data | `lookup_usda.py` |
| Medium | Nutrient extraction: handle nested/null USDA format | `lookup_usda.py` |
| Medium | Learned correction: don’t overwrite explicit quantity/unit | `parse_api.py`, `enrich_meals.py` |
| Medium | Parse API: use pantry (and history) for user when available | `parse_api.py` |
| Medium | USDA-first for common whole foods before GPT | `parse_api.py` |
| Medium | Preparation state: prefer cooked for meat/grains when implied | `lookup_usda.py` |
| Low | Optional: parser “don’t list same ingredient twice” | `parser_gpt.py` |
| Low | Optional: UI “No nutrition data” for ingredients without data | `DayDetail.jsx` / API |
| Low | Icon: beverages never get meat emoji | `foodFrameworks.js` |

All of the above are **general** rules or heuristics (e.g. “drink-like query”, “normalized name”, “explicit quantity”); none rely on hardcoded lists of specific foods or phrases beyond what’s already there (e.g. banned list, expected cal ranges).
