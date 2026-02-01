# Schema Design: Hybrid Vision Structure Support

## Overview

This document explains how the schema supports the hybrid vision parsing approach and future tiers.

---

## Hybrid Parsing Strategy

### Current Approach (Tier 1)
- **Primary**: GPT Vision for all meals
- **No optimization**: Every meal goes through GPT

### Future Approach (Tier 4)
- **Rule-based first**: Templates → Brand DB → History → Cache
- **GPT Vision second**: Only for novel/unrecognized meals
- **Cost optimization**: Reduce GPT calls by 70%+

---

## Schema Updates for Hybrid Approach

### 1. Ingredients Table Enhancements

**Migration**: `1759800002_updated_ingredients_hybrid.js`

**New Fields**:
```javascript
{
  parsingStrategy: "select",  // template, brand_db, history, gpt, manual, cached
  confidence: "number",       // 0.0-1.0
  templateId: "relation",    // → meal_templates (if from template)
  brandFoodId: "relation",   // → brand_foods (if from brand DB)
  parsingMetadata: "json"    // Flexible: cache key, similarity score, etc.
}
```

**Example Data**:
```json
{
  "name": "chicken",
  "quantity": 6,
  "unit": "oz",
  "parsingStrategy": "template",      // From meal template
  "confidence": 0.95,                 // High confidence
  "templateId": "tmpl123",
  "parsingMetadata": {
    "templateMatch": "exact",
    "lastUsed": "2026-02-01"
  }
}
```

```json
{
  "name": "chicken",
  "quantity": 4,
  "unit": "oz",
  "parsingStrategy": "brand_db",      // From Chipotle brand DB
  "confidence": 0.90,
  "brandFoodId": "chipotle_bowl_123",
  "parsingMetadata": {
    "brand": "Chipotle",
    "item": "Chicken Burrito Bowl"
  }
}
```

```json
{
  "name": "chicken",
  "quantity": 5,
  "unit": "oz",
  "parsingStrategy": "gpt",           // From GPT Vision
  "confidence": 0.65,                  // Lower confidence
  "parsingMetadata": {
    "model": "gpt-4o-mini",
    "costUsd": 0.002,
    "tokens": 150
  }
}
```

---

### 2. Parsing Cache (Tier 4)

**Collection**: `parsing_cache` (Migration `1759800005`)

**Purpose**: Cache GPT responses for similar meals to avoid redundant API calls.

**Schema**:
```javascript
{
  mealHash: "text (SHA-256)",        // Hash of meal text/image
  mealText: "text",                  // Original meal text
  parsedIngredients: "json",         // Cached parse result
  modelUsed: "select",               // gpt-4o-mini, gpt-4-vision, gpt-4o
  costUsd: "number",                 // Cost of original parse
  hitCount: "number",                // How many times cache was used
  created: "autodate",
  updated: "autodate"
}
```

**Usage Flow**:
```
1. User logs meal: "chicken salad"
2. Calculate hash: SHA256("chicken salad") = "abc123..."
3. Check cache: SELECT * FROM parsing_cache WHERE mealHash = "abc123..."
4. If found: Use cached result (no GPT call!)
5. If not found: Call GPT, store in cache
```

**Cost Savings**: 
- First parse: $0.01 (GPT call)
- Subsequent similar meals: $0.00 (cache hit)
- **70%+ reduction in GPT costs**

---

### 3. Brand Foods Database (Tier 2)

**Collection**: `brand_foods` (Migration `1759800003`)

**Purpose**: Store brand-specific nutrition data (Chipotle, Starbucks, etc.)

**Schema**:
```javascript
{
  brand: "text",                      // "Chipotle", "Starbucks"
  item: "text",                      // "Chicken Burrito Bowl"
  ingredients: "json",                // Standardized ingredients
  totalCalories: "number",
  nutrition: "json",
  metadata: "json"
}
```

