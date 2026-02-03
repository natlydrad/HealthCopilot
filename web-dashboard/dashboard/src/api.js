let authToken = null;
const PB_BASE = "https://pocketbase-1j2x.onrender.com";

export function setAuthToken(token) {
  authToken = token;
}

export async function fetchMeals() {
  if (!authToken) throw new Error("Not logged in");

  const url = `${PB_BASE}/api/collections/meals/records?perPage=200&sort=-created`;
  console.log("Fetching meals from:", url);

  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${authToken}`,
    },
  });

  const data = await res.json();
  console.log("Raw meals response:", data);

  if (!data || !data.items) {
    console.warn("No 'items' field in meal data:", data);
    return [];
  }

  const sorted = [...data.items].sort(
    (a, b) => new Date(b.created) - new Date(a.created)
  );
  return sorted;
}

// Fetch meals for a specific date range (on-demand loading)
// Converts local dates to UTC for proper timezone handling
export async function fetchMealsForDateRange(startDate, endDate) {
  if (!authToken) throw new Error("Not logged in");

  // startDate and endDate are in format "YYYY-MM-DD" (local time)
  // Convert to UTC bounds based on user's timezone
  
  // Create local midnight for start date, then convert to UTC
  const localStart = new Date(`${startDate}T00:00:00`);
  const localEnd = new Date(`${endDate}T23:59:59.999`);
  
  // Format as PocketBase expects (space instead of T)
  const formatForPB = (date) => {
    return date.toISOString().replace('T', ' ');
  };
  
  const startTS = formatForPB(localStart);
  const endTS = formatForPB(localEnd);

  // Use timestamp field for meal time filtering
  const filter = encodeURIComponent(
    `timestamp >= "${startTS}" && timestamp <= "${endTS}"`
  );

  const url = `${PB_BASE}/api/collections/meals/records?perPage=500&sort=timestamp&filter=${filter}`;
  console.log("🔍 Fetching meals:", startDate, "to", endDate, "| UTC:", startTS, "to", endTS);

  try {
    const res = await fetch(url, {
      headers: {
        Authorization: `Bearer ${authToken}`,
      },
    });

    if (!res.ok) {
      const errorText = await res.text();
      console.error("❌ API error:", res.status, errorText);
      return [];
    }

    const data = await res.json();

    if (!data || !data.items) {
      console.warn("⚠️ No meals in response");
      return [];
    }

    console.log(`✅ Found ${data.items.length} meals (total: ${data.totalItems})`);
    return data.items;
  } catch (err) {
    console.error("❌ Failed to fetch meals:", err);
    return [];
  }
}


export async function fetchIngredients(mealId) {
  // PocketBase filter for a relation field must use this format:
  // filter=(mealId='jmlpwbqrpq4etn8')
  // perPage=500: default is 30 - we were only fetching/deleting first 30, leaving rest to "come back" on refresh
  const filter = encodeURIComponent(`(mealId='${mealId}')`);

  const url = `${PB_BASE}/api/collections/ingredients/records?filter=${filter}&perPage=500`;

  console.log("🛰 Fetching:", url);
  const res = await fetch(url, {
    headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
    cache: "no-store", // prevent stale cache after clear
  });

  if (!res.ok) {
    console.error("❌ fetchIngredients failed", res.status, res.statusText);
    throw new Error("Failed to fetch ingredients");
  }

  const data = await res.json();
  console.log("📦 fetchIngredients got", data.items.length, "ingredients");
  return data.items;
}

// Fetch all ingredients at once (more efficient than per-meal)
export async function fetchAllIngredients() {
  // Don't expand mealId relation - we just need the ID string
  const url = `${PB_BASE}/api/collections/ingredients/records?perPage=500&sort=-created`;
  
  const res = await fetch(url, {
    headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
  });

  if (!res.ok) {
    console.error("❌ fetchAllIngredients failed", res.status, res.statusText);
    return [];
  }

  const data = await res.json();
  const items = data.items || [];
  
  // Debug: Log first ingredient's nutrition field
  if (items.length > 0) {
    const sample = items[0];
    const mealIdValue = sample.mealId;
    const mealIdType = typeof mealIdValue;
    const mealIdResolved = mealIdValue && typeof mealIdValue === 'object' ? mealIdValue.id : mealIdValue;
    
    console.log("🔍 Sample ingredient from API:", {
      id: sample.id,
      name: sample.name,
      mealId: mealIdValue,
      mealIdType: mealIdType,
      mealIdResolved: mealIdResolved,
      mealIdIsObject: typeof mealIdValue === 'object',
      hasNutrition: !!sample.nutrition,
      nutritionType: typeof sample.nutrition,
      nutritionIsArray: Array.isArray(sample.nutrition),
      nutritionPreview: sample.nutrition 
        ? (typeof sample.nutrition === 'string' 
          ? sample.nutrition.substring(0, 200) 
          : JSON.stringify(sample.nutrition).substring(0, 200))
        : null,
      allFields: Object.keys(sample)
    });
  }
  
  return items;
}

// Get current user ID
export function getCurrentUserId() {
  const userStr = localStorage.getItem("pb_user");
  if (!userStr) return null;
  try {
    const user = JSON.parse(userStr);
    return user.id;
  } catch {
    return null;
  }
}

// Create ingredient correction with context
export async function correctIngredient(ingredientId, originalParse, userCorrection, context = {}) {
  if (!authToken) throw new Error("Not logged in");
  
  const userId = getCurrentUserId();
  if (!userId) throw new Error("User not found");

  // Calculate multiplier
  const originalQty = originalParse.quantity || 1;
  const correctedQty = userCorrection.quantity || 1;
  const multiplier = originalQty > 0 ? correctedQty / originalQty : 1.0;

  // Determine correction type
  let correctionType = "quantity_change";
  if (originalParse.name !== userCorrection.name) {
    correctionType = "name_change";
  } else if (originalParse.unit !== userCorrection.unit) {
    correctionType = "unit_change";
  }
  if (originalParse.name !== userCorrection.name && originalParse.quantity !== userCorrection.quantity) {
    correctionType = "complete_replace";
  }

  const payload = {
    ingredientId,
    user: userId,
    originalParse,
    userCorrection,
    multiplier,
    correctionType,
    context, // { mealTime, mealType, mealText }
  };

  const url = `${PB_BASE}/api/collections/ingredient_corrections/records`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${authToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const error = await res.text();
    throw new Error(`Failed to create correction: ${error}`);
  }

  return res.json();
}

// Delete a correction (to "unlearn" a mistake)
export async function deleteCorrection(correctionId) {
  if (!authToken) throw new Error("Not logged in");

  const url = `${PB_BASE}/api/collections/ingredient_corrections/records/${correctionId}`;
  const res = await fetch(url, {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${authToken}`,
    },
  });

  if (!res.ok) {
    const error = await res.text();
    throw new Error(`Failed to delete correction: ${error}`);
  }

  return true;
}

