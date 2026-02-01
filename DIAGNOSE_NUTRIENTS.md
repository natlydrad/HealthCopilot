# Diagnose Missing Nutrients

## Step 1: Check if Data Still Exists

**In PocketBase Admin UI:**
1. Go to Collections → `ingredients`
2. Open any ingredient record
3. Check if `nutrition` field has data
4. Check if `nutrition` is a JSON array (not empty/null)

**If nutrition field is empty/null:**
- Data might have been deleted (unlikely from my migrations)
- Check migration logs for errors

**If nutrition field has data:**
- It's a display issue, not a data issue
- Check browser console for errors

## Step 2: Check Migration Status

**In PocketBase Admin:**
1. Go to Settings → Migrations
2. Check if migrations ran successfully
3. Look for `1759800002_updated_ingredients_hybrid.js` - did it succeed or fail?

**If migration failed:**
- The migration syntax might be wrong
- I've fixed it - try running migrations again

## Step 3: Check Browser Console

**In Web Dashboard:**
1. Open DevTools (F12)
2. Go to Console tab
3. Look for errors related to:
   - `extractMacros`
   - `nutrition`
   - API calls

**Common errors:**
- `nutrition is not an array` - data format issue
- `Failed to fetch ingredients` - API issue
- `Cannot read property 'value'` - data structure issue

## Step 4: Check Network Tab

**In Browser DevTools:**
1. Go to Network tab
2. Refresh dashboard
3. Find `/api/collections/ingredients/records` request
4. Check Response - does it include `nutrition` field?

**If nutrition is missing from API response:**
- Check PocketBase collection settings
- Verify field exists and is readable

**If nutrition is in API response:**
- It's a frontend parsing issue
- Check Dashboard.jsx `extractMacros` function

## Most Likely Causes

### 1. Migration Syntax Error (FIXED)
The migration used `getById()` which might not work. I've fixed it to use `getAll()` and check by name.

**Fix**: Re-run migrations with the fixed file.

### 2. Display Issue
Data is there but not displaying due to:
- Frontend code bug
- API response format change
- Field name mismatch

**Fix**: Check browser console and Network tab.

### 3. Data Actually Gone (UNLIKELY)
If data is actually deleted, it wasn't from my migrations (they only add fields).

**Fix**: Restore from backup or re-run enrichment pipeline.

## Quick Fixes

### If migration failed:
```bash
# Re-run migrations with fixed file
cd backend
./pocketbase migrate
```

### If data is there but not displaying:
1. Check browser console for errors
2. Verify API response includes nutrition
3. Check Dashboard.jsx extractMacros function

### If data is actually gone:
1. Check PocketBase backup (if you have one)
2. Re-run enrichment pipeline:
   ```bash
   cd ml-pipeline/nutrition-pipeline
   python enrich_meals.py
   ```

## Next Steps

1. **Check PocketBase admin** - is nutrition data still there?
2. **Check migration logs** - did migrations succeed?
3. **Check browser console** - any errors?
4. **Report back** - what did you find?

The migrations I created should NOT have deleted any data - they only add new fields. If data is gone, something else happened.