**Example**:
```json
{
  "brand": "Chipotle",
  "item": "Chicken Burrito Bowl",
  "ingredients": [
    {"name": "chicken", "quantity": 4, "unit": "oz"},
    {"name": "rice", "quantity": 0.5, "unit": "cup"},
    {"name": "black beans", "quantity": 0.5, "unit": "cup"},
    {"name": "cheese", "quantity": 1, "unit": "oz"}
  ],
  "totalCalories": 650
}
```

**Parsing Flow**:
```
1. User logs: "Chipotle bowl"
2. Check brand_foods: SELECT * WHERE brand = "Chipotle" AND item LIKE "%bowl%"
3. If match: Use brand data (parsingStrategy: "brand_db", confidence: 0.90)
4. If no match: Fall back to GPT
```

---

### 4. Meal Templates (Tier 3)

**Collection**: `meal_templates` (Migration `1759800004`)

**Purpose**: Store user's recurring meals for instant parsing

**Schema**:
```javascript
{
  user: "relation → users",
  name: "text",                       // "My Usual Breakfast"
  ingredients: "json",
  frequency: "select",               // daily, weekly, monthly, occasional
  timeOfDay: "text",                  // "morning", "lunch", "dinner"
  usageCount: "number",               // How many times used
  metadata: "json"
}
```

**Example**:
```json
{
  "user": "user123",
  "name": "My Usual Breakfast",
  "ingredients": [
    {"name": "oatmeal", "quantity": 0.5, "unit": "cup"},
    {"name": "banana", "quantity": 1, "unit": "piece"},
    {"name": "almond butter", "quantity": 1, "unit": "tbsp"}
  ],
  "frequency": "daily",
  "timeOfDay": "morning",
  "usageCount": 45
}
```

**Parsing Flow**:
```
1. User logs: "my usual breakfast"
2. Check templates: SELECT * WHERE user = "user123" AND name LIKE "%breakfast%"
3. If match: Use template (parsingStrategy: "template", confidence: 0.95)
4. Increment usageCount
```

---

## Parsing Pipeline (Tier 4)

### Complete Flow

```
User logs meal: "chicken salad"
↓
1. Check meal templates
   → Match found? Use template (confidence: 0.95)
   → No match? Continue
↓
2. Check brand database
   → Match found? Use brand data (confidence: 0.90)
   → No match? Continue
↓
3. Check user history (similar past meals)
   → Similar meal found? Use that (confidence: 0.75)
   → No match? Continue
↓
4. Check parsing cache
   → Cache hit? Use cached result (confidence: 0.80)
   → No match? Continue
↓
5. GPT Vision (only if no matches above)
   → Parse with GPT (confidence: 0.60-0.85)
   → Store in cache for future
↓
6. User confirmation (always available)
   → User can correct any parse
```

### Confidence Thresholds

- **High (0.9+)**: Auto-accept (template, brand DB)
- **Medium (0.6-0.9)**: Show to user, auto-accept if no correction
- **Low (<0.6)**: Require user confirmation

---

## Data Flow: Corrections with Hybrid Approach

### Step 1: Parse Meal (Hybrid Strategy)

```python
def parse_meal_hybrid(meal_text, user_id):
    # Try templates first
    template = find_template(user_id, meal_text)
    if template:
        return {
            "ingredients": template["ingredients"],
            "parsingStrategy": "template",
            "confidence": 0.95,
            "templateId": template["id"]
        }
    
    # Try brand DB
    brand_food = find_brand_food(meal_text)
    if brand_food:
        return {
            "ingredients": brand_food["ingredients"],
            "parsingStrategy": "brand_db",
            "confidence": 0.90,
            "brandFoodId": brand_food["id"]
        }
    
    # Try cache
    cache_key = hash_meal(meal_text)
    cached = get_cache(cache_key)
    if cached:
        return {
            "ingredients": cached["parsedIngredients"],
            "parsingStrategy": "cached",
            "confidence": 0.80
        }
    
    # Fall back to GPT
    gpt_result = parse_with_gpt(meal_text)
    store_in_cache(cache_key, gpt_result)
    return {
        "ingredients": gpt_result,
        "parsingStrategy": "gpt",
        "confidence": 0.65
    }
```