// Update ingredient with corrected values
export async function updateIngredient(ingredientId, updates) {
  if (!authToken) throw new Error("Not logged in");

  const url = `${PB_BASE}/api/collections/ingredients/records/${ingredientId}`;
  const res = await fetch(url, {
    method: "PATCH",
    headers: {
      Authorization: `Bearer ${authToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(updates),
  });

  if (!res.ok) {
    const error = await res.text();
    throw new Error(`Failed to update ingredient: ${error}`);
  }

  return res.json();
}

// Simple rule-based parsing (no API key needed)
// For complex meals, use the backend script
export async function parseMealSimple(mealText) {
  if (!mealText?.trim()) return [];
  
  // Simple parsing: split by common separators
  const text = mealText.toLowerCase();
  const separators = /[,\n]|(?:\band\b)|(?:\bwith\b)|(?:\bw\/\b)/;
  const parts = text.split(separators).map(p => p.trim()).filter(p => p.length > 1);
  
  const ingredients = [];
  for (const part of parts) {
    // Try to extract quantity and unit
    const match = part.match(/^(\d+\.?\d*)\s*(oz|g|cup|cups|tbsp|tsp|pieces?|slices?|eggs?)?\s*(.+)$/);
    if (match) {
      ingredients.push({
        name: match[3].trim(),
        quantity: parseFloat(match[1]),
        unit: match[2] || "serving",
        category: "food"
      });
    } else {
      // No quantity found, default to 1 serving
      ingredients.push({
        name: part,
        quantity: 1,
        unit: "serving",
        category: guessCategory(part)
      });
    }
  }
  
  return ingredients;
}

// Guess category based on keywords
function guessCategory(name) {
  const drinks = ['coffee', 'tea', 'water', 'milk', 'juice', 'smoothie', 'latte'];
  const supplements = ['vitamin', 'supplement', 'pill', 'capsule', 'probiotic'];
  
  const lower = name.toLowerCase();
  if (drinks.some(d => lower.includes(d))) return "drink";
  if (supplements.some(s => lower.includes(s))) return "supplement";
  return "food";
}

// Delete an ingredient record
export async function deleteIngredient(ingredientId) {
  if (!authToken) throw new Error("Not logged in");

  const url = `${PB_BASE}/api/collections/ingredients/records/${ingredientId}`;
  const res = await fetch(url, {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${authToken}`,
    },
  });

  if (!res.ok) {
    const error = await res.text();
    console.error(`DELETE ${url} → ${res.status}`, error);
    throw new Error(`Delete failed (${res.status}): ${error || res.statusText}`);
  }

  return true;
}

