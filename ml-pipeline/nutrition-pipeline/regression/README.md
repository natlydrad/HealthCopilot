# Nutrition Pipeline Regression Suite

Regression tests for the nutrition parsing pipeline. Uses meal texts and expectations derived from bulk-review failures to catch regressions.

**Step-by-step guide (how to use this to improve accuracy):** [docs/how-to-improve-parse-accuracy.md](../../../docs/how-to-improve-parse-accuracy.md) — what to run, what to compare, and how to know it’s working.

## Baseline (2026-02-14)

All 10 meals pass with `USE_PARSING_CACHE=false REGRESSION_MODE=true`.

## How to Run

**CLI (fixed suite):**

```bash
cd ml-pipeline/nutrition-pipeline
USE_PARSING_CACHE=false REGRESSION_MODE=true python regression/run_regression.py
```

**Day-based (dashboard):** In the Day view for a date, click **Run regression for this day**. This runs the **production** flow: clear the day (POST /clear per meal), parse everything (POST /parse per meal, same as “Parse everything”), then validate the saved ingredients via POST /regression/validate-ingredients. Pass/fail is on the same data you see in the day view. Results show per-meal pass/fail with expandable failure messages and ingredients; the day view refreshes to show the newly parsed data.

Environment variables:

- `USE_PARSING_CACHE=false` – Disable parsing cache so every run uses fresh GPT/USDA results
- `REGRESSION_MODE=true` – Sets GPT temperature to 0 for deterministic parsing/classification
- `PARSE_FLOW_TIER=mvp|full` – `mvp` = parser + USDA/GPT only (no deterministic rules, no common_sense); `full` = add rules + GPT common_sense (default, matches production text→ingredients)

Requires `OPENAI_API_KEY` and `USDA_KEY` in `.env` (or environment).

## Workflow for Fixes

1. **Before changing code:** Run regression and capture baseline (which meals pass/fail).
2. **Make one change** (e.g. fix tea scoring in `lookup_usda.py`).
3. **Run regression again.** If a previously passing meal fails, investigate before proceeding.
4. **Add new cases:** When you find a new bug in bulk review, add a meal to `regression_meals.json` with the minimal text and expectations. Re-run to ensure it fails, then fix until it passes.
5. **Commit** regression suite + code together so the suite grows over time.

## Adding New Cases

Add an entry to `regression_meals.json`:

```json
{
  "id": "short-unique-id",
  "text": "meal text to parse",
  "expectations": {
    "noOolong": true,
    "hasCaffeine": true,
    "ingredientCount": 1,
    "noDuplicates": true,
    "quantityMatches": {
      "ingredient name substring": { "quantity": 0.75, "unit": "cup" }
    },
    "sourceIsUsda": ["strawberry"],
    "noGptFor": ["kiwi"]
  },
  "note": "optional context from bulk review"
}
```

## Expectation Types

| Key | Type | Description |
|-----|------|-------------|
| `noOolong` | boolean | No ingredient name contains "oolong" |
| `hasCaffeine` | boolean | At least one drink has caffeine > 0 |
| `ingredientCount` | number | Exact number of ingredients |
| `noDuplicates` | boolean | No duplicate ingredient names |
| `quantityMatches` | object | `{ "name_substring": { "quantity": N, "unit": "..." } }` |
| `sourceIsUsda` | string[] | These ingredients must have source "usda" |
| `noGptFor` | string[] | These ingredients must NOT have source "gpt" |
| `caloriesInRange` | object/array | `{ "substr": "name", "min": N, "max": M }` – ingredient calories in range |
| `usdaMatchNameExcludes` | array | `[{ "substr": "cabbage", "exclude": "kimchi" }]` – USDA match must not contain exclude |

## Adding New Expectations

Extend `evaluate_expectations()` in `regression_runner.py` to support new keys. Keep expectations declarative (no code in JSON).

## What we check (comprehensive)

Every run (CLI suite, run-one, run-day) evaluates:

1. **Parsing** – Ingredient count, no duplicates, quantity/unit match (via expectation keys).
2. **Source** – USDA vs GPT where expected (`sourceIsUsda`, `noGptFor`).
3. **Nutrients** – Per-ingredient and per-meal sanity; optional `caloriesInRange` per ingredient.
4. **Servings** – **Production checks:** `foodGroupServings` (when present) must be non-negative and not NaN; aggregate servings across the meal must be valid.
5. **Nutrient sanity (production checks)** – Per ingredient: calories in 0–5000, protein/carbs/fat non-negative. Meal total calories in 0–5000.
6. **USDA display name** – `usdaMatchNameExcludes` to reject wrong matches (e.g. Oolong for non-tea).

Declarative expectations in `regression_meals.json` are evaluated first; then `evaluate_production_checks()` and `evaluate_invariants()` run (servings, nutrient sanity, calories ≈ 4P+4C+9F, non-negative values, portionGrams 0–2000). Any failure is reported in `failures`.

## Golden set (PocketBase)

The golden set is stored in **PocketBase** (collection `golden_entries`). Used by POST `/regression/run-golden` and CLI `run_golden.py` / `run_stability.py`. Each entry has `input.text` and `expected.ingredients` (ground truth). Comparison checks: count + canonical names; quantity/unit; **nutrient comparison** (calories, protein, carbs, fat, fiber, sugar, sodium) when present in expected ingredients' `nutrition` array — actual must be within tolerance of golden (see `acceptableRanges.nutrientTolerancePercent` default 20%, optional `caloriesTolerancePercent`); and `sourceExpectations` (e.g. `{"eggs": "usda"}` by name substring). Entries may include `category` (easy/normal/evil) for per-category scoring. The dashboard shows expected vs actual per nutrient with **pass/fail color-coding** (green/red) so errors are easy to spot.

- **Dashboard:** Golden set builder (Regression Suite): load recent meals, edit ingredients, bulk add, clear. Single-meal “Add to golden set” from a day view sends `mealId` for dedupe.
- **Clear:** `POST /regression/golden-clear` (optionally clears `inGoldenSet` on meals).
- **One-time import from file:** `POST /regression/golden-import` with body `{ "entries": [ { "input": { "text": "..." }, "expected": { "ingredients": [...] }, "category": "normal" }, ... ] }` (same shape as legacy `golden_set.json`).

**Run golden (CLI):** `python regression/run_golden.py` — loads golden set from Parse API when `PARSE_API_URL` (or `PARSE_API_BASE`) is set, else from `regression/golden_set.json` if present. Runs the set, prints summary, appends one row to `golden_results.jsonl` (timestamp, version from `PARSE_PROMPT_VERSION`, tier, pass_count, pass_rate, by_category).

**Stability judge:** `python regression/run_stability.py [--n 5] [--tier mvp|full]` — same source (API or file). Runs each golden entry N times and reports exact-structure match rate, field stability %, and calorie std variance. Use to detect prompt ambiguity at temp=0.

## When Bulk-Review Fails but Regression Passes

- Regression uses the **text-only** path. Production also has classifier, copy-from-previous, image parsing. If the failure is in those paths, add a regression case that exercises them or document the gap.
- Learned corrections / pantry affect production. Regression runs without `user_id` (no corrections). If a bug depends on learned patterns, add a separate regression config with mock learned data.
