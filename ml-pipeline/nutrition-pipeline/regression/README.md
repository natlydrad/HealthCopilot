# Nutrition Pipeline Regression Suite

Regression tests for the nutrition parsing pipeline. Uses meal texts and expectations derived from bulk-review failures to catch regressions.

## Baseline (2026-02-14)

All 10 meals pass with `USE_PARSING_CACHE=false REGRESSION_MODE=true`.

## How to Run

**CLI (fixed suite):**

```bash
cd ml-pipeline/nutrition-pipeline
USE_PARSING_CACHE=false REGRESSION_MODE=true python regression/run_regression.py
```

**Day-based (dashboard):** In the Day view for a date, click **Run regression for this day**. The dashboard sends that day’s meals to the Parse API (`POST /regression/run-day`); each meal text is run through the same text-only parse pipeline. Pass = parse completed, at least one ingredient for non-empty text, and **production checks** (servings + nutrient sanity) pass. Results show per-meal pass/fail with expandable parsed ingredients and failure messages.

Environment variables:

- `USE_PARSING_CACHE=false` – Disable parsing cache so every run uses fresh GPT/USDA results
- `REGRESSION_MODE=true` – Sets GPT temperature to 0 for deterministic parsing/classification

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

Declarative expectations in `regression_meals.json` are evaluated first; then `evaluate_production_checks()` runs on the parsed ingredients (servings + nutrient sanity). Any failure is reported in `failures`.

## When Bulk-Review Fails but Regression Passes

- Regression uses the **text-only** path. Production also has classifier, copy-from-previous, image parsing. If the failure is in those paths, add a regression case that exercises them or document the gap.
- Learned corrections / pantry affect production. Regression runs without `user_id` (no corrections). If a bug depends on learned patterns, add a separate regression config with mock learned data.