// Delete ALL ingredients for a meal (clear parse)
// Uses Parse API (service token) to bypass PocketBase deleteRule 403
export async function clearMealIngredients(mealId) {
  if (!authToken) throw new Error("Not logged in");

  // In dev without VITE_PARSE_API_URL: use Vite proxy /parse-api → localhost:5001 (avoids CORS)
  const parseUrl = import.meta.env.VITE_PARSE_API_URL || "http://localhost:5001";
  const useProxy = import.meta.env.DEV && !import.meta.env.VITE_PARSE_API_URL;
  const url = useProxy ? `/parse-api/clear/${mealId}` : `${parseUrl}/clear/${mealId}`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30_000);
  const res = await fetch(url, {
    method: "POST",
    headers: { Authorization: `Bearer ${authToken}` },
    signal: controller.signal,
  });
  clearTimeout(timeout);
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `Clear failed (${res.status})`);
  }
  const data = await res.json();
  const deleted = data.deleted ?? 0;
  console.log(`✅ Cleared ${deleted} ingredients for meal ${mealId}`);
  return deleted;
}

// Check if meal was classified as non-food (has non_food_logs)
export async function fetchHasNonFoodLogs(mealId) {
  if (!authToken) return false;
  const filter = encodeURIComponent(`mealId='${mealId}'`);
  const res = await fetch(
    `${PB_BASE}/api/collections/non_food_logs/records?filter=${filter}&perPage=1`,
    { headers: { Authorization: `Bearer ${authToken}` }, cache: "no-store" }
  );
  if (!res.ok) return false;
  const data = await res.json();
  return (data.items?.length ?? 0) > 0;
}

