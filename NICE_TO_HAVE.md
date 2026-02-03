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

*Add more nice-to-haves below as we go.*
