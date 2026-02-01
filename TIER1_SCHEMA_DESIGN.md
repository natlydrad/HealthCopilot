# Tier 1 Schema Design: User Preferences & Corrections

## Overview

This document defines the database schema for Tier 1 personalization features. The design prioritizes:
- **Flexibility**: Schema can grow without breaking changes
- **Data integrity**: Original data preserved for learning
- **Future-proofing**: Ready for Tier 2-4 enhancements

---

## Collection 1: `user_preferences`

**Purpose**: Store user preferences, brands, portion sizes, and dietary restrictions.

### Schema

```javascript
{
  id: "text (15 chars, auto)",
  user: "relation → users (required, unique)",
  preferences: {
    // Flexible JSON structure - can grow without migrations
    brands: ["Chipotle", "Starbucks", "Whole Foods"],
    portionMultipliers: {
      // Per-ingredient multipliers learned over time
      "chicken": 1.5,  // User eats 1.5x GPT's estimate
      "rice": 0.8,
      "vegetables": 1.2
    },
    preferredUnits: {
      "meat": "oz",
      "grains": "cup",
      "vegetables": "cup"
    },
    dietaryRestrictions: ["vegetarian", "gluten-free"],
    commonMeals: ["oatmeal", "chicken salad", "burrito bowl"],
    // Future: mealTemplates, brandPreferences, etc.
  },
  metadata: {
    // Future-proofing: store any additional data
    onboardingCompleted: true,
    lastCalibrationDate: "2026-02-01",
    version: 1  // Schema version for migrations
  },
  created: "autodate",
  updated: "autodate"
}
```

### Key Design Decisions

1. **JSON `preferences` field**: Flexible structure that can evolve without migrations
2. **Unique user constraint**: One preference record per user
3. **`metadata` field**: Future-proofing for schema versioning and additional data
4. **Cascade delete**: If user is deleted, preferences are deleted

### Example Data

```json
{
  "id": "abc123def456ghi",
  "user": "user789",
  "preferences": {
    "brands": ["Chipotle", "Starbucks"],
    "portionMultipliers": {
      "chicken": 1.5,
      "rice": 0.8
    },
    "preferredUnits": {
      "meat": "oz",
      "grains": "cup"
    },
    "dietaryRestrictions": ["vegetarian"],
    "commonMeals": ["oatmeal", "chicken salad"]
  },
  "metadata": {
    "onboardingCompleted": true,
    "version": 1
  }
}
```

---

## Collection 2: `ingredient_corrections`

**Purpose**: Track user corrections to parsed ingredients. Critical for Tier 2 learning system.

### Schema

```javascript
{
  id: "text (15 chars, auto)",
  ingredientId: "relation → ingredients (required)",
  user: "relation → users (required)",
  originalParse: {
    // Complete snapshot of original parse (from any source)
    name: "chicken",
    quantity: 4,
    unit: "oz",
    category: "food",
    source: "gpt",  // "gpt", "template", "brand_db", "history", "cached", "manual"
    parsingStrategy: "gpt",  // Which parsing method was used
    confidence: 0.75,  // Confidence score (0.0-1.0)
    rawGPT: {...},  // Full GPT response (if from GPT)
    templateId: null,  // If from template
    brandFoodId: null,  // If from brand DB
    nutrition: [...],  // USDA nutrition data
    macros: {...}
  },
  userCorrection: {
    // What user actually corrected it to
    name: "chicken",
    quantity: 6,  // User corrected from 4oz to 6oz
    unit: "oz",
    category: "food",
    // User may have changed name, quantity, unit, or all
  },
  multiplier: 1.5,  // Calculated: 6 / 4 = 1.5
  correctionType: "quantity_change",  // "quantity_change", "name_change", "unit_change", "add", "remove"
  created: "autodate",
  updated: "autodate"
}
```

### Key Design Decisions

1. **Store original parse**: Critical for learning - can't calculate multipliers without original
2. **Store user correction**: What user actually wants
3. **Calculate multiplier**: Pre-computed for fast queries in Tier 2
4. **Correction type**: Categorize corrections for better learning
5. **Indexes**: Fast lookups by ingredient, user, and type

### Correction Types

- `quantity_change`: User changed quantity (e.g., 4oz → 6oz)
- `name_change`: User changed ingredient name (e.g., "lettuce" → "arugula")
- `unit_change`: User changed unit (e.g., "cup" → "oz")
- `add`: User added new ingredient
- `remove`: User removed ingredient
- `complete_replace`: User replaced entire ingredient

### Example Data

```json
{
  "id": "corr123def456",
  "ingredientId": "ing789abc",
  "user": "user789",
  "originalParse": {
    "name": "chicken",
    "quantity": 4,
    "unit": "oz",
    "category": "food",
    "source": "gpt",
    "macros": {
      "calories": 180,
      "protein": 35,
      "carbs": 0,
      "fat": 4
    }
  },
  "userCorrection": {
    "name": "chicken",
    "quantity": 6,
    "unit": "oz",
    "category": "food"
  },
  "multiplier": 1.5,
  "correctionType": "quantity_change"
}
```

---

## Data Flow: How Corrections Work

### Step 1: User Logs Meal
```
User logs: "chicken salad" (text) or uploads photo
↓
GPT Vision parses → creates ingredients
↓
Ingredients stored in `ingredients` table
```