### Step 2: User Corrects

```python
# User corrects ingredient
correction = {
    "ingredientId": "ing123",
    "originalParse": {
        "name": "chicken",
        "quantity": 4,
        "unit": "oz",
        "parsingStrategy": "template",  # Track which strategy failed
        "confidence": 0.95,
        "templateId": "tmpl123"
    },
    "userCorrection": {
        "name": "chicken",
        "quantity": 6,
        "unit": "oz"
    }
}

# Store correction
create_correction(correction)

# Learning: Template was wrong, update template
if correction["originalParse"]["parsingStrategy"] == "template":
    update_template(correction["originalParse"]["templateId"], correction["userCorrection"])
```

---

## Cost Tracking

### Parsing Cache Tracks Costs

```python
# When GPT is called
gpt_result = parse_with_gpt(meal_text)
cost = calculate_cost(tokens_used, model)

# Store in cache
store_in_cache({
    "mealHash": hash_meal(meal_text),
    "parsedIngredients": gpt_result,
    "modelUsed": "gpt-4o-mini",
    "costUsd": cost,
    "hitCount": 0
})

# When cache is hit
cached = get_cache(cache_key)
cached["hitCount"] += 1
# Cost saved: cached["costUsd"] (no new GPT call!)
```

### Cost Metrics

- **Total GPT costs**: Sum of `costUsd` in `parsing_cache`
- **Costs saved**: `hitCount * costUsd` (if cache wasn't used)
- **Cost per user**: Track via user's meals → ingredients → parsingStrategy

---

## Migration Strategy

### Phase 1: Tier 1 (Current)
- ✅ Create `user_preferences`
- ✅ Create `ingredient_corrections`
- ✅ Update `ingredients` with hybrid fields (backward compatible)

### Phase 2: Tier 2
- ✅ Create `brand_foods` (can populate gradually)
- Use brand DB when available

### Phase 3: Tier 3
- ✅ Create `meal_templates`
- Build templates from user corrections

### Phase 4: Tier 4
- ✅ Create `parsing_cache`
- Implement hybrid parsing pipeline
- Track costs and optimize

---

## Backward Compatibility

### Existing Ingredients

All new fields are **optional**:
- `parsingStrategy`: Defaults to `null` (can infer from `source` field)
- `confidence`: Defaults to `null` (assume 0.5 for old data)
- `templateId`, `brandFoodId`: Defaults to `null`

### Migration Path

```python
# Backfill existing ingredients
ingredients = fetch_all_ingredients()
for ing in ingredients:
    if not ing.get("parsingStrategy"):
        # Infer from source field
        if ing.get("source") == "gpt":
            ing["parsingStrategy"] = "gpt"
            ing["confidence"] = 0.65  # Default for GPT
        elif ing.get("source") == "manual":
            ing["parsingStrategy"] = "manual"
            ing["confidence"] = 1.0
        # Update ingredient
        update_ingredient(ing["id"], {
            "parsingStrategy": ing["parsingStrategy"],
            "confidence": ing["confidence"]
        })
```

---

## Summary

The schema now fully supports:

1. ✅ **Hybrid parsing**: Track which strategy was used
2. ✅ **Confidence scoring**: Know when to trust a parse
3. ✅ **Cost optimization**: Cache GPT responses
4. ✅ **Brand awareness**: Brand-specific nutrition data
5. ✅ **Template system**: User's recurring meals
6. ✅ **Learning system**: Track which strategies are most accurate

**Result**: Ready for Tier 1-4 implementation with no schema changes needed!
