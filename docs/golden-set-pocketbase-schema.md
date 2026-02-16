# Golden set PocketBase schema

Create these in PocketBase admin so the Parse API can store the golden set in PocketBase.

## Collection: `golden_entries`

Create a new collection with **API name** `golden_entries`.

| Field name | Type   | Required | Notes |
|------------|--------|----------|--------|
| mealId     | Text   | No       | PocketBase meal record id; unique per meal for dedupe. |
| text       | Text   | Yes      | Meal input text at time of add. |
| expected   | JSON   | Yes      | `{ "ingredients": [ ... ], "acceptableRanges": optional }`. Each ingredient can include `nutrition` (array of `{ nutrientName, unitName, value }`). |
| category   | Text   | No       | `easy`, `normal`, or `evil`. Default `normal`. |
| addedAt    | Date   | No       | When the entry was added (ISO datetime). |

- **Nutrient comparison:** `expected.ingredients[].nutrition` is the reference for calories, protein, carbs, fat, fiber, sugar, sodium, caffeine (Caffeine, MG). When running golden regression, actual parsed output is compared to these values; pass = actual within tolerance of golden for each stored nutrient.
- **Tolerance:** `expected.acceptableRanges` may include `nutrientTolerancePercent` (default 20) for all nutrients, and optional `caloriesTolerancePercent` to override for calories only. Actual must be within ±that % of expected (with a minimum absolute tolerance for small values).
- Record **id** is auto-generated; it is used as the stable `id` in run-golden results.
- In PocketBase you may need to allow empty string or null for optional text fields; for `expected` use JSON type.

## Meals collection: new field

Add one optional field to the existing **meals** collection:

| Field name   | Type    | Required | Notes |
|--------------|---------|----------|--------|
| inGoldenSet  | Bool    | No       | Set to true when this meal is added to the golden set. |

Alternatively you can use **markedCorrectAt** (Date) instead of inGoldenSet; the code will use whichever field name you add (see pb_client and parse_api).

## Code reference

- **pb_client.py**: `fetch_golden_entries()`, `create_or_update_golden_entry()`, `delete_all_golden_entries()`, `set_meal_in_golden_set()`.
- **parse_api.py**: GET `/regression/golden-set`, POST `/regression/golden-add`, POST `/regression/golden-add-bulk`, POST `/regression/golden-clear`.
