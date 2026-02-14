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
