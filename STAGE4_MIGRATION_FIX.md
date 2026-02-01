# Stage 4 (Tier 4) Migration Fix & Next Steps

## What Happened

You were working on **Stage 4 (Tier 4)** from the MVP Tier Plan, which implements the **Hybrid Parsing Strategy**. This involves:

1. **Hybrid Parsing Pipeline**: Rule-based first (templates, brand DB, history), GPT Vision only for novel meals
2. **Confidence Scoring**: Assign confidence scores to each parse
3. **Cost Optimization**: Cache GPT responses, use cheaper models when possible
4. **Continuous Learning**: Weekly retraining, A/B testing

## Why Migrations Broke

The migrations failed because of **incorrect API usage** in PocketBase migrations:

### Problem 1: `getById()` throws errors
- **Migration 1759800006** (`added_ingredient_relations.js`) used `collection.fields.getById("relation_template")` 
- **Migration 1759800007** (`added_mealId_relation.js`) used `collection.fields.getById("relation4249466421")`
- **Issue**: `getById()` throws an error if the field doesn't exist, breaking the migration

### Problem 2: Inconsistent parameter naming
- **Migration 1759800002** used `app` instead of `txApp` (though this might work, it's inconsistent)

## What Was Fixed

✅ **Fixed Migration 1759800006**: Changed from `getById()` to `getAll()` + `some()` check
✅ **Fixed Migration 1759800007**: Changed from `getById()` to `getAll()` + `some()` check  
✅ **Fixed Migration 1759800002**: Changed `app` to `txApp` for consistency

All migrations now use the safe pattern:
```javascript
const existingFields = collection.fields.getAll();
const hasField = existingFields.some(f => f.id === "field_id" || f.name === "fieldName");
if (!hasField) {
  // Add field
}
```

## Next Steps

### 1. Run Migrations ✅
The migrations should now work correctly. Run them:

```bash
cd backend
./pocketbase migrate
```

Or if using PocketBase admin UI:
1. Go to Settings → Migrations
2. Verify all migrations are listed
3. Run any pending migrations

### 2. Verify Schema ✅
After migrations run, verify the `ingredients` collection has these new fields:
- ✅ `parsingStrategy` (select: template, brand_db, history, gpt, manual, cached)
- ✅ `confidence` (number: 0.0-1.0)
- ✅ `parsingMetadata` (json)
- ✅ `templateId` (relation to meal_templates)
- ✅ `brandFoodId` (relation to brand_foods)
- ✅ `mealId` (relation to meals)

### 3. Implement Tier 4 Features

#### 3.1 Hybrid Parsing Pipeline
Update your parser to follow this flow:

```
1. Check meal templates → parsingStrategy: "template", confidence: 0.95
2. Check brand database → parsingStrategy: "brand_db", confidence: 0.90
3. Check user history → parsingStrategy: "history", confidence: 0.75
4. Check parsing cache → parsingStrategy: "cached", confidence: 0.80
5. GPT Vision → parsingStrategy: "gpt", confidence: 0.60-0.85
6. User confirmation → always available
```

**Files to update:**
- `ml-pipeline/nutrition-pipeline/parser_gpt.py` - Add hybrid parsing logic
- `ml-pipeline/nutrition-pipeline/enrich_meals.py` - Update to use new fields

#### 3.2 Confidence Scoring
Assign confidence scores based on parsing strategy:
- Template match: 0.95
- Brand DB match: 0.90
- History match: 0.75
- Cached parse: 0.80
- GPT parse (with context): 0.70-0.85
- GPT parse (novel): 0.60-0.70

#### 3.3 Cost Optimization
- **Cache GPT responses**: Store in `parsing_cache` collection
- **Use cheaper models**: Use `gpt-4o-mini` for simple parses
- **Batch processing**: Process low-priority meals in batches

#### 3.4 Update Application Code
- **Frontend**: Update dashboard to show confidence scores
- **Backend**: Update API to return parsing strategy and confidence
- **ML Pipeline**: Implement hybrid parsing logic

### 4. Testing Checklist

- [ ] Migrations run successfully
- [ ] All new fields exist in `ingredients` collection
- [ ] Relations work (templateId, brandFoodId, mealId)
- [ ] Parser uses hybrid strategy
- [ ] Confidence scores are assigned correctly
- [ ] Caching works (parsing_cache collection)
- [ ] Frontend displays confidence scores
- [ ] API returns parsing strategy metadata

## Migration Order (for reference)

The migrations run in this order:
1. `1759799999_created_ingredients.js` - Creates ingredients collection
2. `1759800000_created_user_preferences.js` - Tier 1: User preferences
3. `1759800001_created_ingredient_corrections.js` - Tier 1: Corrections
4. `1759800002_updated_ingredients_hybrid.js` - Tier 4: Hybrid fields (parsingStrategy, confidence, parsingMetadata)
5. `1759800003_created_brand_foods.js` - Tier 2: Brand foods collection
6. `1759800004_created_meal_templates.js` - Tier 3: Meal templates collection
7. `1759800005_created_parsing_cache.js` - Tier 4: Parsing cache
8. `1759800006_added_ingredient_relations.js` - Tier 2-3: Relations (templateId, brandFoodId)
9. `1759800007_added_mealId_relation.js` - Links ingredients to meals

## Success Criteria (Tier 4)

From MVP_TIER_PLAN.md:
- ✅ 70% of meals parsed without GPT (templates/brand DB)
- ✅ GPT API costs reduced by 50%
- ✅ Parsing accuracy maintained at 85%+

## Notes

- The migrations are now **idempotent** - they can be run multiple times safely
- All field checks use `getAll()` + `some()` instead of `getById()` to avoid errors
- The schema supports all Tier 1-4 features as designed
