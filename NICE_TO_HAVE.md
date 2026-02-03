# Nice-to-have features

Backlog of improvements we might do later. Not critical path.

---

## Barcode + Open Food Facts for packaged foods

**What:** When the user logs a photo of a packaged product (e.g. bag of chips) with a visible barcode, extract the barcode (and/or brand + product name) from the image, then look up the exact product in Open Food Facts (free API) or our brand DB. Use that nutrition instead of (or before) GPT reading the label or USDA generic lookup.

**Why nice-to-have:**
- Exact product match → more accurate, consistent nutrition for packaged foods.
- Less reliance on GPT correctly reading every field on the label.
- Good differentiator for users who log a lot of packaged stuff.

**Why not critical:**
- GPT + Nutrition Facts label already gives good data when the label is visible.
- Only helps when (1) image is a single packaged product, (2) barcode is visible/readable, (3) product is in Open Food Facts.
- No impact on whole foods, restaurant meals, or photos without barcodes.

**Rough implementation:**
1. **Image parser (parser_gpt.py):** For single packaged product with label, ask GPT to also return `barcode` (if visible), `brandName`, `productName`.
2. **Parse API:** When we have one packaged item with barcode: call Open Food Facts `GET https://world.openfoodfacts.net/api/v2/product/{barcode}`; if found, use OFF nutrition and set `parsingStrategy` appropriately.
3. **Fallback:** If barcode missing or OFF has no match, try `lookup_brand_food(brand, productName)` (our PocketBase brand_foods), then current flow (label + USDA).

**References:**
- Open Food Facts API: https://world.openfoodfacts.net/api/v2/product/{barcode} (free, no key, ~100 req/min).
- Current brand lookup: `pb_client.lookup_brand_food`, `search_brand_foods` (used only in enrich_meals.py batch, not on-demand parse).

---

## Brand identification & clarification

**What:** Resolve or clarify brand names when the user mentions a store or parent company but means a specific brand. Examples: "Costco" → "Kirkland" (Costco's store brand); "Trader Joe's" → "Trader Joe's" brand; "whole foods" → "365" or clarify. Or when a brand is mentioned but not identifiable—infer or ask.

**Why nice-to-have:**
- Improves nutrition lookup accuracy (store-brand vs national brand can differ).
- Cleaner ingredient display ("Kirkland organic almond milk" vs "Costco almond milk").
- Helps when parsing "green tea costco" or "chips from Costco"—we know which product line to look up.

**Why not critical:**
- Current flow still works with store names; USDA/GPT can often guess.
- Requires a store→brand mapping and/or GPT logic to infer.

**Rough implementation:**
1. **Store/brand mapping:** Small map of common stores → primary brand (Costco→Kirkland, Trader Joe's→Trader Joe's, Whole Foods→365, etc.).
2. **Parse/GPT:** When ingredient text contains a known store name, optionally expand to brand name before USDA lookup, or include in parsing metadata.
3. **Ambiguous brands:** If GPT sees "X brand" but can't identify X, flag for clarification or use fuzzy matching against known brands.

---

*Add more nice-to-haves below as we go.*
