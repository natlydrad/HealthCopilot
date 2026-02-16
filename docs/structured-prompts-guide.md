# Structured prompts guide

Use this checklist when asking for a feature or fix so the AI has clear context and you get better results.

## Checklist

1. **One-line goal** – What should be done? (e.g. "Add validation so portion cannot be negative.")
2. **@relevant file or doc** – Attach the file(s) or doc that matter (e.g. `@lookup_usda.py`, `@docs/project-overview.md`).
3. **Current vs desired behavior** – What happens now? What should happen instead?
4. **"Step by step" or "list your plan first"** – Ask the AI to reason or show a plan before editing.

## Example

**Vague:** "Fix the tea thing."

**Structured:**

- **Goal:** Fix tea being scored or labeled incorrectly in USDA lookup.
- **Context:** @lookup_usda.py @regression/README.md
- **Current:** Oolong is sometimes classified as non-caffeinated or matched to the wrong food.
- **Desired:** Tea ingredients get correct caffeine and USDA match; regression cases for tea pass.
- **Ask:** "List your plan first, then implement."

## If you don't have time to structure it

The AI is instructed to treat vague requests by **proposing** a structured plan (goal, needed context, steps) and asking you to **confirm or correct** before making any edits. You can then approve or refine that plan.
