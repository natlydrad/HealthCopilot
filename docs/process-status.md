# Process status / work log

Carry context across sessions. At the end of a logical unit of work (or when you're done for the day), append a short session summary. Answer these when relevant:

1. **What did we implement?**
2. **What problems did we encounter?**
3. **How did we fix them?**

---

## Session summaries

*(Append new entries below with date and a 2–3 line summary.)*

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
