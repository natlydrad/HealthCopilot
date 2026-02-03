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

## USDA brand match corrections: show product images, click to select

**What:** When we show USDA options for a brand correction (e.g. "Silk Original Soy Milk"), display product images for each option so the user can visually pick the right one. User clicks the correct product image to select it.

**Why nice-to-have:**
- Visual confirmation reduces mis-clicks (e.g. Silk Unsweetened vs Silk Original look different).
- Better UX for brand-heavy corrections—user sees the package, not just text + macros.
- Complements the existing "pick from USDA options" flow we built.

**Why not critical:**
- USDA FoodData Central API does not return product images (it’s a nutrition DB, not a product catalog).
- Would require an external source for images (Open Food Facts, Google Images, brand CDNs, etc.).
- Text + macros selection already works.

**Rough implementation:**
1. **Image source:** Open Food Facts has product images; could try barcode→OFF→image_url when we have a barcode. Or: search Google/Bing Images API (costs, rate limits) for "{brand} {product} package".
2. **UI:** Extend the USDA options cards in the correction chat—when an image URL is available, show it as a thumbnail. Keep the existing click-to-select behavior.
3. **Fallback:** No image → show text-only card as today.

**References:**
- USDA FoodData Central: no product images in API responses.
- Open Food Facts: product images available via API for barcode lookups.

---

*Add more nice-to-haves below as we go.*