// Clear non-food classification: delete non_food_logs for this meal, reset meal.isFood to null
export async function clearNonFoodClassification(mealId) {
  if (!authToken) throw new Error("Not logged in");

  const filter = encodeURIComponent(`mealId='${mealId}'`);
  const listRes = await fetch(
    `${PB_BASE}/api/collections/non_food_logs/records?filter=${filter}&perPage=50`,
    { headers: { Authorization: `Bearer ${authToken}` }, cache: "no-store" }
  );
  if (!listRes.ok) throw new Error("Failed to fetch non-food logs");
  const { items } = await listRes.json();
  for (const log of items || []) {
    const delRes = await fetch(
      `${PB_BASE}/api/collections/non_food_logs/records/${log.id}`,
      { method: "DELETE", headers: { Authorization: `Bearer ${authToken}` } }
    );
    if (!delRes.ok) console.warn("Failed to delete non_food_log", log.id);
  }

  const patchRes = await fetch(
    `${PB_BASE}/api/collections/meals/records/${mealId}`,
    {
      method: "PATCH",
      headers: {
        Authorization: `Bearer ${authToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ isFood: null }),
    }
  );
  if (!patchRes.ok) throw new Error("Failed to reset meal classification");
  console.log(`✅ Cleared non-food classification for meal ${mealId}`);
  return true;
}

// Create an ingredient record
export async function createIngredient(ingredient) {
  if (!authToken) throw new Error("Not logged in");
  
  const url = `${PB_BASE}/api/collections/ingredients/records`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${authToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(ingredient),
  });

  if (!res.ok) {
    const error = await res.text();
    throw new Error(`Failed to create ingredient: ${error}`);
  }

  return res.json();
}

// Backend Parse API URL (for GPT Vision image parsing)
const PARSE_API_URL = import.meta.env.VITE_PARSE_API_URL || "http://localhost:5001";
export function getParseApiUrl() {
  return PARSE_API_URL;
}

// Parse and save ingredients for a meal (parse-on-view)
// Tries backend API first (supports images), falls back to simple text parsing
export async function parseAndSaveMeal(meal) {
  const hasText = meal.text?.trim();
  const hasImage = meal.image;
  
  if (!hasText && !hasImage) return { ingredients: [], classificationResult: null };
  
  console.log("🧠 Parsing meal:", meal.id, hasText ? `"${meal.text}"` : "[image only]");
  
  // Try backend API first (supports images via GPT Vision)
  // Send user's token so backend can load meal image (user-owned file)
  try {
    console.log("🔗 Trying Parse API...", `${PARSE_API_URL}/parse/${meal.id}`);
    const timezone = typeof Intl !== "undefined" && Intl.DateTimeFormat ? Intl.DateTimeFormat().resolvedOptions().timeZone : "";
    const apiRes = await fetch(`${PARSE_API_URL}/parse/${meal.id}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
      },
      body: JSON.stringify(timezone ? { timezone } : {}),
    });
    
    if (apiRes.ok) {
      const data = await apiRes.json();
      console.log("✅ Parse API success:", data.count, "ingredients from", data.source, data.classificationResult || "");
      return {
        ingredients: data.ingredients || [],
        classificationResult: data.classificationResult || null,
        isFood: data.isFood,
        message: data.message,
        source: data.source,
        reason: data.reason,
      };
    }
    
    // Surface backend error so user sees why it failed
    const errBody = await apiRes.json().catch(() => ({}));
    const msg = errBody?.error || errBody?.message || `Parse API returned ${apiRes.status}`;
    console.warn("⚠️ Parse API error:", msg);
    throw new Error(msg);
  } catch (err) {
    if (err instanceof Error && err.message?.startsWith("Parse API returned")) {
      throw err;
    }
    if (err instanceof Error && err.message && err.message !== "Failed to fetch") {
      throw err;
    }
    console.log("⚠️ Parse API unreachable:", err?.message || err, "- falling back to simple parser");
  }
  
  // Fallback: Simple text parsing (no images)
  if (!hasText) {
    const msg = "Parse server unreachable. Image-only meals need the parse server; text-only meals will use simple parser.";
    throw new Error(msg);
  }
  
  const parsed = await parseMealSimple(meal.text);
  console.log("📝 Simple parsed:", parsed);
  
  if (parsed.length === 0) return { ingredients: [], classificationResult: null };

  // Save each ingredient
  const saved = [];
  for (const ing of parsed) {
    try {
      // Look up nutrition from USDA
      const usda = await lookupUSDANutrition(ing.name);
      
      const quantity = ing.quantity || 1;
      const unit = ing.unit || "serving";
      
      // Scale nutrition to actual portion size
      const scaledNutrition = usda?.nutrition 
        ? scaleNutrition(usda.nutrition, quantity, unit)
        : [];
      
      const ingredient = {
        mealId: meal.id,
        name: ing.name,
        quantity,
        unit,
        category: ing.category || "food",
        source: usda ? "usda" : "simple",
        usdaCode: usda?.usdaCode || null,
        nutrition: scaledNutrition,
      };
      
      const result = await createIngredient(ingredient);
      saved.push(result);
      console.log("✅ Saved:", ing.name, `(${quantity} ${unit})`);
    } catch (err) {
      console.error("Failed to save ingredient:", ing.name, err);
    }
  }
  
  return { ingredients: saved, classificationResult: null };
}