### Step 2: User Corrects Ingredient
```
User sees parsed ingredient: "chicken 4oz"
User corrects to: "chicken 6oz"
↓
Create `ingredient_corrections` record:
- originalParse: {quantity: 4, unit: "oz"}
- userCorrection: {quantity: 6, unit: "oz"}
- multiplier: 1.5
↓
Update `ingredients` table with corrected values
```

### Step 3: Tier 2 Learning (Future)
```
System analyzes all corrections for user
↓
Calculates average multipliers per ingredient
↓
Updates `user_preferences.portionMultipliers`
↓
Future parses use multipliers automatically
```

---

## API Endpoints (Tier 1)

### User Preferences

```
GET /api/collections/user_preferences/records
  → Returns user's preferences (filtered by auth)

POST /api/collections/user_preferences/records
  → Create/update user preferences
  Body: {
    "preferences": {
      "brands": [...],
      "portionMultipliers": {...},
      ...
    }
  }

PATCH /api/collections/user_preferences/records/{id}
  → Update preferences
```

### Ingredient Corrections

```
POST /api/collections/ingredient_corrections/records
  → Create correction
  Body: {
    "ingredientId": "ing123",
    "originalParse": {...},
    "userCorrection": {...},
    "correctionType": "quantity_change"
  }

GET /api/collections/ingredient_corrections/records
  → Get user's corrections (for learning system)
  Query params: ?filter=(user='{userId}')&expand=ingredientId
```

---

## Migration Strategy

### Phase 1: Create Collections
- Run migration `1759800000_created_user_preferences.js`
- Run migration `1759800001_created_ingredient_corrections.js`

### Phase 2: Backfill (Optional)
- For existing users: Create default `user_preferences` records
- For existing corrections: If you have any manual corrections, migrate them

### Phase 3: Update Application Code
- Update parser to load user preferences
- Add correction UI
- Update GPT prompts with preferences

---

## Hybrid Vision Structure Support

### Parsing Strategy Tracking

The schema now supports the hybrid parsing approach (Tier 4):

**Ingredients table** (via migration `1759800002_updated_ingredients_hybrid.js`):
- `parsingStrategy`: Tracks which method was used
  - `template`: From meal template (Tier 3)
  - `brand_db`: From brand database (Tier 2)
  - `history`: From similar past meal (Tier 3)
  - `gpt`: From GPT Vision (current)
  - `manual`: User entered directly
  - `cached`: From parsing cache (Tier 4)
- `confidence`: 0.0-1.0 score (Tier 4)
- `templateId`: Link to meal template if used
- `brandFoodId`: Link to brand food if used
- `parsingMetadata`: Flexible JSON for parsing details

**Corrections table**:
- `originalParse.source` now tracks parsing strategy
- Enables learning which strategies are most accurate

### Parsing Pipeline (Tier 4)

```
1. Check meal templates → parsingStrategy: "template", confidence: 0.95
2. Check brand database → parsingStrategy: "brand_db", confidence: 0.90
3. Check user history → parsingStrategy: "history", confidence: 0.75
4. Check parsing cache → parsingStrategy: "cached", confidence: 0.80
5. GPT Vision → parsingStrategy: "gpt", confidence: 0.60-0.85
6. User confirmation → always available
```

---

## Future Enhancements (Tier 2-4)

### Tier 2: Learning System ✅ (Collections Created)
- ✅ `brand_foods` collection (brand-specific nutrition) - Migration `1759800003`
- ✅ `parsing_accuracy` tracking via corrections
- Enhance `user_preferences` with learned multipliers

### Tier 3: Context Awareness ✅ (Collections Created)
- ✅ `meal_templates` collection (user's recurring meals) - Migration `1759800004`
- Pattern recognition via corrections + templates
- Enhance corrections with context (time of day, location)

### Tier 4: Optimization ✅ (Collections Created)
- ✅ `parsing_cache` collection (cache GPT responses) - Migration `1759800005`
- ✅ Confidence scoring in ingredients table
- ✅ Cost tracking in parsing_cache
- Hybrid parsing strategy support

---

## Validation Rules

### User Preferences
- `user` must be unique (one preference record per user)
- `preferences` JSON must be valid
- `preferences.brands` should be array of strings
- `preferences.portionMultipliers` should be object with numeric values

### Ingredient Corrections
- `ingredientId` must exist in `ingredients` table
- `originalParse` must contain at least `name`, `quantity`, `unit`
- `userCorrection` must contain at least `name`, `quantity`, `unit`
- `multiplier` should be calculated: `userCorrection.quantity / originalParse.quantity`
- `correctionType` must be one of valid types

---

## Testing Checklist

- [ ] Create user preferences
- [ ] Update user preferences
- [ ] Create ingredient correction
- [ ] Verify multiplier calculation
- [ ] Query corrections by user
- [ ] Query corrections by ingredient
- [ ] Verify cascade delete (user → preferences)
- [ ] Verify cascade delete (user → corrections)
- [ ] Test with missing data (graceful handling)

---

## Notes

1. **Flexibility First**: JSON fields allow schema evolution without migrations
2. **Data Preservation**: Always store original parse (critical for learning)
3. **Performance**: Indexes on frequently queried fields
4. **Security**: All collections use user-based access rules
5. **Future-Proof**: `metadata` field allows schema versioning

This schema design supports Tier 1 requirements while being ready for Tier 2-4 enhancements.
