# Plan: Multi-Ingredient Add / Delete / Edit

Based on the sardine pizza meal context and correction flow.

---

## The Sardine Pizza Problem

**What happened:**
- Meal parsed as: `pizza crust` + `pizza toppings`
- User said: "it's marinara sauce and sardines"
- Correction chat lumped them into **one** ingredient: `marinara sauce and sardines`
- USDA matched "WILD SARDINES IN MARINARA SAUCE" — one combined item

**What the user wanted:**
- Either: `pizza crust` + `marinara sauce` + `sardines` (3 separate ingredients)
- Or: split the vague "pizza toppings" into specific items without going through multiple correction cycles

**Current limitations:**
- **Edit**: ✓ Per-ingredient correction chat (exists)
- **Add one**: ✓ Via "missing_item" in correction chat (one new ingredient at a time)
- **Add many**: ✗ No way to add multiple ingredients in one action
- **Delete one**: ✗ Only "Clear" removes all ingredients; no single-ingredient delete

---

## Proposed Features

### 1. Single-Ingredient Delete

**Behavior:** Remove one ingredient from a meal without touching the others.

**Implementation:**
- **API**: `DELETE /ingredients/{id}` — PocketBase supports this. Add `deleteIngredient(ingredientId)` in `api.js` if not present. May need Parse API endpoint if PocketBase rules block user deletes (ingredients may require mealId.user = auth).
- **UI**: Trash icon on each ingredient row. On click → confirm → delete → refresh list.
- **Backend**: Parse API already has `delete_ingredient` in pb_client (service token). Add `DELETE /ingredients/<id>` or `POST /delete-ingredient/<id>` if frontend can't delete directly.

**Where:** `DayDetail.jsx` (ingredient list), `api.js`

---

### 2. Multi-Ingredient Add

**Behavior:** Add several ingredients at once from natural text (e.g. "sardines 1 can, marinara 2 tbsp, olives 5").

**Implementation:**
- **Backend**: New endpoint `POST /add-ingredients/<meal_id>`
  - Body: `{ text: "sardines 1 can, marinara 2 tbsp" }`
  - Uses existing `parse_ingredients(text)` (GPT)
  - For each parsed item: USDA lookup → `insert_ingredient(payload)` (same flow as main parse)
  - Returns `{ ingredients: [...], count: N }`
- **Frontend**: 
  - "Add ingredients" button next to "Clear" (or in the ingredient list header)
  - Modal/section with text input + placeholder: "e.g. sardines 1 can, marinara 2 tbsp, olives 5"
  - On submit → call `addIngredients(mealId, text)` → append new ingredients to list

**Reuses:** `parse_ingredients`, USDA lookup, `insert_ingredient` — all exist in parse_api.

**Where:** `parse_api.py` (new route), `api.js`, `DayDetail.jsx`

---

### 3. Edit (Already Exists)

Correction chat per ingredient — no change needed.

---

## Sardine Pizza Workflow With These Features

**Option A (split combined ingredient):**
1. Delete "marinara sauce and sardines"
2. Add ingredients: "marinara sauce 2 tbsp, sardines 1 can"
3. Result: pizza crust + marinara + sardines (3 items)

**Option B (fix from scratch):**
1. Clear all
2. Add ingredients: "pizza crust 2 slices, marinara sauce 2 tbsp, sardines 1 can"
3. Result: 3 separate ingredients with proper nutrition

---

## Implementation Order

| # | Task | Effort | Dependencies |
|---|------|--------|--------------|
| 1 | Single-ingredient delete (API + UI) | Small | Check PocketBase rules for ingredients |
| 2 | Add-ingredients endpoint (Parse API) | Medium | parse_ingredients, USDA lookup |
| 3 | Add-ingredients UI (button + modal) | Small | #2 |

---

## API Details

### Delete Ingredient
```
DELETE /api/collections/ingredients/records/{id}
```
Or via Parse API (if PB rules block):
```
POST /parse-api/delete-ingredient/{id}
```
Parse API would: delete corrections for ingredient, then delete ingredient (pb_client.delete_ingredient).

### Add Ingredients
```
POST /parse-api/add-ingredients/{meal_id}
Body: { "text": "sardines 1 can, marinara 2 tbsp" }
Response: { "ingredients": [...], "count": 2 }
```

---

## UI Mockup (Add Ingredients)

```
[ Ingredients list ]
  - pizza crust (2 slices)  [Edit] [🗑]
  - marinara sauce and sardines (1.5 oz)  [Edit] [🗑]

[+ Add ingredients]  [🗑 Clear]

--- When "Add ingredients" clicked ---
┌─────────────────────────────────────┐
│ Add ingredients to this meal        │
│                                     │
│ [sardines 1 can, marinara 2 tbsp  ] │
│  e.g. sardines 1 can, olives 5      │
│                                     │
│ [Cancel]  [Add]                     │
└─────────────────────────────────────┘
```
