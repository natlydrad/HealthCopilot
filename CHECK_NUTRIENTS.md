# Troubleshooting: Missing Nutrients

## Quick Checks

### 1. Check if data still exists in PocketBase
- Open PocketBase admin UI
- Go to Collections → ingredients
- Check if ingredients still have `nutrition` field populated
- Check if `nutrition` field is JSON array format

### 2. Check browser console
- Open web dashboard
- Open browser DevTools (F12)
- Check Console tab for errors
- Check Network tab - are ingredients being fetched?

### 3. Check migration status
- In PocketBase admin, go to Settings → Migrations
- Check if migrations ran successfully
- Look for any errors in migration logs

## Possible Issues

### Issue 1: Migration Syntax Error
The migration `1759800002_updated_ingredients_hybrid.js` uses `collection.fields.getById()` which might not be the correct PocketBase API. If this fails, the migration might have errored.

**Fix**: Check PocketBase logs for migration errors.

### Issue 2: Data Still There, Just Not Displaying
The nutrients might still be in the database but not displaying due to:
- API fetch issue
- Frontend parsing issue
- Field name change

**Fix**: Check browser console and Network tab.

### Issue 3: Migration Rolled Back
If a migration failed and rolled back, it might have affected data.

**Fix**: Check migration status in PocketBase admin.

## Quick Fixes

### If data is gone:
1. **Restore from backup** (if you have one)
2. **Re-run enrichment pipeline** to regenerate ingredients

### If data is there but not displaying:
1. **Check API response** - open Network tab, find ingredients API call
2. **Check nutrition field format** - should be JSON array
3. **Check Dashboard code** - verify `extractMacros` function is working

## Debug Steps

1. **Check PocketBase directly**:
   ```sql
   SELECT id, name, nutrition FROM ingredients LIMIT 5;
   ```
   (or use PocketBase admin UI)

2. **Check API response**:
   - Open browser DevTools → Network tab
   - Refresh dashboard
   - Find `/api/collections/ingredients/records` request
   - Check response - does it have `nutrition` field?

3. **Check frontend code**:
   - Open Dashboard.jsx
   - Add console.log in `extractMacros`:
   ```javascript
   console.log("Nutrition data:", nutrition);
   ```

## Most Likely Cause

The migrations I created **only add fields** - they don't delete data. The most likely issue is:

1. **Migration syntax error** - `getById()` might not work, causing migration to fail
2. **Display issue** - Data is there but not showing due to frontend bug
3. **API issue** - Ingredients not being fetched correctly

**Next step**: Check PocketBase admin to see if ingredients still have nutrition data.
