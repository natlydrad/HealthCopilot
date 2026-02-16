# Parsing improvement and production E2E – master plan

Single reference for the parsing accuracy workflow, golden set structure, and what to run when.

## Goal

Improve parse accuracy using a golden set; target **~80% pass rate** on common-sense subsections (text-only, image-only, image+text); track user-personalization subsections (memory/pantry, unique inputs) separately. Use a one-change-at-a-time loop and clear production E2E.

## Golden subsections (tag values)

Each golden entry has an optional **tags** array (in addition to **category** for difficulty). Use tags to filter runs and report pass/fail by subsection.

| Tag | Meaning | Target |
|-----|---------|--------|
| **text_only** | Common sense, text-only input | ~80% pass (with 2–3 below) |
| **image_only** | Common sense, image-only input | ~80% pass |
| **image_and_text** | Common sense, image + text input | ~80% pass |
| **memory_pantry** | User personalization (learned names, pantry) | Track separately |
| **unique_inputs** | User-specific shorthand (e.g. “chx”) | Track separately |

- **Common sense (1–3):** Aim for ~80% pass rate on entries tagged with any of these (combined or per-tag).
- **Personalization (4–5):** No 80% target; measure and track separately.

## Option C: category + tags

- **category** (existing): `easy`, `normal`, or `evil` – difficulty.
- **tags** (optional array): one or more of `text_only`, `image_only`, `image_and_text`, `memory_pantry`, `unique_inputs` – subsection for filtering and reporting.

Filter and report by **both** category and tags (e.g. by_category and by_tag in run-golden output and `golden_results.jsonl`).

## Current infra summary

- **Golden set:** PocketBase collection `golden_entries`. Fields: mealId, text, expected, category, addedAt, tags. See [docs/golden-set-pocketbase-schema.md](golden-set-pocketbase-schema.md).
- **Parse API:** `ml-pipeline/nutrition-pipeline/parse_api.py` – GET `/regression/golden-set`, POST `/regression/golden-add`, `/regression/golden-add-bulk`, `/regression/run-golden` (optional `?tags=` filter, returns by_category and by_tag).
- **pb_client.py:** `fetch_golden_entries()`, `create_or_update_golden_entry(..., tags=...)`.
- **run_golden.py:** CLI in `ml-pipeline/nutrition-pipeline/regression/run_golden.py` – loads golden set from API or `golden_set.json`, optional `GOLDEN_TAGS` or `--tags` filter, prints and logs by_category and by_tag.
- **run_regression.py:** Fixed suite from `regression_meals.json` – declarative expectations per meal.
- **Dashboard:** Regression Suite (golden set builder, Run golden set), Day view (“Run regression for this day”, “Add to golden set” modal). Tags can be set in builder and in the add-to-golden modal.

## Ordered master plan

1. **Tagging** – Add `tags` to schema and PocketBase, API and dashboard UI, run_golden and API run-golden support filter + by_tag. *(Done.)*
2. **Targets** – 80% for common-sense (tags 1–3); track 4–5 (reported in by_tag).
3. **One-change loop** – As in [docs/how-to-improve-parse-accuracy.md](how-to-improve-parse-accuracy.md): one change → run golden set → compare → keep or revert.
4. **Production E2E** – Use “Run regression for this day” and run_golden as below; see “What to run when”.

## Doc map

| Doc | Purpose |
|-----|---------|
| [docs/parse-flow-breakdown.md](parse-flow-breakdown.md) | Parse flow from button to USDA/GPT: IDs and file locations (MVP → +3). |
| [docs/how-to-improve-parse-accuracy.md](how-to-improve-parse-accuracy.md) | Step-by-step: baseline, one-change loop, run golden set, log file. |
| [docs/golden-set-pocketbase-schema.md](golden-set-pocketbase-schema.md) | PocketBase `golden_entries` schema and migration for `tags`. |
| [ml-pipeline/nutrition-pipeline/regression/README.md](../ml-pipeline/nutrition-pipeline/regression/README.md) | Regression suite: run_regression, run_golden, day regression, golden set tags. |
| [docs/project-overview.md](project-overview.md) | Project components and where key logic lives. |

## What to run when

| What | When |
|------|------|
| **run_golden.py** (or dashboard “Run golden set”) | Accuracy on the golden set. Run before/after code or prompt changes. Optional filter: `GOLDEN_TAGS=text_only,image_only,image_and_text` or `--tags text_only,image_only` to run only common-sense entries. Output and log include by_category and by_tag. |
| **run_regression.py** | Fixed declarative suite (`regression_meals.json`). Catch regressions on known cases; run as part of CI or before/after changes. |
| **Run regression for this day** (dashboard) | Production E2E for a single day: clear meals, parse all (full pipeline with images, user context), validate saved ingredients. Use to verify real flow on real data. |
