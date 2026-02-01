# Web App Corrections Guide

## Overview

The correction UI is now available in the web dashboard. You can correct any ingredient from any meal, and corrections will be tracked for the learning system.

---

## How to Use Corrections

### Step 1: View Meals
- Open the web dashboard
- Navigate to any day's meals
- Each meal card shows ingredients

### Step 2: Correct an Ingredient
1. **Hover over an ingredient** - you'll see a ✏️ edit button appear
2. **Click the edit button** - correction modal opens
3. **Edit the values**:
   - Ingredient name
   - Quantity
   - Unit (oz, cup, tbsp, etc.)
   - Category (food, drink, supplement, other)
4. **Click "Save Correction"**

### Step 3: What Happens
- ✅ Correction is saved to `ingredient_corrections` table
- ✅ Ingredient is updated with your corrected values
- ✅ Dashboard refreshes to show updated values
- ✅ Original parse is preserved for learning

---

## Features

### ✅ Edit Any Ingredient
- Click the ✏️ button on any ingredient
- Works for all meals (current and past)

### ✅ See All Ingredients
- Click "▶ Nutrients" to expand and see all ingredients
- Click "Show less" to collapse

### ✅ Original Values Preserved
- Original parse is stored in `originalParse` field
- Enables learning system to calculate multipliers

### ✅ Automatic Refresh
- Dashboard refreshes after each correction
- See changes immediately

---

## Correction Types Tracked

The system automatically categorizes corrections:

- **quantity_change**: Changed quantity (e.g., 4oz → 6oz)
- **name_change**: Changed ingredient name (e.g., "lettuce" → "arugula")
- **unit_change**: Changed unit (e.g., "cup" → "oz")
- **complete_replace**: Changed name + quantity

---

## Test Week Setup

### Starting Fresh
- This week is your test week
- Correct ingredients as you see them
- Old entries can be corrected later (they're still accessible)

### What to Correct
- **Portion sizes**: If GPT estimated wrong
- **Ingredient names**: If it misidentified something
- **Missing ingredients**: Add them manually (future feature)
- **Wrong units**: Fix unit conversions

---

## Data Flow

```
1. User sees ingredient: "chicken 4oz"
2. User clicks ✏️ and corrects to "chicken 6oz"
3. System creates correction record:
   - originalParse: {quantity: 4, unit: "oz"}
   - userCorrection: {quantity: 6, unit: "oz"}
   - multiplier: 1.5
   - correctionType: "quantity_change"
4. System updates ingredient: quantity = 6
5. Dashboard refreshes
```

---

## API Endpoints Used

- `POST /api/collections/ingredient_corrections/records` - Create correction
- `PATCH /api/collections/ingredients/records/{id}` - Update ingredient

---

## Troubleshooting

### Edit button not showing?
- Make sure you're hovering over the ingredient
- Check browser console for errors

### Correction not saving?
- Check that you're logged in
- Verify PocketBase migrations ran successfully
- Check browser console for API errors

### Dashboard not refreshing?
- Try refreshing the page manually
- Check network tab for API calls

---

## Next Steps (Tier 2)

Once you've collected corrections:
1. System will learn your portion multipliers
2. Future parses will use learned values
3. Accuracy will improve automatically

---

## Example Workflow

**Monday**: Log "chicken salad"
- GPT parses: chicken 4oz, lettuce 1 cup
- You correct: chicken 6oz, arugula 1 cup
- ✅ Corrections saved

**Tuesday**: Log "chicken salad" again
- GPT parses: chicken 4oz (still wrong)
- You correct: chicken 6oz again
- ✅ Another correction saved

**Tier 2**: System learns
- Average multiplier: 6/4 = 1.5x for chicken
- Next "chicken salad": Auto-estimates 6oz
- ✅ No correction needed!

---

## Notes

- Corrections work retroactively - you can correct old meals anytime
- Original parse is always preserved
- Each correction helps the learning system
- More corrections = better personalization

Happy correcting! 🎯
