# Regression System Update — Plan

**Goal:** Make the regression system day-based, align pass/fail with production behavior, and enable comprehensive checking (including nutrition servings summary and USDA/GPT nutrient sanity).

**Phase A (done):** Backend `POST /regression/run-day`; dashboard `runRegressionForDay(meals)`; Day view button “Run regression for this day” with inline pass/fail results. See `regression/README.md` and `DayDetail.jsx`. **Phase B (done):** Regression runner adds portionGrams/foodGroupServings and evaluate_production_checks; wired into run-one, run-day, CLI. **Phase C (done):** Comprehensive checklist in README; process-status updated.

---

## 1. Relevant docs and files

| Purpose | Path |
|--------|------|
| Regression suite (overview, how to run, expectations) | `ml-pipeline/nutrition-pipeline/regression/README.md` |
| Regression test data (10 meals from bulk-review 2026-02-06) | `ml-pipeline/nutrition-pipeline/regression/regression_meals.json` |
| Shared regression logic (parse + evaluate) | `ml-pipeline/nutrition-pipeline/regression/regression_runner.py` |
| CLI entrypoint | `ml-pipeline/nutrition-pipeline/regression/run_regression.py` |
| Parse API regression endpoints | `ml-pipeline/nutrition-pipeline/parse_api.py` (routes `/regression/suite`, `/regression/run-one`) |
| Dashboard regression UI | `web-dashboard/dashboard/src/RegressionSuite.jsx` |
| API calls for regression | `web-dashboard/dashboard/src/api.js` (`fetchRegressionSuite`, `runRegressionMeal`) |
| **Production: servings summary** | `web-dashboard/dashboard/src/utils/foodFrameworks.js` (`computeServingsByFramework`) |
| **Production: day view** | `web-dashboard/dashboard/src/DayDetail.jsx` (single date, meals + ingredients) |
| **Production: week view** | `web-dashboard/dashboard/src/Dashboard.jsx` (week offset, fetches meals for 7 days) |
| **Production: parse flow (metadata)** | `ml-pipeline/nutrition-pipeline/parse_api.py` (portionGrams, foodGroupServings in `parsingMetadata`) |
| **Production: foodGroupServings source** | `parser_gpt.py`, `enrich_common_sense.py`, `common_sense.py` (GPT + deterministic) |
| Project overview | `docs/project-overview.md` |
| Process status | `docs/process-status.md` |

**Current mismatch:** Regression uses **text-only** pipeline in `regression_runner.parse_meal_text_to_ingredients()` and does **not** compute `parsingMetadata.foodGroupServings` or `portionGrams`. Production day view uses those for the **nutrition servings summary** (MyPlate/Daily Dozen). So regression cannot currently fail on “servings summary errors” or full “USDA/GPT nutrients not making sense” (only partial checks: source, `caloriesInRange`).

---

## 2. Current vs desired (summary)

| Aspect | Current | Desired |
|--------|---------|---------|
| **Scope** | Fixed list of 10 meals from `regression_meals.json` (bulk-review 2026-02-06) | **Day-based:** pick a date, run regression on that day’s meals (or keep suite as secondary) |
| **View** | Standalone “Regression Suite” page (list of meal texts) | Regression **view in the day**: e.g. run from Day view for a chosen date |
| **Pass/fail** | Declarative expectations (ingredientCount, sourceIsUsda, caloriesInRange, etc.) only | **Match production:** include servings summary checks and nutrient sanity (not just calories range) |
| **Coverage** | Parsing + USDA/GPT source + some quantity/calorie checks | **Comprehensive:** parsing, USDA/GPT, **servings/food groups**, **nutrient sanity** (calories, protein/carbs/fat present and plausible) |

---

## 3. Step-by-step implementation plan

### Phase A — Day-based regression (data + API)

1. **Backend: “Regression for a date”**
   - Add endpoint (e.g. `GET /regression/day?date=YYYY-MM-DD` or `POST /regression/run-day`) that:
     - Fetches all meals for that date (via existing PocketBase/API: `fetch_meals_for_user_on_local_date` or equivalent).
     - For each meal, runs the **same parse path** used in production (or the closest possible without writing to DB: e.g. parse → USDA → GPT fallback → common-sense so that `foodGroupServings` and `portionGrams` are present).
   - Return structure: list of meals with meal id, text, and for each: parsed ingredients (including `parsingMetadata` if we run production-like path), and pass/fail per meal (and optionally per-ingredient) based on existing + new checks.

2. **Optional: fixture for “day” when no PocketBase**
   - Allow a “day regression” config (e.g. `regression_day_meals.json` or query param pointing to a fixture) so you can run day-based regression without a live user/date (e.g. 1 day with 5–10 meals).

