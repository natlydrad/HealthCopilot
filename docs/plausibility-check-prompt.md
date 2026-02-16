# Plausibility Check: Structured Prompt for Implementation

Use this prompt when you're ready to plan and implement the plausibility checker. It contains all context needed for a good plan.

---

## One-line goal

Add a GPT-based plausibility checker that runs **at parse time**, assigns a confidence status to each ingredient, persists it in the ingredients collection schema, and color-codes ingredients in Day View (ok = green, suspicious = yellow, likely_wrong = red).

---

## Context files

- **@web-dashboard/dashboard/src/DayDetail.jsx** – ingredient rows, `getNutritionArray`, `isLowConfidence`, meal cards
- **@ml-pipeline/nutrition-pipeline/common_sense.py** – existing GPT common-sense check (meal-level, corrections); similar pattern for plausibility
- **@ml-pipeline/nutrition-pipeline/parse_api.py** – parse flow, where checks run, trace
- **@ml-pipeline/nutrition-pipeline/lookup_usda.py** – USDA lookup, scaling, `validate_usda_match`, `validate_scaled_protein`, `validate_scaled_calories`
- **@docs/parse-flow-breakdown.md** – parse flow IDs (common_sense = 211, etc.)
- **@web-dashboard/dashboard/src/api.js** – `fetchIngredients`, ingredient schema
- **@ml-pipeline/nutrition-pipeline/pb_client.py** – `insert_ingredient`, ingredients payload

---

## Current vs desired behavior

### Current

- Parsed ingredients show in Day View with source badges (USDA, GPT, etc.) and low-confidence flag (`isLowConfidence` based on USDA presence and nutrition).
- No macro plausibility check: entries like "1/2 cup lentils" or "3/4 cup cooked ground beef" can have USDA matches with wrong raw/cooked or unit conversion, resulting in calories/macros that are clearly wrong.
- Example failure type: calories that look reasonable for the portion but protein implausibly low (or vice versa) for that food → suggests raw/cooked mismatch, wrong USDA serving, or bad unit/portion. We detect these manually by "smell test" — we don't have automated plausibility.

### Desired

- **Per-ingredient plausibility check** runs **during the parse flow** (after USDA/GPT nutrition, before or after common_sense).
- GPT uses general nutrition knowledge to infer food type and typical macro profiles on the fly (no pre-stored ranges).
- Produces structured output: `status` (ok | suspicious | likely_wrong), `why`, `whatToVerify`, `confidence`, optional `suggestedCorrection`.
- **Persist to DB:** Each ingredient gets a **new schema field** (e.g. `plausibilityStatus` or `plausibility`) storing this result. Assigned at parse time, saved with the ingredient.
- **UI:** Day View reads the field and **color-codes** each ingredient row: ok (normal), suspicious (amber/yellow), likely_wrong (red).
- Tooltip or expandable area shows `why` and `whatToVerify` so the user knows what to fix.

**Scope:** Both **parsing flow changes** (run plausibility, write field) and **UI changes** (read field, apply color).

---

## Inputs (from Day View / ingredient schema)

For each ingredient row:

| Field       | Source                      | Notes                            |
|------------|-----------------------------|----------------------------------|
| name       | `ing.name`                  | Food name (e.g. "ground beef")   |
| amount     | `ing.quantity`              | Number (e.g. 0.5, 1, 2)          |
| unit       | `ing.unit`                  | cup, oz, g, serving, tbsp, etc.  |
| calories   | From `nutrition` array      | Energy in KCAL                   |
| protein_g  | From `nutrition` array      | Protein                          |
| carbs_g    | From `nutrition` array      | Optional                         |
| fat_g      | From `nutrition` array      | Optional                         |
| fiber_g    | From `nutrition` array      | Optional                         |

Ingredients come from `fetchIngredients`; nutrition is in `ing.nutrition` or `ing.scaled_nutrition` as array of `{ nutrientName, value, unitName }`.

---

## GPT tasks per ingredient

### A) Identify food type from the name

Examples:

- "ground beef" → meat / protein-dense animal food
- "lentils" → legume
- "egg" → whole egg
- "salsa" → low-cal veggie condiment
- "nut butter" → pure fat / high-fat spread

### B) Infer a "typical macro profile" on the fly

Without a lookup table, GPT infers rules such as:

- **Meat / poultry / fish** – high protein relative to calories; protein per calorie must be in a plausible range for that food. If calories look reasonable for the portion but protein is implausibly low (or vice versa), treat as fail/suspicious and mention possible raw vs cooked, wrong USDA serving, or unit/portion.
- **Pure fats** – calories but near-zero protein/carbs
- **Vegetables / condiments** – low calorie
- **Legumes** – carbs + fiber + some protein; raw vs cooked differs sharply—flag when stated calories/macros don't match typical cooked vs raw for the portion.

### C) Run plausibility checks

Use general principles only—no fixed numeric examples (so the model generalizes to all implausible meat/portion combos):

