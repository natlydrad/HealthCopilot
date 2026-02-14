# Nutrition Pipeline Regression Suite

Regression tests for the nutrition parsing pipeline. Uses meal texts and expectations derived from bulk-review failures to catch regressions.

## Baseline (2026-02-14)

All 10 meals pass with `USE_PARSING_CACHE=false REGRESSION_MODE=true`.

## How to Run

```bash
cd ml-pipeline/nutrition-pipeline
USE_PARSING_CACHE=false REGRESSION_MODE=true python regression/run_regression.py
```

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

## Adding New Expectations

Extend `evaluate_expectations()` in `run_regression.py` to support new keys. Keep expectations declarative (no code in JSON).

## When Bulk-Review Fails but Regression Passes

- Regression uses the **text-only** path. Production also has classifier, copy-from-previous, image parsing. If the failure is in those paths, add a regression case that exercises them or document the gap.
- Learned corrections / pantry affect production. Regression runs without `user_id` (no corrections). If a bug depends on learned patterns, add a separate regression config with mock learned data.