// ============================================================
// CORRECTION CHAT API
// ============================================================

// Send a message in the correction chat
export async function sendCorrectionMessage(ingredientId, message, conversation = []) {
  console.log("💬 Sending correction message:", message);
  
  try {
    const res = await fetch(`${PARSE_API_URL}/correct/${ingredientId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, conversation }),
    });
    
    if (!res.ok) {
      const error = await res.text();
      throw new Error(`Correction API error: ${error}`);
    }
    
    const data = await res.json();
    console.log("💬 AI response:", data.reply?.substring(0, 100));
    return data;
  } catch (err) {
    console.error("Correction chat error:", err);
    throw err;
  }
}

// Preview what would be saved (no persistence)
export async function previewCorrection(ingredientId, correction, learned = null, correctionReason = null, shouldLearn = false, conversation = []) {
  return saveCorrection(ingredientId, correction, learned, correctionReason, shouldLearn, conversation, true);
}

// Save a finalized correction (correction may include chosenUsdaOption)
export async function saveCorrection(ingredientId, correction, learned = null, correctionReason = null, shouldLearn = false, conversation = [], preview = false) {
  console.log(preview ? "👁️ Previewing correction:" : "💾 Saving correction:", correction, "reason:", correctionReason);
  
  try {
    const res = await fetch(`${PARSE_API_URL}/correct/${ingredientId}/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ 
        correction, 
        learned, 
        correctionReason,
        shouldLearn,
        conversation,
        preview
      }),
    });
    
    if (!res.ok) {
      const error = await res.text();
      throw new Error(`Save correction error: ${error}`);
    }
    
    const data = await res.json();
    if (preview) {
      console.log("👁️ Preview received:", data.ingredient?.name, data.addedIngredient?.name);
    } else {
      console.log("✅ Correction saved:", data.success, "learned:", data.shouldLearn);
    }
    return data;
  } catch (err) {
    console.error(preview ? "Preview error:" : "Save correction error:", err);
    throw err;
  }
}

// Unit to grams conversion (matches backend)
const UNIT_TO_GRAMS = {
  oz: 28.35, ounce: 28.35, ounces: 28.35,
  g: 1.0, gram: 1.0, grams: 1.0,
  cup: 240.0, cups: 240.0,
  tbsp: 15.0, tablespoon: 15.0,
  tsp: 5.0, teaspoon: 5.0,
  piece: 100.0, pieces: 100.0,
  slice: 30.0, slices: 30.0,
  egg: 50.0, eggs: 50.0,
  serving: 100.0, servings: 100.0,
};

// Scale nutrition values from per-100g to actual portion
function scaleNutrition(nutrients, quantity, unit) {
  const gramsPerUnit = UNIT_TO_GRAMS[unit?.toLowerCase()] || 100;
  const grams = quantity * gramsPerUnit;
  const scaleFactor = grams / 100;
  
  console.log(`📊 Scaling: ${quantity} ${unit} = ${grams.toFixed(1)}g (${scaleFactor.toFixed(2)}x)`);
  
  return nutrients.map(n => ({
    ...n,
    value: n.value != null ? Math.round(n.value * scaleFactor * 100) / 100 : n.value
  }));
}

// USDA FoodData Central API lookup
const USDA_API_KEY = "W26xpKvwmvxKKmff5ymcSwIfOVtVW1dR6gmC3BId";

export async function lookupUSDANutrition(foodName) {
  try {
    // Search for the food
    const searchUrl = `https://api.nal.usda.gov/fdc/v1/foods/search?api_key=${USDA_API_KEY}&query=${encodeURIComponent(foodName)}&pageSize=5&dataType=Foundation,SR%20Legacy`;
    
    const searchRes = await fetch(searchUrl);
    if (!searchRes.ok) return null;
    
    const searchData = await searchRes.json();
    const foods = searchData.foods || [];
    
    if (foods.length === 0) return null;
    
    // Get the best match (first result)
    const match = foods[0];
    
    return {
      usdaCode: String(match.fdcId),
      description: match.description,
      nutrition: match.foodNutrients || [],
      source: "usda",
    };
  } catch (err) {
    console.error("USDA lookup failed:", err);
    return null;
  }
}