1. **Protein density check** – For meat/poultry/fish (and similar protein-dense foods), protein per calorie must be plausible for that food. If calories look reasonable for the portion but protein is too low (or vice versa), treat as fail/suspicious and mention possible raw vs cooked, wrong USDA serving, or unit/portion.
2. **Macro–calorie consistency** – `expected_cal ≈ 4×protein + 4×carbs + 9×fat` (fiber optional). Large drift → missing fat/carb fields or wrong serving mapping.
3. **Unit/portion reasonableness** – For volume portions (cups, tbsp) of dense or variable-density foods (meat, cheese, nut butter, legumes), consider whether stated calories and macros are plausible for that volume. If inconsistent with typical cooked/raw or serving size, flag and suggest verifying cooked vs raw or weighing in grams.

### D) If units are volume-based, sanity-check weight and macros

For volume portions of dense foods (e.g. meat, cheese, nut butter), reason about whether the stated calories and macros are plausible for that volume (cooked vs raw and packing affect density). If wildly inconsistent, flag and suggest verifying cooked vs raw or weighing in grams.

### E) Produce a structured result

```json
{
  "status": "ok" | "suspicious" | "likely_wrong",
  "why": "Human-readable reason",
  "whatToVerify": ["raw vs cooked", "fat %", "grams", "serving database entry"],
  "confidence": 0.0–1.0,
  "suggestedCorrection": "Optional: weigh beef cooked (grams) or choose 'cooked, crumbled, 80/20' entry; verify raw vs cooked drained."
}
```

---

## Example: Meat / volume portion (principle-based)

When an entry has **volume portions** (e.g. cups) of **meat or other dense foods**, the checker should:

- Assess whether protein per calorie is plausible for that food (meat/poultry/fish are protein-dense; implausibly low protein for the calories suggests raw vs cooked mix-up, wrong USDA serving, or bad unit/portion).
- Assess whether stated calories and macros are plausible for that volume (cooked vs raw and packing affect density).
- If inconsistent: set status to suspicious or likely_wrong, and in `whatToVerify` / `suggestedCorrection` mention: raw vs cooked, unit conversion (cups → grams), database serving definition, or weighing in grams. Do not encode a single numeric example (e.g. one specific kcal/protein pair)—apply the same logic to any implausible combo.

---

## Example: Legumes (raw/cooked confusion)

For **legumes** (e.g. lentils), raw vs cooked changes calories and macros sharply. If the stated calories or macros are inconsistent with typical cooked vs raw for the portion (e.g. numbers that fit raw when user likely meant cooked, or vice versa), flag as suspicious with `whatToVerify` including "raw vs cooked" and optionally suggest verifying serving or weighing.

---

## Key insight

We don't need exact truth — we need to **detect** that macros fail the smell test, suggesting unit/raw-cooked mismatch or bad database mapping. The output drives color-coding and helps the user know what to verify or correct.

---

## Schema change: ingredients collection

Add a new field to the **ingredients** collection (PocketBase):

| Field name | Type | Required | Notes |
|------------|------|----------|-------|
| `plausibilityStatus` | Text | No | `"ok"` \| `"suspicious"` \| `"likely_wrong"` — drives color tag |
| `plausibilityResult` | JSON | No | Full result: `{ why, whatToVerify, confidence, suggestedCorrection }` for tooltip/expand |

Alternative: single JSON field `plausibility` with `{ status, why, whatToVerify, confidence, suggestedCorrection }`.

**When assigned:** At parse time — plausibility check runs in the parse pipeline, and the result is written to the ingredient payload before `insert_ingredient`. Existing ingredients (no field) can show neutral/default until re-parsed or batch-updated.

---

## Design decisions to plan for

1. **When to run** – **At parse time** (per meal, for each ingredient after nutrition is known). Not on demand when loading Day View.
2. **Where in the pipeline** – New plausibility step after nutrition is set (USDA/GPT + scaling), before or after `common_sense_check`. Run before `insert_ingredient` so the field is persisted with the ingredient.
3. **Schema migration** – Add `plausibilityStatus` (and optionally `plausibilityResult`) to PocketBase ingredients collection. Plan for existing records (null = neutral or run batch backfill).
4. **API shape** – No separate endpoint. Plausibility runs inside parse flow; `insert_ingredient` includes the new field(s). `fetchIngredients` / GET ingredients returns them; Day View reads from ingredient objects.
5. **UI integration** – Day View reads `ing.plausibilityStatus` and applies border/background color (green / amber / red). Tooltip from `plausibilityResult.why` / `whatToVerify`.
6. **Regression** – Add plausibility expectations to golden set or regression meals?

---

## Ask

**List your plan first, then implement.** Include:

1. **Parse flow:** Where the plausibility check lives (new module, integration point in `parse_api.py`). Run after nutrition is set, before `insert_ingredient`; include result in payload.
2. **Schema:** New field(s) on ingredients collection (`plausibilityStatus`, `plausibilityResult` or single `plausibility` JSON). Migration / backfill for existing ingredients.
3. **UI:** Color-coding rules in `DayDetail.jsx` (read `ing.plausibilityStatus`), tooltip/expandable "why" from `plausibilityResult`.
4. **Both flows:** Parsing flow changes (run check, persist field) and UI changes (read field, apply color tag).
