let authToken = null;
const PB_BASE = "https://pocketbase-1j2x.onrender.com";
const PARSE_API_URL = import.meta.env.VITE_PARSE_API_URL || "http://localhost:5001";

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
export async function fetchMealsForDateRange(startDate, endDate) {
  if (!authToken) throw new Error("Not logged in");

  // startDate/endDate are "YYYY-MM-DD" in user's LOCAL calendar (from Dashboard)
  // Interpret as local midnight/end-of-day, then convert to UTC for PocketBase filter
  // (avoids timezone bug: e.g. Feb 3 PST should query Feb 3 08:00 UTC -> Feb 4 07:59 UTC)
  const startLocal = new Date(startDate + "T00:00:00");
  const endLocal = new Date(endDate + "T23:59:59.999");
  const startTS = startLocal.toISOString().replace("T", " ").replace(/\.\d{3}Z$/, ".000Z");
  const endTS = endLocal.toISOString().replace("T", " ").replace(/\.\d{3}Z$/, ".999Z");

  // Use timestamp field for meal time filtering
  const filter = encodeURIComponent(
    `timestamp >= "${startTS}" && timestamp <= "${endTS}"`
  );

  const url = `${PB_BASE}/api/collections/meals/records?perPage=100&sort=-timestamp&filter=${filter}`;
  console.log("🔍 Fetching meals:", startDate, "to", endDate);

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

// Create a new meal (text-only, for web dashboard Add Meal)
export async function createMeal(text, timestamp) {
  if (!authToken) throw new Error("Not logged in");
  const userId = getCurrentUserId();
  if (!userId) throw new Error("User not found");

  const localId = "web-" + Date.now() + "-" + Math.random().toString(36).slice(2, 9);
  const ts = timestamp instanceof Date ? timestamp : new Date(timestamp);
  const iso = ts.toISOString();

  const res = await fetch(`${PB_BASE}/api/collections/meals/records`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${authToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      user: userId,
      text: (text || "").trim(),
      timestamp: iso,
      localId,
    }),
  });

  if (!res.ok) {
    const error = await res.text();
    throw new Error(`Failed to create meal: ${error}`);
  }

  return res.json();
}

export async function fetchIngredients(mealId) {
  // Prefer Parse API: fetches with admin token, includes full nutrition (bypasses PocketBase rules)
  const useProxy = import.meta.env.DEV && !import.meta.env.VITE_PARSE_API_URL;
  const parseUrl = useProxy ? `/parse-api/ingredients/${mealId}` : `${PARSE_API_URL}/ingredients/${mealId}`;
  if (authToken) {
    try {
      const res = await fetch(parseUrl, {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        const items = data.items || [];
        console.log("📦 fetchIngredients (Parse API) got", items.length, "ingredients");
        if (items.length > 0) {
          const first = items[0];
          console.log("📊 [diagnostic] first ingredient keys:", Object.keys(first), "nutrition:", first?.nutrition ? (Array.isArray(first.nutrition) ? `array[${first.nutrition.length}]` : typeof first.nutrition) : "missing");
        }
        return items;
      }
    } catch (e) {
      console.warn("Parse API ingredients fetch failed, falling back to PocketBase:", e.message);
    }
  }

  // Fallback: direct PocketBase
  const filter = encodeURIComponent(`(mealId='${mealId}')`);
  const url = `${PB_BASE}/api/collections/ingredients/records?filter=${filter}`;
  console.log("🛰 Fetching:", url);
  const res = await fetch(url, {
    headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
  });

  if (!res.ok) {
    console.error("❌ fetchIngredients failed", res.status, res.statusText);
    throw new Error("Failed to fetch ingredients");
  }

  const data = await res.json();
  const items = data.items || [];
  console.log("📦 fetchIngredients (PocketBase) got", items.length, "ingredients");
  if (items.length > 0) {
    const first = items[0];
    console.log("📊 [diagnostic] first ingredient keys:", Object.keys(first), "nutrition:", first?.nutrition ? (Array.isArray(first.nutrition) ? `array[${first.nutrition.length}]` : typeof first.nutrition) : "missing");
  }
  return items;
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

// Parse and save ingredients for a meal (parse-on-view)
export async function parseAndSaveMeal(meal) {
  const hasText = meal.text?.trim();
  const hasImage = meal.image;
  if (!hasText && !hasImage) return { ingredients: [], classificationResult: null };

  // Try Parse API first (supports images + GPT)
  try {
    const useProxy = import.meta.env.DEV && !import.meta.env.VITE_PARSE_API_URL;
    const url = useProxy ? `/parse-api/parse/${meal.id}` : `${PARSE_API_URL}/parse/${meal.id}`;
    const timezone = typeof Intl !== "undefined" && Intl.DateTimeFormat ? Intl.DateTimeFormat().resolvedOptions().timeZone : "";
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}) },
      body: JSON.stringify(timezone ? { timezone } : {}),
    });
    if (res.ok) {
      const data = await res.json();
      return {
        ingredients: data.ingredients || [],
        classificationResult: data.classificationResult || null,
        message: data.message,
        reason: data.reason,
        source: data.source,
        ...data,
      };
    }
  } catch (err) {
    console.warn("Parse API unreachable, falling back to simple parser:", err.message);
  }

  // Fallback: simple text-only parsing
  if (!hasText) return { ingredients: [], classificationResult: null };
  const parsed = await parseMealSimple(meal.text);
  if (parsed.length === 0) return { ingredients: [], classificationResult: null };

  const saved = [];
  for (const ing of parsed) {
    try {
      const usda = await lookupUSDANutrition(ing.name);
      const result = await createIngredient({
        mealId: meal.id,
        name: ing.name,
        quantity: ing.quantity || 1,
        unit: ing.unit || "serving",
        category: ing.category || "food",
        source: usda ? "usda" : "simple",
        usdaCode: usda?.usdaCode || null,
        nutrition: usda?.nutrition || [],
      });
      saved.push(result);
    } catch (err) {
      console.error("Failed to save ingredient:", ing.name, err);
    }
  }
  return { ingredients: saved, classificationResult: null };
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
  });

  if (!res.ok) return [];
  const data = await res.json();
  return data.items || [];
}

