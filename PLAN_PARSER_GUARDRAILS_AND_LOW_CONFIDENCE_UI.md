# Plan: Parser Guard Rails & Low-Confidence UI

Reduce correction fatigue by (1) improving parser output quality and (2) making low-confidence ingredients more obvious and easier to fix.

---

## Phase 1: Parser Guard Rails

**Goal:** Avoid obviously vague parses before users ever see them.

### 1.1 Add "avoid vague terms" to parser prompts

**Files:** `ml-pipeline/nutrition-pipeline/parser_gpt.py`

- **Image parser** (`parse_ingredients_from_image`): Add explicit rule to prompt:
  - "Avoid vague composite terms like 'pizza toppings', 'salad stuff', 'sandwich fillings', 'leftover food'. Prefer specific items: 'pepperoni pizza slice', '2 slices cheese pizza', 'lettuce, tomato, dressing', 'turkey sandwich'."
  - Extend the existing "List actual ingredients" guidance with examples of bad vs good.
- **Text parser** (`parse_ingredients`): Same guidance for text-only inputs.

### 1.2 Post-parse validation (optional, later)

- After GPT returns parsed items, run a pass that flags or rejects known vague terms.
- Could prompt for re-parse with "Be more specific" or auto-expand to common alternatives.
- Lower priority; prompt improvements may be enough.

---

## Phase 2: Low-Confidence UI (priority)

**Goal:** Make it obvious which ingredients need review and reduce friction to fix them.

### 2.1 Stronger visual treatment for low-confidence ingredients

**Current state:** `isLowConfidence(ing)` → amber background, `?` icon, "tap to edit".

**Improvements:**

| Element | Current | Proposed |
|--------|---------|----------|
| Background | `bg-amber-50` | `bg-amber-50` + subtle left border (e.g. 3px amber) |
| Icon | Small `?` | More visible badge: "Review" or "Check" with amber styling |
| Copy | "tap to edit" | "Needs review — tap to fix" (only for low-conf) |
| Meal-level | — | Optional: badge on meal card if *any* ingredient is low-conf, e.g. "1 needs review" |

**Files:** `web-dashboard/dashboard/src/DayDetail.jsx`

### 2.2 Expand low-confidence logic

**Current:** Low confidence = no USDA code, or GPT source without nutrition.

**Add:**

- **Vague name heuristic:** If ingredient name matches known vague patterns (e.g. "pizza toppings", "salad", "leftover", "toppings", "stuff"), treat as low-confidence even if USDA matched. (We could add a small list in the frontend or return a flag from the backend.)
- **Parser metadata:** If the parser ever returns a `confidence` or `isVague` flag, use it.

**Files:** `DayDetail.jsx` (`isLowConfidence`), optionally `api.js` or a small util.

### 2.3 Quick actions for low-confidence ingredients

When user taps a low-confidence ingredient, show a **shortcut bar** before or alongside the chat:

| Action | Behavior |
|--------|----------|
| **✏️ Re-describe** | Opens minimal flow: "Describe this in your own words" → re-parse (existing flow) |
| **👎 Wrong** | One-tap to open correction chat with pre-filled "This is wrong" or "Be more specific" — or skip straight to re-describe |
| **✓ Looks good** | Optional: dismiss "needs review" for this session (no persistence; just UX) |

**Implementation:**

- Add a row of buttons in the correction modal header (or above the chat) when the ingredient is low-confidence.
- "Re-describe" can reuse the existing Re-describe & re-parse flow.
- "Wrong" could either (a) send "This is wrong, please be more specific" as the first user message, or (b) focus the input with placeholder "What was it really?"

**Files:** `DayDetail.jsx` (CorrectionModal / correction chat UI)

### 2.4 Meal-level summary

- If a meal has ≥1 low-confidence ingredient, show a compact badge: e.g. "2 need review" next to the ingredient count.
- Clicking the badge could scroll to the first low-confidence ingredient or expand the list.

**Files:** `DayDetail.jsx` (MealCard or ingredient list header)

---

## Phase 3: Quick Alternatives (optional)

**Goal:** For common mis-parses (e.g. pizza), offer one-tap alternatives.

### 3.1 Context-aware quick picks

- When ingredient is low-confidence AND name matches a category (e.g. "pizza", "pizza toppings", "salad"), show 2–4 quick alternatives: "Pepperoni pizza", "Cheese pizza", "Veggie pizza", "Other…"
- Tapping an alternative could trigger a correction with that name (similar to USDA options flow).
- Requires mapping categories → alternatives (small config or heuristic).

**Scope:** Nice-to-have; adds complexity. Consider after Phases 1–2.

---

## Implementation Order

| # | Task | Effort | Impact |
|---|------|--------|--------|
| 1 | Parser prompt: avoid vague terms (image + text) | Small | High |
| 2 | Stronger low-confidence visuals (border, badge, copy) | Small | High |
| 3 | Vague-name heuristic in `isLowConfidence` | Small | Medium |
| 4 | Quick actions in correction modal (Re-describe, Wrong) | Medium | High |
| 5 | Meal-level "X need review" badge | Small | Medium |
| 6 | Quick alternatives for pizza/salad etc. | Medium | Medium (later) |

---

## Success Criteria

- Fewer vague parses (e.g. "pizza toppings") from the parser.
- Low-confidence ingredients are immediately visible.
- Users can fix low-confidence items with fewer steps (quick actions, clearer CTAs).
