# Process status / work log

Carry context across sessions. At the end of a logical unit of work (or when you're done for the day), append a short session summary. Answer these when relevant:

1. **What did we implement?**
2. **What problems did we encounter?**
3. **How did we fix them?**

---

## Session summaries

*(Append new entries below with date and a 2–3 line summary.)*

**2026-02-16 — Repeat intent: anchor cues, trailing text, food-based source meal**

1. parse_api.py: Rewrote _parse_repeat_intent to use a small anchor set (another, more, same, again, repeat, second, third, same as, like before, like earlier) with trailing text allowed (e.g. "2 more cookies", "another coffee"). Extracts multiplier (digits or number-words) and mentioned_food. Added _pick_source_meal_for_repeat: when food is mentioned, finds most recent meal with matching ingredient; otherwise uses most recent meal. _ingredient_matches_food does flexible substring/token matching. Restarted parse API.
2. None.
3. N/A

**2026-02-16 — Always use USDA canonical name when USDA match is used**

1. parse_api.py: when we have a valid USDA match and use its nutrition, we now always set display_name to the USDA canonical name (usda.get("name", ing["name"])). Removed the one-word exception that preferred parsed name over USDA "Word, rest"; _usda_display_name_ok is still used only to reject wrong matches (e.g. pork → Oolong tea). Restarted parse API.
2. None.
3. N/A

**2026-02-16 — Parse fidelity: do not overwrite main ok with display mismatch**

1. Display fidelity was overwriting main fidelity: for "3/4 cup pork shoulder" main correctly returned ok (parsed "pork shoulder"), then display fidelity ran on USDA name "Pork, Shoulder breast, ... cooked, broiled" and returned mismatch, so the UI showed Parse mismatch. parse_api.py now only applies display fidelity result when display is "ok" or when main was not "ok", so main "ok" is never overwritten by display "mismatch"/"ambiguous".
2. N/A
3. N/A

**2026-02-16 — Parse fidelity: reduce false positives**

1. Updated text-based fidelity prompt in parse_fidelity.py: added explicit "Do NOT flag" rules (cooking state when unspecified, USDA-style normalization, generic→specific same product) and "DO flag" rules (different product type, wrong variety/brand, opposite qualifier when user was explicit); added four example judgments (pork shoulder ok, green tea ok, almond milk mismatch, raw pork mismatch). Restarted parse API.
2. None.
3. N/A

**2026-02-16 — Fidelity before plausibility**

1. Parse API: run wrong-product (fidelity) before plausibility (macro). In the single plausibility loop, if parseFidelityStatus is mismatch or ambiguous we set plausibilityStatus to parse_mismatch from parseFidelityResult and skip plausibility_check_one; otherwise we call plausibility_check_one as before. Removed the separate override loop that set parse_mismatch after plausibility.
2. None.
3. N/A

**2026-02-16 — Image-based parse fidelity**

1. Fidelity check now treats image-based parses (source gpt_image or gpt_both) with an image-aware prompt: ingredients are not marked mismatch solely because the caption is generic or empty; only clear hallucinations or wrong-product get mismatch. parse_api.py passes `parsed_from_image=(source in ("gpt_image", "gpt_both"))` into `parse_fidelity_check`; parse_fidelity.py adds `parsed_from_image` param and a second prompt for image mode. docs/parse-flow-breakdown.md step 216 updated.
2. None.
3. N/A

**2026-02-16 — Parse fidelity check**

1. Implemented parse fidelity check per plan: new `parse_fidelity.py` with one batch GPT call (`parse_fidelity_check(meal_text, parsed)`) returning per-ingredient status (ok/mismatch/ambiguous), why, suggestedName. Parse API: run fidelity after merge/dedupe/align; attach results to parsed; add parseFidelityStatus/parseFidelityResult to payload and copy path; after plausibility loop, override to plausibilityStatus "parse_mismatch" when fidelity is mismatch/ambiguous. Dashboard: purple UI for parse_mismatch (badge "Parse mismatch", row and expandable with border-purple / bg-purple-50). docs/parse-flow-breakdown.md: step 216.
2. None.
3. N/A

**2026-02-16 — Nutrition examples in parse_ingredients_with_nutrition**

1. Added concrete per-food nutrition examples to the gpt_first parse prompt: new `_NUTRITION_EXAMPLES` constant (10 examples: egg, chicken breast, wings, apple, orange, strawberries, black coffee, cooked rice, cabbage, whole milk) in the same style as gpt_estimate_nutrition. Injected after `_CALIBRATION_HINTS` in the parse_ingredients_with_nutrition prompt so the model has clear numeric targets for stated portions.
2. None.
3. N/A

**2026-02-14 — Dashboard Regression Suite**

1. Implemented dashboard-integrated regression testing: new RegressionSuite view at `/regression` loads regression_meals.json from Parse API, runs each meal with bounded concurrency, displays pass/fail per meal with expandable failure details and parsed ingredients. Parse API endpoints: GET `/regression/suite`, POST `/regression/run-one`. Extracted shared logic into `regression_runner.py`; `run_regression.py` now imports from it. Added "Add to regression" modal in DayDetail: generates JSON snippet from meal text + expectations for copy-paste into regression_meals.json.
2. No major issues.
3. N/A

**2026-02-14 — Regression Phase B & C (production parity + docs)**

1. Phase B: Regression runner now adds `portionGrams` and `foodGroupServings` (via deterministic rules and parsingMetadata). Applied `foodGroupServings` from enrich_common_sense corrections in `_apply_corrections`. Added `evaluate_production_checks()`: servings sanity (foodGroupServings non-negative, no NaN; aggregate valid) and nutrient sanity (per-ingredient calories 0–5000, macros non-negative; meal total calories 0–5000). Wired production checks into `/regression/run-one`, `/regression/run-day`, and CLI `run_regression.py`. Phase C: Documented comprehensive checklist in regression README (parsing, source, nutrients, servings, nutrient sanity, USDA display name) and added expectation types for `caloriesInRange` and `usdaMatchNameExcludes`.
2. None.
3. N/A

**2026-02-14 — Golden set + Mark as correct outcome**

1. Golden set: new `regression/golden_set.json` with version, description, entries (id, input.text, expected.ingredients, category, addedAt). Parse API: GET `/regression/golden-set`, POST `/regression/golden-add` (sanitize ingredients, unique id from text slug), POST `/regression/run-golden` (parse each entry, compare actual vs expected, run production checks). Regression runner: `_canonical_ingredient_name()` and `compare_golden_actual_to_expected()` for count + canonical name set equality. Frontend: `addToGoldenSet()` in api.js; DayDetail "Add to golden set" button (when meal has ingredients) + AddToGoldenSetModal (category Easy/Normal/Evil, success message); Regression Suite "Run golden set" section with same pass/fail + expandable failures and actual ingredients.
2. None.
3. N/A

**2026-02-14 — Parse flow gaps (tier, invariants, golden comparison, versioning, stability)**

1. Implemented full parse-flow-gaps plan: (1) Pipeline parity and MVP vs full tier: `parse_meal_text_to_ingredients(text, tier)` with `PARSE_FLOW_TIER=mvp|full`; tier=full runs deterministic rules + `common_sense_check` in regression; tier=mvp skips both. Extended `_apply_corrections` for common_sense (quantity/unit/serving_size_g re-resolve USDA, added_sugar_g/sodium_mg). (2) Invariants: `evaluate_invariants()` (calories ≈ 4P+4C+9F, non-negative, portionGrams 0–2000); wired into run_regression and run-golden. (3) Extended golden comparison: `compare_golden_actual_to_expected(..., expected_options)` for quantity/unit, acceptableRanges, sourceExpectations. (4) Versioning and score log: `run_golden.py` and run-golden API (optional ?log=1) append to `golden_results.jsonl`. (5) Stability judge: `run_stability_check()` and `run_stability.py` CLI.
2. None.
3. N/A

**2026-02-14 — Golden set in PocketBase (full plan)**

1. Completed Golden set in PocketBase: (1) Schema doc `docs/golden-set-pocketbase-schema.md`; pb_client CRUD for `golden_entries` + `set_meal_in_golden_set`. (2) Parse API: GET/POST golden-set and golden-add from PocketBase; golden-add-bulk, golden-clear, run-golden from PB; GET recent-meals. (3) Dashboard: Golden set builder (load recent meals, select, bulk add, clear), EditGoldenIngredientsModal; DayDetail sends mealId to golden-add. (4) CLI: run_golden.py and run_stability.py load from PARSE_API_URL when set, else golden_set.json. (5) POST /regression/golden-import for one-time file import; docs updated (how-to-improve-parse-accuracy, regression README).
2. EditGoldenIngredientsModal was missing—added inline in RegressionSuite.jsx with JSON textarea and Save/Cancel.
3. N/A

**2026-02-15 — Golden set in day view**

1. Day view: when `inGoldenSet === true`, meal card shows golden styling (ring + left border). "Add to golden set" becomes "Remove from golden set" when in set; button moved to bottom left of card (footer row). Backend: `delete_golden_entry_by_meal_id` in pb_client, POST `/regression/golden-remove-one`; frontend `removeFromGoldenSet(mealId)`. AddToGoldenSetModal onAdded calls `onMealUpdated(meal.id, { inGoldenSet: true })` so card turns golden without refetch.
2. None.
3. N/A

**2026-02-16 — Parsing master plan and golden set tags**

1. Implemented parsing master plan and golden tags: (1) Schema + migration: `tags` (JSON array) on `golden_entries`, doc in golden-set-pocketbase-schema.md, migration script `scripts/add_golden_tags_field.py`, setup script creates collection with tags for new installs. (2) pb_client: `GOLDEN_TAG_VALUES`, `_normalize_golden_tags()`, `create_or_update_golden_entry(..., tags=)`. parse_api: golden-set/golden-add/golden-add-bulk/golden-import accept and return tags; run-golden supports ?tags= filter and returns by_category + by_tag. (3) run_golden.py: `GOLDEN_TAGS` env and `--tags` CLI filter, by_tag aggregation and log. (4) Dashboard: RegressionSuite builder Tags column (multi-select for text_only, image_only, image_and_text, memory_pantry, unique_inputs); DayDetail AddToGoldenSetModal tags checkboxes; api.js addToGoldenSet(..., tags). (5) docs/parsing-master-plan.md with goal, tag subsections, infra, ordered plan, doc map, what to run when. Updated golden-set-pocketbase-schema.md and regression README with tags section.
2. None.
3. N/A

**2026-02-16 — Golden set: tags required, category optional, button styling**

1. Tags required: schema and pb_client require at least one tag on create/update (ValueError); golden-add returns 400 if missing; modal and RegressionSuite require at least one tag (Add disabled otherwise). Category optional: schema and backend only send category when valid (easy/normal/evil); modal category removed; RegressionSuite Difficulty column has “—” option. Add/Remove from golden set in DayDetail are solid buttons (amber-100, rounded-lg) instead of link-style text.
2. None.
3. N/A

**2026-02-16 — Simple correct in export-for-review bar (like add ingredient)**

1. In the bulk-review row under each ingredient: “Correct to…” input + Apply. Apply now saves immediately (send correction message → save correction → refresh ingredients), no preview popup. Same flow as add ingredient: type and Apply; only alert on failure or when API can’t interpret.
2. User reported a popup and nothing worked with the previous two-step (preview + Confirm).
3. Removed pending/Confirm/Cancel; single Apply that calls sendCorrectionMessage then saveCorrection and refreshes.

**2026-02-16 — Plausibility checker (parse-time + UI)**

1. Implemented GPT-based per-ingredient plausibility check: new `plausibility.py` with `plausibility_check_one(name, quantity, unit, nutrition)` returning status (ok/suspicious/likely_wrong), why, whatToVerify, confidence, suggestedCorrection. Integrated in parse_api after common_sense, before insert_ingredient; copy flow includes plausibilityStatus/plausibilityResult. PocketBase migration 1759900012 adds plausibilityStatus (text) and plausibilityResult (json) to ingredients. DayDetail: row color by plausibility (red/amber), "Verify" badge with tooltip (why, whatToVerify, suggestedCorrection).
2. None.
3. N/A

**2026-02-16 — Plausibility prompt: principle-based only (no fixed numeric examples)**

1. Updated plausibility checker prompt and doc so the model generalizes: removed single numeric examples (e.g. 277 kcal / 15g protein, 25–30g) from `plausibility.py` and `docs/plausibility-check-prompt.md`. Check 1 (unit/portion) now states principles for volume portions of dense foods (meat, cheese, nut butter, legumes): consider cooked vs raw and serving; flag and suggest verifying or weighing in grams. Check 4 (protein density): protein per calorie must be plausible for that food; flag when implausibly low/high and mention raw vs cooked, wrong USDA serving, unit/portion. Added rule: use general principles only, no single numeric example. Doc examples rewritten as principle-based (meat/volume, legumes raw/cooked) without fixed numbers.
2. None.
3. N/A

**2026-02-16 — GPT-first parse flow (optional, behind PARSE_FLOW)**

1. Implemented optional GPT-first parse flow per plan: (1) `PARSE_FLOW` env = `name_first` (default) | `gpt_first`. (2) `parser_gpt.parse_ingredients_with_nutrition` already present; used for text path when gpt_first. (3) `lookup_usda.usda_closest_match_to_estimate(name, qty, unit, gpt_cal, gpt_protein, gpt_carbs, gpt_fat)` returns (usda_dict|None, scaled_nutrition, source); scores USDA candidates by weighted relative error to GPT estimate, threshold via `GPT_FIRST_USDA_FIT_THRESHOLD` (default 0.45). (4) parse_api: read PARSE_FLOW, branch parsing to use consolidated parser when gpt_first; per-ingredient (when no label/pantry) use closest_match for text-derived items with GPT nutrition, else name_first path; trace includes flow. (5) regression_runner: `parse_meal_text_to_ingredients(text, tier, flow)`; gpt_first path uses parse_ingredients_with_nutrition + usda_closest_match_to_estimate; tier=full still applies deterministic rules and common_sense. (6) run_golden.py and POST `/regression/run-golden`: support PARSE_FLOW/flow, log `flow` in golden_results.jsonl. (7) Docs: parse-flow-breakdown.md (PARSE_FLOW variants), how-to-improve-parse-accuracy.md (run golden with gpt_first).
2. None.
3. N/A

**2026-02-16 — Parse path toggle on day view**

1. Dashboard: toggle at top of day view to switch parse path (Name first | GPT first); choice persisted in localStorage and sent with every parse request. parse_api accepts optional `flow` in POST body to override PARSE_FLOW for that request. api.js: parseAndSaveMeal(meal, options) supports options.flow.
2. None.
3. N/A

**2026-02-16 — GPT-first: widen USDA acceptability threshold**

1. Increased `GPT_FIRST_USDA_FIT_THRESHOLD_DEFAULT` from 0.45 to 0.65 so more USDA matches are accepted instead of defaulting to GPT. Previously almost every item was marked as GPT due to overly strict fit scoring.
2. None.
3. N/A

**2026-02-16 — Archive GPT-first, name-first only, disable pantry/learned**

1. Archived GPT-first parse flow: logic moved to `parse_api_archived_gpt_first.py`; parse_api and regression always use name_first. Day view: removed flow toggle and localStorage; always passes flow "name_first". Temporarily disabled pantry, learned corrections, and add-to-pantry in name-first path; gated behind `USE_PANTRY_AND_LEARNED=true` (when unset, parsing is vanilla name-first: USDA + GPT fallback only).
2. None.
3. N/A