// Get learned patterns — uses Parse API (reads user_food_profile) so Learning panel works
// even when PocketBase API rules block direct access
export async function getLearnedPatterns() {
  const useProxy = import.meta.env.DEV && !import.meta.env.VITE_PARSE_API_URL;
  const url = useProxy ? "/parse-api/learning/patterns" : `${PARSE_API_URL}/learning/patterns`;
  if (authToken) {
    try {
      const headers = { Authorization: `Bearer ${authToken}`, "Cache-Control": "no-store" };
      if (getCurrentUserId()) headers["X-User-Id"] = getCurrentUserId();
      const res = await fetch(url, { headers });
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data.patterns)) return data.patterns;
      }
    } catch (e) {
      console.warn("Parse API learning/patterns failed, falling back to corrections:", e);
    }
  }
  // Fallback: aggregate from corrections
  const corrections = await getCorrections(200);
  const patterns = {};
  for (const c of corrections) {
    if (c.correctionType === "add_missing") continue;
    const orig = c.originalParse?.name?.toLowerCase();
    const corr = c.userCorrection?.name;
    if (orig && corr && orig !== corr.toLowerCase()) {
      const key = `${orig}→${corr}`;
      if (!patterns[key]) {
        patterns[key] = { original: orig, learned: corr, count: 0, correctionIds: [] };
      }
      patterns[key].count++;
      if (c.id) patterns[key].correctionIds.push(c.id);
    }
  }
  return Object.values(patterns).map(p => ({
    ...p,
    status: p.count >= 3 ? "confident" : "learning",
    confidence: Math.min(0.5 + (p.count * 0.15), 0.99),
  })).sort((a, b) => b.count - a.count);
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

// ============================================================
// PARSE API (corrections, reparse, clear, non-food, learning)
// ============================================================

export function getParseApiUrl() {
  return PARSE_API_URL;
}

function _parseApiFetch(path, options = {}) {
  const useProxy = import.meta.env.DEV && !import.meta.env.VITE_PARSE_API_URL;
  const url = useProxy ? `/parse-api${path}` : `${PARSE_API_URL}${path}`;
  return fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
      ...options.headers,
    },
    ...options,
  });
}

export async function fetchHasNonFoodLogs(mealId) {
  if (!authToken) return false;
  try {
    const res = await fetch(
      `${PB_BASE}/api/collections/non_food_logs/records?filter=mealId='${mealId}'&perPage=1`,
      { headers: { Authorization: `Bearer ${authToken}` }, cache: "no-store" }
    );
    if (!res.ok) return false;
    const data = await res.json();
    return (data.items?.length || 0) > 0;
  } catch {
    return false;
  }
}