// Get all corrections (for tracking view)
export async function getCorrections(limit = 50) {
  const url = `${PB_BASE}/api/collections/ingredient_corrections/records?sort=-created&perPage=${limit}`;
  
  const res = await fetch(url, {
    headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
    cache: "no-store",
  });

  if (!res.ok) return [];
  const data = await res.json();
  return data.items || [];
}

// Get learned patterns from user_food_profile (source of truth for what affects future parses)
// Falls back to corrections if profile is empty - fixes blank Learning tab when corrections API rules differ
export async function getLearnedPatterns() {
  const userId = getCurrentUserId();
  const patternsFromProfile = [];

  if (userId && authToken) {
    try {
      const filter = encodeURIComponent(`user="${userId}"`);
      const res = await fetch(
        `${PB_BASE}/api/collections/user_food_profile/records?filter=${filter}&perPage=5`,
        { headers: { Authorization: `Bearer ${authToken}` }, cache: "no-store" }
      );
      if (res.ok) {
        const { items } = await res.json();
        const profile = items?.[0];
        const pairs = profile?.confusionPairs || [];
        for (const c of pairs) {
          const mistaken = (c.mistaken || "").trim();
          const actual = (c.actual || "").trim();
          if (mistaken && actual && mistaken.toLowerCase() !== actual.toLowerCase()) {
            patternsFromProfile.push({
              original: mistaken.toLowerCase(),
              learned: actual,
              count: c.count ?? 1,
              correctionIds: [],
              status: (c.count ?? 1) >= 3 ? "confident" : "learning",
              confidence: Math.min(0.5 + ((c.count ?? 1) * 0.15), 0.99),
            });
          }
        }
      }
    } catch (e) {
      console.warn("Failed to load user_food_profile for learning:", e);
    }
  }

  if (patternsFromProfile.length > 0) {
    patternsFromProfile.sort((a, b) => b.count - a.count);
    return patternsFromProfile;
  }

  // Fallback: aggregate from corrections (name changes only).
  // Quantity-only corrections (e.g. 5 pieces → 6 pieces) are NOT learned as patterns:
  // they’re stored in ingredient_corrections for audit, but don’t become confusionPairs.
  const corrections = await getCorrections(200);
  const patterns = {};
  for (const c of corrections) {
    if (c.correctionType === "add_missing") continue;
    const orig = c.originalParse?.name?.toLowerCase();
    const corr = c.userCorrection?.name;
    
    if (orig && corr && orig !== corr.toLowerCase()) {
      const key = `${orig}→${corr}`;
      if (!patterns[key]) {
        patterns[key] = {
          original: orig,
          learned: corr,
          count: 0,
          correctionIds: [],
          lastCorrected: c.created,
          firstCorrected: c.created,
        };
      }
      patterns[key].count++;
      patterns[key].correctionIds.push(c.id);
      if (c.created < patterns[key].firstCorrected) {
        patterns[key].firstCorrected = c.created;
      }
    }
  }
  
  const result = Object.values(patterns).map(p => ({
    ...p,
    confidence: Math.min(0.5 + (p.count * 0.15), 0.99),
    status: p.count >= 3 ? "confident" : p.count >= 1 ? "learning" : "new",
  }));
  result.sort((a, b) => b.count - a.count);
  return result;
}

