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
  console.log("Raw meals response:", data); // <-- log everything

  if (!data || !data.items) {
    console.warn("No 'items' field in meal data:", data);
    return [];
  }

  // Optional: sort client-side by created just to be sure
  const sorted = [...data.items].sort(
    (a, b) => new Date(b.created) - new Date(a.created)
  );
  console.log("Sorted meal IDs:", sorted.map((m) => m.id));
  return sorted;
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

// Create ingredient correction
export async function correctIngredient(ingredientId, originalParse, userCorrection) {
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