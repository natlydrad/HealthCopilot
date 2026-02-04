# Framework Categorization Logic – Review & Flaw Analysis

**Status:** Fixes implemented. See commits.

## How It Works

There are **two code paths**:

1. **Keyword path** (no `foodGroupServings`): Ingredient name is matched against keyword lists; servings are calculated from quantity/unit.
2. **GPT path** (`foodGroupServings` present): GPT provides a single object `{ grains, vegetables, fruits, protein, dairy }`. We then **map** those numbers into Daily Dozen and Longevity categories.

---

## Flaw 1: Beef, Sardines → Beans

**Cause:** On the GPT path (lines 66–67), **all** `fg.protein` is mapped to:
- `dd.beans = fg.protein`
- `lg.legumes = fg.protein * 0.3`

`foodGroupServings` has one “protein” field and does not distinguish animal vs plant protein. So beef, sardines, chicken, etc. are all counted as beans/legumes.

**Fix:** Use the ingredient name to decide where protein goes. Animal protein (beef, sardines, chicken, fish, etc.) should not go to beans/legumes. Only beans, tofu, tempeh, soy, etc. should increase `dd.beans` and `lg.legumes`.

---

## Flaw 2: Soy Milk → Dairy

**Cause:** `DAIRY` includes `'milk'`. “Soy milk” matches `name.includes('milk')`, so it’s classified as dairy.

**Fix:** Treat plant milks as legumes (or their primary source), not dairy. Add exclusions: `soy milk`, `almond milk`, `oat milk`, `coconut milk` → should be legumes/grains/etc., not dairy. Add `'soy'` to BEANS and ensure BEANS is checked before DAIRY (it already is).

---

## Flaw 3: Focaccia → Whole Grains

**Cause:** `WHOLE_GRAINS` includes `'focaccia'`. Most focaccia is made with refined white flour.

**Fix:** Remove focaccia from WHOLE_GRAINS. Be more conservative: only count as whole grain if the name implies whole grain (e.g. whole wheat, quinoa, brown rice, oats) or the product is typically whole (oatmeal, bulgur, etc.). Refined bread products (focaccia, white bread, bagel, white pasta, white rice) should go to “Grains” (refined), not “Whole grains”.

---

## Flaw 4: Spinach Split 50/50 Greens / Other Veg

**Cause:** On the GPT path (lines 66–67):
```js
dd.greens = (fg.vegetables) * 0.5;
dd.otherVeg = (fg.vegetables) * 0.5;
```
All vegetables are split 50/50 between greens and otherVeg, regardless of the actual ingredient.

**Fix:** Use the ingredient name to decide how to allocate `fg.vegetables`. Spinach, kale, lettuce → 100% greens. Broccoli, cabbage → 100% cruciferous. Carrots, tomatoes → 100% otherVeg. Only use a split for genuinely mixed items (e.g. “mixed vegetables”).

---

## Flaw 5: Blueberries Split 30% Berries / 70% Other Fruits

**Cause:** On the GPT path (lines 67):
```js
dd.berries = (fg.fruits) * 0.3;
dd.otherFruits = (fg.fruits) * 0.7;
```
All fruits are split 30% berries / 70% other fruits.

**Fix:** Use the ingredient name. Blueberries, strawberries, raspberries → 100% berries. Apples, oranges, bananas → 100% other fruits.

---

## Summary of Changes Needed

| Issue | Location | Change |
|-------|----------|--------|
| Animal protein → beans | GPT path `fg.protein` mapping | Use name: animal protein → no beans/legumes |
| Soy milk → dairy | DAIRY list + order | Add `soy` to BEANS; optionally exclude plant milks from DAIRY |
| Focaccia → whole grains | WHOLE_GRAINS list | Remove focaccia, bread, bagel, pita, tortilla, pizza, crust, white rice, pasta, etc. – keep only true whole grains |
| Spinach 50/50 split | GPT path `fg.vegetables` mapping | Use name: allocate to greens vs cruciferous vs otherVeg |
| Blueberries 30/70 split | GPT path `fg.fruits` mapping | Use name: allocate to berries vs otherFruits |

**Main principle:** When we have `foodGroupServings`, we should still use the ingredient name to decide how to allocate servings across Daily Dozen and Longevity subcategories, instead of applying fixed splits.
