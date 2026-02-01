# What Are These Migrations Doing?

## TL;DR
**You're migrating your database schema** to support Tier 4 (Stage 4) features: hybrid parsing strategy, confidence scoring, and cost optimization. The migrations add new fields and collections to your PocketBase database.

## What Are Database Migrations?

Database migrations are scripts that **change your database structure** (add tables, add columns, modify data) in a controlled, repeatable way. Think of them like version control for your database schema.

**Why use migrations?**
- ✅ Track schema changes over time
- ✅ Apply changes consistently across environments (dev → staging → production)
- ✅ Rollback if something breaks
- ✅ Team members can sync their local databases

## What These Specific Migrations Do

### Migration 1759799999: Create `ingredients` Collection
**What:** Creates the base `ingredients` table if it doesn't exist  
**Why:** Foundation for storing parsed meal ingredients

### Migration 1759800000: Create `user_preferences` Collection (Tier 1)
**What:** Creates table to store user preferences (brands, portion multipliers, dietary restrictions)  
**Why:** Enables personalization - learn what brands users eat, their typical portion sizes

### Migration 1759800001: Create `ingredient_corrections` Collection (Tier 1)
**What:** Creates table to track when users correct parsed ingredients  
**Why:** Critical for learning - stores original parse vs. user correction so you can learn from mistakes

### Migration 1759800002: Add Hybrid Parsing Fields to `ingredients` (Tier 4) ⭐
**What:** Adds 3 new fields to the `ingredients` table:
- `parsingStrategy` (select): Which method parsed this ingredient? (template, brand_db, history, gpt, manual, cached)
- `confidence` (number 0.0-1.0): How confident are we in this parse?
- `parsingMetadata` (json): Flexible storage for parsing details

**Why:** This is the **core of Tier 4** - enables hybrid parsing:
- Track which parsing method was used (so you know what's most accurate)
- Assign confidence scores (so you know when to ask users to confirm)
- Store metadata (for debugging and optimization)

### Migration 1759800003: Create `brand_foods` Collection (Tier 2)
**What:** Creates table for brand-specific nutrition data (e.g., Chipotle burrito bowl nutrition)  
**Why:** Instead of parsing "Chipotle bowl" with GPT every time, look it up in this database first (faster, cheaper, more accurate)

### Migration 1759800004: Create `meal_templates` Collection (Tier 3)
**What:** Creates table for user's recurring meals (e.g., "my usual breakfast")  
**Why:** When user logs "my usual breakfast", match it to a template instead of parsing with GPT (instant, free, accurate)

### Migration 1759800005: Create `parsing_cache` Collection (Tier 4) ⭐
**What:** Creates table to cache GPT parsing results  
**Why:** Cost optimization - if you've parsed "chicken salad" before, reuse that result instead of calling GPT again (saves money, faster)

### Migration 1759800006: Add Relations to `ingredients` (Tier 2-3)
**What:** Adds 2 relation fields to `ingredients`:
- `templateId`: Links to `meal_templates` if parsed from a template
- `brandFoodId`: Links to `brand_foods` if parsed from brand database

**Why:** Track where ingredients came from (for learning and debugging)

### Migration 1759800007: Add `mealId` Relation to `ingredients`
**What:** Adds `mealId` field linking ingredients to meals  
**Why:** Connect ingredients back to the meal they belong to (basic data modeling)

## Why Is This Migration Necessary?

### Current State (Before Migrations)
- ❌ All meals parsed with GPT Vision (expensive, slow)
- ❌ No tracking of parsing method or confidence
- ❌ Can't reuse previous parses
- ❌ No brand database or meal templates
- ❌ No way to optimize costs

### After Migrations (Tier 4)
- ✅ Hybrid parsing: Try templates/brand DB/history/cache FIRST, GPT only as last resort
- ✅ Track parsing strategy and confidence for every ingredient
- ✅ Cache GPT results to avoid redundant API calls
- ✅ Brand database for common restaurants
- ✅ Meal templates for recurring meals
- ✅ **Goal: 70% of meals parsed without GPT, 50% cost reduction**

## Do You Need to Push/Deploy?

### ✅ YES - You Should Push the Fixed Migrations

**Why:**
1. **Production needs these changes** - Your Render deployment (production) needs the new database schema
2. **Migrations run automatically** - Your Dockerfile (line 45) runs migrations on every deployment
3. **The fixes are important** - The broken migrations would fail in production too

### How to Deploy:

1. **Commit the fixed migrations:**
   ```bash
   git add backend/pb_migrations/*.js
   git commit -m "Fix Tier 4 migrations: use getAll() instead of getById()"
   ```

2. **Push to trigger deployment:**
   ```bash
   git push origin main
   ```

3. **Render will automatically:**
   - Build new Docker image with fixed migrations
   - Run migrations on startup
   - Apply schema changes to production database

### ⚠️ Important Notes:

- **Migrations are safe** - They only ADD fields/collections, they don't delete data
- **Idempotent** - Can run multiple times safely (checks if fields exist first)
- **Production data is safe** - Your Dockerfile preserves existing data (line 37-42)
- **Migrations run on startup** - Every time PocketBase starts, it checks for new migrations

## What Happens When Migrations Run?

1. PocketBase starts up
2. Checks `/app/pb_migrations` for migration files
3. Compares timestamps to see which migrations haven't run yet
4. Runs new migrations in order (by filename timestamp)
5. Updates internal migration log
6. Starts serving requests

**If a migration fails:**
- Migration is rolled back (transaction)
- PocketBase won't start (prevents broken state)
- You'll see error logs

**If migrations succeed:**
- New fields/collections appear in PocketBase admin UI
- Your application code can now use the new fields
- No data is lost (only additions)

## Next Steps After Migrations Run

Once migrations are deployed and running:

1. **Verify schema** - Check PocketBase admin UI to confirm new fields exist
2. **Update application code** - Modify your parser to use hybrid strategy
3. **Populate collections** - Add brand foods, create meal templates
4. **Implement caching** - Update parser to check cache before GPT
5. **Add confidence scoring** - Assign confidence based on parsing method

## Summary

**What:** Database schema changes to support Tier 4 hybrid parsing  
**Why:** Reduce GPT costs by 50%, improve accuracy, enable personalization  
**When:** Migrations run automatically on deployment  
**Risk:** Low - only adds fields, doesn't delete data  
**Action:** Push the fixed migrations to trigger deployment