3. **Dashboard: Regression in Day view**
   - From **Day** view (e.g. `DayDetail` for `/day/YYYY-MM-DD`):
     - Add a “Run regression for this day” (or “Regression”) control.
     - Call the new “regression for date” API; show results in a modal or inline section: pass/fail per meal, expandable details (same as current suite: failures, parsed ingredients).
   - Keep the existing **Regression Suite** page for the fixed `regression_meals.json` list; optionally add a tab or toggle: “Suite” vs “Day” (day = date picker + run for that date).

### Phase B — Pass/fail matching production

4. **Servings summary (food groups)**
   - **Option B1 (recommended):** In the backend, after parsing a meal (with a production-like path that sets `foodGroupServings` and `portionGrams`), run the **same aggregation** as the frontend: e.g. Python equivalent of `computeServingsByFramework` on the parsed ingredients, or call a small shared helper.
   - Add regression checks (or “production checks”) that:
     - Require daily (or per-meal) totals for MyPlate (or Daily Dozen) to be non-negative and, where you have expectations, within expected ranges.
     - Or at minimum: “no crash, no NaN, no negative servings” and “ingredients that should contribute to protein/veg do so” (e.g. meat has protein > 0 in foodGroupServings).
   - **Option B2:** From the dashboard, when running “regression for this day”, after fetching ingredients from the API, run `computeServingsByFramework` on the client and assert “no errors, no absurd totals”; report failures back. (Less ideal if you want regression to run without opening the app.)

5. **Nutrient sanity (USDA/GPT “making sense”)**
   - Extend `evaluate_expectations()` (or add a separate `evaluate_production_checks()`) to:
     - **Per ingredient:** Calories in reasonable range (you have `caloriesInRange`); add: protein, carbs, fat non-negative; optional: protein + carbs + fat contribution to calories ~4/4/9 per gram (sanity band).
     - **Per meal or per day:** Total calories and macros in a plausible range (e.g. meal total 50–2000 cal, no negative macros).
   - Add optional expectation keys, e.g. `nutrientSanity: true` (run these checks) or `maxCaloriesPerIngredient`, `minProtein`, etc., so existing suite doesn’t break.

6. **Production-like pipeline in regression**
   - To make “pass/fail” truly match production:
     - Either run the **full parse flow** that produces `parsingMetadata` (portionGrams, foodGroupServings) in the backend for each meal text (without writing to DB), then run servings + nutrient checks on that output; or
     - Run the existing production parse endpoint internally (e.g. create a temporary meal, call parse, read ingredients, then delete) and evaluate. Easiest match is “run real parse path, no DB” by reusing `parse_api` logic in a function that returns ingredients + metadata (refactor if needed).

### Phase C — Comprehensive checking and docs

7. **Checklist of what “comprehensive” means**
   - **Parsing:** ingredient count, no duplicates, quantity/unit match (existing).
   - **Source:** USDA vs GPT where expected (existing); optional: “no GPT for whole foods” (existing `noGptFor`).
   - **Nutrients:** calories range (existing); protein/carbs/fat present and non-negative; optional ratio/total sanity (Phase B).
   - **Servings:** food group totals non-negative, no NaN; meat/veg/grains contribute where expected (Phase B).
   - **Display name / USDA match:** no wrong USDA name (e.g. Oolong) for non-tea; optional expectations for `usda_matched_name` (existing `usdaMatchNameExcludes`).
   - Document this in `regression/README.md` and in the dashboard (e.g. “What we check” section).

8. **Regression README and process-status**
   - Update `regression/README.md`: day-based mode, new expectations, production checks, link to this plan.
   - After implementation, append a short summary to `docs/process-status.md`.

---

## 4. Suggested order of work

1. **Phase A (day-based):** Backend endpoint for “regression for date” + dashboard “Run regression for this day” in Day view. Use existing expectations first; optional fixture for offline day.
2. **Phase B (production parity):** Add production-like path (or reuse parse flow) so ingredients have `foodGroupServings`/`portionGrams`; add servings summary checks and nutrient sanity checks; wire them into day regression and optionally into suite.
3. **Phase C:** Document “comprehensive” checklist and update README/process-status.

---

## 5. Clarifications that would help

- **Day data source:** Should “regression for this day” always use **live** meals from PocketBase for the selected date (and a specific user?), or do you also want a **fixture file** (e.g. one JSON with a list of meal texts per date) so CI or offline runs don’t need the app/DB?
- **User context:** Should day regression run with a specific `user_id` (learned corrections, pantry) or without (like current suite) for reproducibility?
- **Where to show results:** Prefer “Regression” only inside Day view (one date at a time), or also keep a separate “Regression” page that can switch between “Suite” (10 meals) and “Day” (date picker)?

Once these are decided, implementation can follow the phases above.
