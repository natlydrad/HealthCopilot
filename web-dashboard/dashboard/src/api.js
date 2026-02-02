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
export async function fetchMealsForDateRange(startDate, endDate) {
  if (!authToken) throw new Error("Not logged in");

  // PocketBase stores timestamps with space instead of T: "2025-12-17 22:47:57.000Z"
  // startDate and endDate are in format "YYYY-MM-DD"
  const startTS = `${startDate} 00:00:00.000Z`;
  const endTS = `${endDate} 23:59:59.999Z`;

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


export async function fetchIngredients(mealId) {
  // PocketBase filter for a relation field must use this format:
  // filter=(mealId='jmlpwbqrpq4etn8')
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

// Parse and save ingredients for a meal (parse-on-view)
// Tries backend API first (supports images), falls back to simple text parsing
export async function parseAndSaveMeal(meal) {
  const hasText = meal.text?.trim();
  const hasImage = meal.image;
  
  if (!hasText && !hasImage) return [];
  
  console.log("🧠 Parsing meal:", meal.id, hasText ? `"${meal.text}"` : "[image only]");
  
  // Try backend API first (supports images via GPT Vision)
  try {
    console.log("🔗 Trying Parse API...");
    const apiRes = await fetch(`${PARSE_API_URL}/parse/${meal.id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    
    if (apiRes.ok) {
      const data = await apiRes.json();
      console.log("✅ Parse API success:", data.count, "ingredients from", data.source);
      return data.ingredients || [];
    }
    
    console.log("⚠️ Parse API unavailable, falling back to simple parser");
  } catch (err) {
    console.log("⚠️ Parse API error:", err.message, "- falling back to simple parser");
  }
  
  // Fallback: Simple text parsing (no images)
  if (!hasText) {
    console.log("❌ Image-only meal requires Parse API");
    return [];
  }
  
  const parsed = await parseMealSimple(meal.text);
  console.log("📝 Simple parsed:", parsed);
  
  if (parsed.length === 0) return [];
  
  // Save each ingredient
  const saved = [];
  for (const ing of parsed) {
    try {
      // Look up nutrition from USDA
      const usda = await lookupUSDANutrition(ing.name);
      
      const ingredient = {
        mealId: meal.id,
        name: ing.name,
        quantity: ing.quantity || 1,
        unit: ing.unit || "serving",
        category: ing.category || "food",
        source: usda ? "usda" : "simple",
        usdaCode: usda?.usdaCode || null,
        nutrition: usda?.nutrition || [],
      };
      
      const result = await createIngredient(ingredient);
      saved.push(result);
      console.log("✅ Saved:", ing.name);
    } catch (err) {
      console.error("Failed to save ingredient:", ing.name, err);
    }
  }
  
  return saved;
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

// Get learned patterns (aggregated from corrections)
export async function getLearnedPatterns() {
  const corrections = await getCorrections(200);
  
  // Group by original → corrected
  const patterns = {};
  for (const c of corrections) {
    const orig = c.originalParse?.name?.toLowerCase();
    const corr = c.userCorrection?.name;
    
    if (orig && corr && orig !== corr.toLowerCase()) {
      const key = `${orig}→${corr}`;
      if (!patterns[key]) {
        patterns[key] = {
          original: orig,
          learned: corr,
          count: 0,
          lastCorrected: c.created,
          firstCorrected: c.created,
        };
      }
      patterns[key].count++;
      // Track first correction
      if (c.created < patterns[key].firstCorrected) {
        patterns[key].firstCorrected = c.created;
      }
    }
  }
  
  // Convert to array, add confidence, sort
  const result = Object.values(patterns).map(p => ({
    ...p,
    confidence: Math.min(0.5 + (p.count * 0.15), 0.99),
    status: p.count >= 3 ? "confident" : p.count >= 1 ? "learning" : "new",
  }));
  
  result.sort((a, b) => b.count - a.count);
  return result;
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