# HealthCopilot – Project Overview

Single source of truth for architecture and key components. Use **@docs/project-overview.md** when starting a task so the AI has explicit context.

## What this project is

AI-powered nutrition tracking: meal photo/text logging, GPT-4 Vision + USDA for ingredients and nutrition, PocketBase backend, iOS app and React web dashboard. Personalization learns from user corrections.

## Main components

| Component | Location | Purpose |
|-----------|----------|---------|
| **Parse API** | `ml-pipeline/nutrition-pipeline/` | Text/image parsing, GPT + USDA lookup, serves enriched ingredients to dashboard. Entry: `parse_api.py`. Restart after code changes here. |
| **SVG Group API** | `web-dashboard/svg-group-api/` | Flask API for GPT-suggested rigging groups for SVG characters. Entry: `app.py`. Restart after changes there. |
| **Web Dashboard** | `web-dashboard/dashboard/` | React 19 + Vite; review/edit meals, corrections UI. Uses Parse API for full nutrition. |
| **Nutrition pipeline (batch)** | `ml-pipeline/nutrition-pipeline/` | Scripts: `enrich_meals.py`, `parser_gpt.py`, `lookup_usda.py`, `pb_client.py`. Batch enrichment and PocketBase sync. |
| **Regression suite** | `ml-pipeline/nutrition-pipeline/regression/` | Meal-based regression tests for parsing/lookup. Run before/after changes; add cases from bulk-review failures. See [regression/README.md](../ml-pipeline/nutrition-pipeline/regression/README.md). |
| **Backend** | `backend/` | PocketBase (SQLite-based BaaS). |
| **iOS app** | Project root (Swift/Views, Managers) | SwiftUI app, HealthKit, sync with PocketBase. |

## Tech stack

- **Backend:** PocketBase
- **Web dashboard:** React 19, Vite, Tailwind
- **ML / Parse API:** Python, OpenAI GPT-4 Vision, USDA FoodData Central
- **SVG Group API:** Python, Flask
- **iOS:** SwiftUI, HealthKit

## Where key logic lives

- **Text/meal parsing and classification:** `ml-pipeline/nutrition-pipeline/` (e.g. `parser_gpt.py`, `log_classifier.py`, `common_sense.py`)
- **USDA lookup and scoring:** `ml-pipeline/nutrition-pipeline/lookup_usda.py`
- **Parse API HTTP interface:** `ml-pipeline/nutrition-pipeline/parse_api.py`
- **Regression expectations and runner:** `ml-pipeline/nutrition-pipeline/regression/`

## Regression suite (quick ref)

- Run: `cd ml-pipeline/nutrition-pipeline && USE_PARSING_CACHE=false REGRESSION_MODE=true python regression/run_regression.py`
- Workflow: run before/after changes, one change at a time; add cases to `regression_meals.json` from bulk-review failures; commit suite + code together.
- Full details: [ml-pipeline/nutrition-pipeline/regression/README.md](../ml-pipeline/nutrition-pipeline/regression/README.md)

## More detail

- Root [README.md](../README.md) – setup, env vars, schema, deployment
- [web-dashboard/dashboard/README.md](../web-dashboard/dashboard/README.md) – dashboard env and Parse API URL
- [web-dashboard/svg-group-api/README.md](../web-dashboard/svg-group-api/README.md) – SVG Group API setup and endpoints