export async function clearNonFoodClassification(mealId) {
  if (!authToken) throw new Error("Not logged in");
  const logs = await fetch(
    `${PB_BASE}/api/collections/non_food_logs/records?filter=mealId='${mealId}'`,
    { headers: { Authorization: `Bearer ${authToken}` } }
  ).then((r) => r.json()).catch(() => ({ items: [] }));
  for (const log of logs.items || []) {
    await fetch(`${PB_BASE}/api/collections/non_food_logs/records/${log.id}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${authToken}` },
    });
  }
  await fetch(`${PB_BASE}/api/collections/meals/records/${mealId}`, {
    method: "PATCH",
    headers: { Authorization: `Bearer ${authToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ isFood: true, categories: [] }),
  });
}

export async function clearMealIngredients(mealId) {
  if (!authToken) throw new Error("Not logged in");
  const useProxy = import.meta.env.DEV && !import.meta.env.VITE_PARSE_API_URL;
  const url = useProxy ? `/parse-api/clear/${mealId}` : `${PARSE_API_URL}/clear/${mealId}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { Authorization: `Bearer ${authToken}` },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Clear failed (${res.status})`);
  }
  const data = await res.json();
  return data.deleted ?? 0;
}

export async function deleteIngredient(ingredientId) {
  if (!authToken) throw new Error("Not logged in");
  const useProxy = import.meta.env.DEV && !import.meta.env.VITE_PARSE_API_URL;
  const url = useProxy ? `/parse-api/delete-ingredient/${ingredientId}` : `${PARSE_API_URL}/delete-ingredient/${ingredientId}`;
  const res = await fetch(url, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${authToken}` },
  });
  if (!res.ok) {
    const text = await res.text();
    let msg = text;
    try {
      const j = text ? JSON.parse(text) : {};
      if (typeof j?.error === "string" && j.error) msg = j.error;
    } catch (_) {}
    throw new Error(msg || `Delete failed (${res.status})`);
  }
  const data = await res.json();
  return data;
}

export async function addIngredients(mealId, text) {
  if (!authToken) throw new Error("Not logged in");
  const res = await _parseApiFetch(`/add-ingredients/${mealId}`, {
    method: "POST",
    body: JSON.stringify({ text: (text || "").trim() }),
  });
  if (!res.ok) {
    const text = await res.text();
    let msg = text;
    try {
      const j = text ? JSON.parse(text) : {};
      if (typeof j?.error === "string" && j.error) msg = j.error;
    } catch (_) {}
    throw new Error(msg || `Add ingredients failed (${res.status})`);
  }
  return res.json();
}

export async function updateIngredientPortion(ingredientId, quantity, unit) {
  if (!authToken) throw new Error("Not logged in");
  const res = await _parseApiFetch(`/update-portion/${ingredientId}`, {
    method: "POST",
    body: JSON.stringify({ quantity: Number(quantity), unit: (unit || "serving").trim() }),
  });
  if (!res.ok) {
    const text = await res.text();
    let msg = text;
    try {
      const j = text ? JSON.parse(text) : {};
      if (typeof j?.error === "string" && j.error) msg = j.error;
    } catch (_) {}
    throw new Error(msg || `Update portion failed (${res.status})`);
  }
  return res.json();
}

export async function sendCorrectionMessage(ingredientId, message, conversation = []) {
  const res = await _parseApiFetch(`/correct/${ingredientId}`, {
    method: "POST",
    body: JSON.stringify({ message, conversation }),
  });
  if (!res.ok) {
    const text = await res.text();
    let msg = text;
    try {
      const j = text ? JSON.parse(text) : {};
      if (typeof j?.error === "string" && j.error) msg = j.error;
    } catch (_) {}
    throw new Error(msg || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function previewCorrection(ingredientId, correction, learned, correctionReason, shouldLearn, conversation) {
  return saveCorrection(ingredientId, correction, learned, correctionReason, shouldLearn, conversation, true);
}

export async function saveCorrection(ingredientId, correction, learned, correctionReason, shouldLearn, conversation, preview = false) {
  const res = await _parseApiFetch(`/correct/${ingredientId}/save`, {
    method: "POST",
    body: JSON.stringify({
      correction,
      learned,
      correctionReason,
      shouldLearn,
      conversation,
      preview,
    }),
  });
  if (!res.ok) {
    const text = await res.text();
    let msg = text;
    try {
      const j = text ? JSON.parse(text) : {};
      if (typeof j?.error === "string" && j.error) msg = j.error;
    } catch (_) {}
    throw new Error(msg || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function reparseIngredientFromText(ingredientId, text, preview = true) {
  if (!authToken) throw new Error("Not logged in");
  const res = await _parseApiFetch(`/reparse/${ingredientId}`, {
    method: "POST",
    body: JSON.stringify({ text: (text || "").trim(), preview }),
  });
  if (!res.ok) {
    const text = await res.text();
    let msg = text;
    try {
      const j = text ? JSON.parse(text) : {};
      if (typeof j?.error === "string" && j.error) msg = j.error;
    } catch (_) {}
    throw new Error(msg || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function removeLearnedPattern(original, learned, correctionIds = []) {
  if (!authToken) throw new Error("Not logged in");
  const useProxy = import.meta.env.DEV && !import.meta.env.VITE_PARSE_API_URL;
  const url = useProxy ? "/parse-api/learning/unlearn" : `${PARSE_API_URL}/learning/unlearn`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${authToken}`,
      "Content-Type": "application/json",
      ...(getCurrentUserId() ? { "X-User-Id": getCurrentUserId() } : {}),
    },
    body: JSON.stringify({ original: (original || "").trim(), learned: (learned || "").trim(), correctionIds: correctionIds || [] }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.error || `Unlearn failed (${res.status})`);
  }
}