// Remove a learned pattern (unlearn a mistake) - user-facing fix for bad learning
export async function removeLearnedPattern(original, learned, correctionIds = []) {
  if (!authToken) throw new Error("Not logged in");
  const userId = getCurrentUserId();
  if (!userId) throw new Error("User not found");

  // 1. Remove from user_food_profile (stops affecting future parsing)
  const filter = encodeURIComponent(`user="${userId}"`);
  const listRes = await fetch(
    `${PB_BASE}/api/collections/user_food_profile/records?filter=${filter}`,
    { headers: { Authorization: `Bearer ${authToken}` } }
  );
  if (listRes.ok) {
    const { items } = await listRes.json();
    const profile = items?.[0];
    if (profile) {
      const orig = (original || "").toLowerCase().trim();
      const learn = (learned || "").trim();
      const confusions = (profile.confusionPairs || []).filter(
        (c) => (c.mistaken || "").toLowerCase() !== orig || (c.actual || "").trim() !== learn
      );
      const foods = (profile.foods || []).filter(
        (f) => (f.name || "").toLowerCase().trim() !== learn
      );
      const needsUpdate =
        confusions.length !== (profile.confusionPairs || []).length ||
        foods.length !== (profile.foods || []).length;
      if (needsUpdate) {
        const patch = { confusionPairs: confusions };
        if (foods.length !== (profile.foods || []).length) patch.foods = foods;
        const patchRes = await fetch(
          `${PB_BASE}/api/collections/user_food_profile/records/${profile.id}`,
          {
            method: "PATCH",
            headers: {
              Authorization: `Bearer ${authToken}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify(patch),
          }
        );
        if (!patchRes.ok) throw new Error("Failed to update profile");
      }
    }
  }

  // 2. Delete correction records (removes from Learning Panel)
  for (const id of correctionIds || []) {
    try {
      await deleteCorrection(id);
    } catch {
      // ignore per-record errors
    }
  }
}

// Get learning stats over time (for tracking adaptation)
export async function getLearningStats() {
  const corrections = await getCorrections(500);
  if (corrections.length === 0) return { timeline: [], summary: {} };
  
  // Sort by created date (oldest first)
  const sorted = [...corrections].sort((a, b) => new Date(a.created) - new Date(b.created));
  
  // Build timeline with cumulative stats
  const timeline = [];
  const seenPatterns = new Set();
  let totalCorrections = 0;
  let uniquePatterns = 0;
  let confidentPatterns = 0; // patterns corrected 3+ times
  
  // Pattern counts for confidence tracking
  const patternCounts = {};
  
  for (const c of sorted) {
    totalCorrections++;
    const orig = c.originalParse?.name?.toLowerCase();
    const corr = c.userCorrection?.name;
    
    if (orig && corr) {
      const key = `${orig}→${corr}`;
      
      // Track unique patterns
      if (!seenPatterns.has(key)) {
        seenPatterns.add(key);
        uniquePatterns++;
      }
      
      // Track pattern counts for confidence
      patternCounts[key] = (patternCounts[key] || 0) + 1;
      
      // Recalculate confident patterns
      confidentPatterns = Object.values(patternCounts).filter(cnt => cnt >= 3).length;
    }
    
    // Add milestone markers (every 5 corrections)
    if (totalCorrections % 5 === 0 || totalCorrections === sorted.length) {
      timeline.push({
        correctionNum: totalCorrections,
        date: c.created,
        uniquePatterns,
        confidentPatterns,
        latestCorrection: {
          from: orig,
          to: corr,
        },
      });
    }
  }
  
  // Summary stats
  const summary = {
    totalCorrections,
    uniquePatterns,
    confidentPatterns,
    learningRate: uniquePatterns > 0 ? (confidentPatterns / uniquePatterns * 100).toFixed(0) : 0,
    firstCorrection: sorted[0]?.created,
    lastCorrection: sorted[sorted.length - 1]?.created,
  };
  
  return { timeline, summary };
}

// Update ingredient with new name AND re-fetch nutrition
export async function updateIngredientWithNutrition(ingredientId, updates, originalName) {
  // If name changed, re-lookup nutrition
  if (updates.name && updates.name !== originalName) {
    console.log(`Name changed: "${originalName}" → "${updates.name}", looking up nutrition...`);
    
    const usda = await lookupUSDANutrition(updates.name);
    
    if (usda) {
      console.log(`Found USDA match: ${usda.description}`);
      updates.usdaCode = usda.usdaCode;
      updates.nutrition = usda.nutrition;
      updates.source = "usda";
    } else {
      console.log("No USDA match found, keeping as GPT source");
      updates.source = "gpt";
      updates.usdaCode = null;
    }
  }
  
  return updateIngredient(ingredientId, updates);
}