import { useEffect, useState } from "react";
import { fetchMeals, fetchAllIngredients } from "./api";

export default function Dashboard() {
  const [meals, setMeals] = useState([]);
  const [ingredients, setIngredients] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        // Fetch meals and ingredients in parallel
        const [mealItems, allIngredients] = await Promise.all([
          fetchMeals(),
          fetchAllIngredients()
        ]);
        
        setMeals(mealItems);
        
        // Group ingredients by mealId
        const ingMap = {};
        for (const ing of allIngredients) {
          const mealId = ing.mealId;
          if (!mealId) continue;
          if (!ingMap[mealId]) ingMap[mealId] = [];
          ingMap[mealId].push(ing);
        }
        setIngredients(ingMap);
        console.log("Loaded", mealItems.length, "meals and", allIngredients.length, "ingredients");
      } catch (e) {
        console.error("Failed to load:", e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  // Get last 7 days (in local timezone)
  const days = [];
  for (let i = 6; i >= 0; i--) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    // Get local date in YYYY-MM-DD format
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const date = String(d.getDate()).padStart(2, '0');
    days.push(`${year}-${month}-${date}`);
  }

  // Group meals by day (convert to local date for proper grouping)
  const mealsByDay = {};
  for (const day of days) {
    const dayMeals = meals.filter((m) => {
      if (!m.timestamp) return false;
      // Parse timestamp and get local date string (handles timezone correctly)
      const mealDate = new Date(m.timestamp);
      // Get local date in YYYY-MM-DD format
      const year = mealDate.getFullYear();
      const month = String(mealDate.getMonth() + 1).padStart(2, '0');
      const date = String(mealDate.getDate()).padStart(2, '0');
      const mealDay = `${year}-${month}-${date}`;
      return mealDay === day;
    });
    // Sort chronologically (earliest first)
    dayMeals.sort((a, b) => {
      const timeA = new Date(a.timestamp).getTime();
      const timeB = new Date(b.timestamp).getTime();
      return timeA - timeB;
    });
    mealsByDay[day] = dayMeals;
  }

  const formatDay = (dateStr) => {
    const d = new Date(dateStr + "T12:00:00");
    const today = new Date().toISOString().split("T")[0];
    const yesterday = new Date(Date.now() - 86400000).toISOString().split("T")[0];
    
    if (dateStr === today) return "Today";
    if (dateStr === yesterday) return "Yesterday";
    return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
  };

  const formatTime = (timestamp) => {
    if (!timestamp) return "";
    const d = new Date(timestamp);
    return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 p-4 flex items-center justify-center">
        <p className="text-slate-500">Loading meals...</p>
      </div>
    );
  }

  // Extract macros from USDA nutrition array
  const extractMacros = (nutrition, quantity, unit) => {
    if (!Array.isArray(nutrition) || nutrition.length === 0) {
      return { calories: 0, protein: 0, carbs: 0, fat: 0 };
    }
    
    const macros = { calories: 0, protein: 0, carbs: 0, fat: 0 };
    
    for (const n of nutrition) {
      const name = (n.nutrientName || "").toLowerCase();
      const value = n.value || 0;
      
      if (name.includes("energy") && n.unitName === "KCAL") {
        macros.calories = value;
      } else if (name === "protein") {
        macros.protein = value;
      } else if (name.includes("carbohydrate")) {
        macros.carbs = value;
      } else if (name.includes("total lipid") || name === "fat") {
        macros.fat = value;
      }
    }
    
    // Scale by quantity (USDA values are per 100g, estimate grams from quantity/unit)
    const UNIT_TO_GRAMS = {
      // Weight
      oz: 28.35, g: 1, grams: 1, gram: 1,
      // Volume  
      cup: 150, cups: 150, tbsp: 15, tablespoon: 15, tsp: 5, teaspoon: 5,
      // Count - smaller portions
      piece: 50, pieces: 50, slice: 20, slices: 20, 
      serving: 100, 
      // Eggs
      eggs: 50, egg: 50,
      // Supplements - essentially 0 macros
      pill: 0, pills: 0, capsule: 0, capsules: 0, l: 0,
      // Drinks
      liter: 1000, ml: 1,
    };
    const multiplier = UNIT_TO_GRAMS[(unit || "").toLowerCase()] ?? 80; // default to smaller portion
    const grams = (quantity || 1) * multiplier;
    const scale = grams / 100;
    
    return {
      calories: macros.calories * scale,
      protein: macros.protein * scale,
      carbs: macros.carbs * scale,
      fat: macros.fat * scale,
    };
  };

  // Calculate daily macro totals
  const getDayMacros = (day) => {
    const dayMeals = mealsByDay[day] || [];
    const totals = { calories: 0, protein: 0, carbs: 0, fat: 0 };
    
    for (const meal of dayMeals) {
      const mealIngs = ingredients[meal.id] || [];
      for (const ing of mealIngs) {
        const macros = extractMacros(ing.nutrition, ing.quantity, ing.unit);
        totals.calories += macros.calories || 0;
        totals.protein += macros.protein || 0;
        totals.carbs += macros.carbs || 0;
        totals.fat += macros.fat || 0;
      }
    }
    
    return totals;
  };

  return (
    <div className="min-h-screen bg-slate-50 p-4">
      <h1 className="text-2xl font-bold text-slate-800 mb-4">This Week</h1>
      
      <div className="grid grid-cols-7 gap-2">
        {days.map((day) => {
          const macros = getDayMacros(day);
          const hasMacros = macros.calories > 0;
          
          return (
            <div key={day} className="flex flex-col">
              {/* Day header */}
              <div className="bg-slate-800 text-white px-3 py-2 rounded-t-lg text-center">
                <div className="font-semibold text-sm">{formatDay(day)}</div>
                <div className="text-xs text-slate-300">{day.slice(5)}</div>
              </div>
              
              {/* Daily macro summary */}
              {hasMacros && (
                <div className="bg-slate-700 text-white px-2 py-1.5 text-[10px]">
                  <div className="flex justify-between">
                    <span>🔥 {Math.round(macros.calories)}</span>
                    <span>🥩 {Math.round(macros.protein)}g</span>
                  </div>
                  <div className="flex justify-between text-slate-300">
                    <span>🍞 {Math.round(macros.carbs)}g</span>
                    <span>🧈 {Math.round(macros.fat)}g</span>
                  </div>
                </div>
              )}
              
              {/* Meals for this day */}
              <div className="bg-white rounded-b-lg shadow-sm flex-1 min-h-[400px] p-2 space-y-2">
                {mealsByDay[day].length === 0 ? (
                  <p className="text-slate-300 text-xs text-center py-4">No meals</p>
                ) : (
                  mealsByDay[day].map((meal) => (
                    <MealCard 
                      key={meal.id} 
                      meal={meal} 
                      ingredients={ingredients[meal.id] || []}
                      formatTime={formatTime}
                    />
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const PB_URL = "https://pocketbase-1j2x.onrender.com";

function MealCard({ meal, ingredients, formatTime }) {
  const hasImage = !!meal.image;
  const hasText = !!(meal.text && meal.text.trim());
  const text = hasText ? meal.text : "";
  const truncated = text.length > 50 ? text.slice(0, 50) + "..." : text;
  
  // PocketBase file URL: /api/files/{collectionId}/{recordId}/{filename}
  const imageUrl = hasImage 
    ? `${PB_URL}/api/files/${meal.collectionId}/${meal.id}/${meal.image}?thumb=200x200`
    : null;
  
  return (
    <div className="bg-slate-50 rounded-lg p-2 text-xs border border-slate-100">
      <div className="text-slate-400 text-[10px] mb-1">{formatTime(meal.timestamp)}</div>
      
      {/* Photo thumbnail */}
      {imageUrl && (
        <div className="mb-2">
          <img 
            src={imageUrl} 
            alt="meal" 
            className="w-full h-24 object-cover rounded"
            loading="lazy"
          />
        </div>
      )}
      
      {/* Text description */}
      {truncated && <div className="text-slate-700 font-medium leading-tight">{truncated}</div>}
      
      {ingredients.length > 0 && (
        <div className="mt-2 pt-2 border-t border-slate-200">
          <div className="text-slate-500 space-y-0.5">
            {ingredients.slice(0, 4).map((ing) => {
              // Show quantity more clearly
              const qty = ing.quantity;
              const unit = ing.unit || "";
              let qtyStr = "";
              if (qty && unit && unit !== "serving") {
                qtyStr = `${qty} ${unit}`;
              } else if (qty && qty !== 1) {
                qtyStr = `×${qty}`;
              }
              
              // Infer category from name if not set
              const nameLower = ing.name.toLowerCase();
              const DRINKS = ['coffee', 'tea', 'water', 'milk', 'juice', 'soda', 'latte', 'espresso', 'coke', 'matcha', 'chai', 'smoothie'];
              const SUPPS = ['vitamin', 'supplement', 'd3', 'b12', 'k2', 'flonase', 'elderberry', 'probiotic', 'omega', 'magnesium', 'zinc', 'melatonin', 'threonate', 'ashwagandha', 'creatine', 'collagen', 'fish oil', 'iron', 'calcium', 'biotin'];
              
              let category = ing.category;
              if (!category) {
                if (DRINKS.some(d => nameLower.includes(d))) category = 'drink';
                else if (SUPPS.some(s => nameLower.includes(s))) category = 'supplement';
                else category = 'food';
              }
              
              const emoji = { food: "🟢", drink: "🔵", supplement: "💊", other: "⚪" }[category] || "🟢";
              
              return (
                <div key={ing.id} className="flex items-center gap-1">
                  <span className="text-xs">{emoji}</span>
                  <span className={category === "other" ? "text-slate-400 italic" : ""}>{ing.name}</span>
                  {qtyStr && <span className="text-slate-400">({qtyStr})</span>}
                </div>
              );
            })}
            {ingredients.length > 4 && (
              <div className="text-slate-400">+{ingredients.length - 4} more</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
