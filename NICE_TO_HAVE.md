# Nice to Have

Backlog of non-critical features and improvements.

---

## Leftover meal auto-identification

**Feature:** When the parser identifies something as "leftover meal", "leftover food", "plate of leftovers", etc., have it infer what the original meal was instead of leaving it generic.

**How it could work:**
- At parse time, if GPT returns a vague "leftover food" / "leftover meal" type ingredient, check recent meals for that day (or yesterday).
- Copy ingredients from the most likely match (e.g. the most recent meal with similar visual/context cues, or the meal the user logged immediately before).
- Optionally ask the user to confirm: "Is this the same as your earlier [egg noodles] meal?"

**Why it's nice-to-have:** Manual correction ("same as egg noodles meal, 50%") works today. This would reduce friction by guessing correctly upfront.

---

## "Scale entire meal" when correcting to "50% of earlier meal"

**Feature:** When the user says "same as the egg noodles meal but 50%", they often mean scale the *whole* meal (egg noodles AND bacon, etc.), not just the one "leftover food" placeholder ingredient.

**Current behavior:** Correction chat only updates the single ingredient you're correcting. If the meal has leftover food + bacon, correcting "leftover food" → egg noodles 50% leaves bacon unchanged.

**Desired:** When user says "50% of [meal name]", optionally scale all ingredients in the current meal to match 50% of the referenced meal — or offer "Apply 50% to all ingredients in this meal?"

**Why it's nice-to-have:** User can correct bacon separately today. Reduces clicks when the whole plate is a half-portion.

---
