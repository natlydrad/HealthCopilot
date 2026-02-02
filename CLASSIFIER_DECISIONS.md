# Log Classifier Decisions & Backlog

## Current Classification Categories

### Food (has nutritional value to track)
- Meals, snacks
- Beverages with calories (coffee, matcha, smoothies)

### Non-Food Categories
- **hydration**: Water intake tracking (start/finish bottles)
- **poop**: Bowel movements
- **mood**: Emotions, feelings, mental state
- **symptom**: Physical symptoms (nausea, pain, tired)
- **supplement**: Vitamins, supplements (vitamin D, fish oil, etc.)
- **medication**: Drugs, medicine (naproxen, ibuprofen, etc.)
- **activity**: Exercise, sleep, events

---

## Decisions Made

### 2026-02-01
- [x] Medications → **non-food** (separate `medication` category)
- [x] Supplements/vitamins → **non-food** (separate `supplement` category)
- [x] "finished matcha/coffee" → **food** (has calories)
- [x] "finished water bottle" → **hydration** (no calories, tracking intake)

---

## Backlog / Return To Later

---

## Schema Changes

### `meals` table (updated)
```
+ isFood: boolean       // Should this go through nutrition parser?
+ categories: JSON      // ["food", "symptom"] - all categories that apply
```

### `non_food_logs` table (new)
```
id, mealId, user, category, content, timestamp, metadata, created, updated
```
- Links back to original meal via `mealId`
- `category`: hydration, poop, mood, symptom, supplement, medication, activity
- `content`: the relevant portion of text for this category
- `metadata`: JSON for category-specific data (future use)

---

## Backlog / Return To Later

### Caffeine Tracking
- **Idea**: Track caffeine intake timing (40mg all at once vs spread out)
- **Why deferred**: Not necessary for MVP
- **When to revisit**: When optimizing for energy/sleep correlation

### Hydration vs Food Edge Cases
- Coffee/tea/matcha: Currently → food (has calories)
- Could split: nutrition goes to food, consumption timing goes to hydration
- **When to revisit**: If user wants to track "drinks consumed" separately from nutrition

### Mixed Entries
- Entries like "ate chicken and felt nauseous" get split
- Need to decide: Store as one record with multiple categories, or split into multiple records?

---

## Category Keywords (for reference)

```
hydration: water, bottle, start, finish, hydrate, oz (when about water)
poop: poop, bowel, bathroom, stool, diarrhea, constipation
mood: feel, felt, happy, sad, anxious, stress, cry, angry, joy
symptom: nausea, headache, pain, tired, fatigue, hurt, ache
medication: mg, naproxen, ibuprofen, tylenol, medicine, drug, prescription
activity: exercise, walk, run, sleep, nap, woke, gym, workout
```
