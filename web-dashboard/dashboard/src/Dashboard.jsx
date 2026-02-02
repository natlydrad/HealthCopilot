import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchMealsForDateRange, fetchAllIngredients } from "./api";

export default function Dashboard() {
  const navigate = useNavigate();
  const [meals, setMeals] = useState([]);
  const [ingredients, setIngredients] = useState({});
  const [loading, setLoading] = useState(true);
  const [showCalendar, setShowCalendar] = useState(false);
  
  // Load weekOffset from localStorage, default to 0 (current week)
  const [weekOffset, setWeekOffset] = useState(() => {
    const saved = localStorage.getItem('healthcopilot_weekOffset');
    return saved ? parseInt(saved, 10) : 0;
  });
  
  // Save weekOffset to localStorage when it changes
  useEffect(() => {
    localStorage.setItem('healthcopilot_weekOffset', weekOffset.toString());
  }, [weekOffset]);

  // Helper to calculate days for a given week offset
  const getDaysForWeek = (offset) => {
    const result = [];
    for (let i = 6; i >= 0; i--) {
      const d = new Date();
      d.setDate(d.getDate() - i + (offset * 7));
      const year = d.getFullYear();
      const month = String(d.getMonth() + 1).padStart(2, '0');
      const date = String(d.getDate()).padStart(2, '0');
      result.push(`${year}-${month}-${date}`);
    }
    return result;
  };

  // Calculate current week's days
  const days = getDaysForWeek(weekOffset);

  // Fetch meals whenever the week changes
  useEffect(() => {
    async function loadWeek() {
      setLoading(true);
      const weekDays = getDaysForWeek(weekOffset);
      const startDate = weekDays[0];
      const endDate = weekDays[6];
      
      console.log(`🔄 Fetching meals for ${startDate} to ${endDate}...`);
      
      try {
        // Fetch meals for this week and ingredients in parallel
        const [mealItems, allIngredients] = await Promise.all([
          fetchMealsForDateRange(startDate, endDate),
          fetchAllIngredients()
        ]);
        
        console.log(`✅ Got ${mealItems.length} meals`);
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
      } catch (e) {
        console.error("❌ Failed to load:", e);
      } finally {
        setLoading(false);
      }
    }
    loadWeek();
  }, [weekOffset]); // Only re-run when weekOffset changes

  // Get week label
  const getWeekLabel = () => {
    if (weekOffset === 0) return "This Week";
    if (weekOffset === -1) return "Last Week";
    if (weekOffset === 1) return "Next Week";
    // Add T12:00:00 to avoid timezone issues when parsing date strings
    const startDate = new Date(days[0] + "T12:00:00");
    const endDate = new Date(days[6] + "T12:00:00");
    return `${startDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} - ${endDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`;
  };

  // Jump to a specific date
  const jumpToDate = (dateStr) => {
    const targetDate = new Date(dateStr);
    const today = new Date();
    const diffTime = today - targetDate;
    const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
    const newOffset = -Math.floor(diffDays / 7);
    setWeekOffset(newOffset);
    setShowCalendar(false);
  };

  // Helper to parse PocketBase timestamp (has space instead of T)
  const parseTimestamp = (ts) => {
    if (!ts) return null;
    return new Date(ts.replace(' ', 'T'));
  };

  // Group meals by day (convert to local date for proper grouping)
  const mealsByDay = {};
  for (const day of days) {
    const dayMeals = meals.filter((m) => {
      if (!m.timestamp) return false;
      // Parse timestamp and get local date string
      const mealDate = parseTimestamp(m.timestamp);
      if (!mealDate || isNaN(mealDate.getTime())) return false;
      // Get local date in YYYY-MM-DD format
      const year = mealDate.getFullYear();
      const month = String(mealDate.getMonth() + 1).padStart(2, '0');
      const date = String(mealDate.getDate()).padStart(2, '0');
      const mealDay = `${year}-${month}-${date}`;
      return mealDay === day;
    });
    // Sort chronologically (earliest first)
    dayMeals.sort((a, b) => {
      const timeA = parseTimestamp(a.timestamp)?.getTime() || 0;
      const timeB = parseTimestamp(b.timestamp)?.getTime() || 0;
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
    const d = parseTimestamp(timestamp);
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

  // Calculate daily micronutrient totals
  const getDayMicros = (day) => {
    const dayMeals = mealsByDay[day] || [];
    const micros = {};
    
    const UNIT_TO_GRAMS = {
      oz: 28.35, g: 1, grams: 1, gram: 1,
      cup: 150, cups: 150, tbsp: 15, tablespoon: 15, tsp: 5, teaspoon: 5,
      piece: 50, pieces: 50, slice: 20, slices: 20,
      serving: 100, eggs: 50, egg: 50,
      pill: 0, pills: 0, capsule: 0, capsules: 0, l: 0,
      liter: 1000, ml: 1,
    };
    
    const keyNutrients = [
      "Fiber, total dietary", "Calcium, Ca", "Iron, Fe", "Sodium, Na",
      "Potassium, K", "Magnesium, Mg", "Zinc, Zn",
      "Vitamin C", "Thiamin", "Riboflavin", "Niacin", "Vitamin B-6",
      "Folate, total", "Vitamin E (alpha-tocopherol)", "Vitamin K (phylloquinone)"
    ];
    
    for (const meal of dayMeals) {
      const mealIngs = ingredients[meal.id] || [];
      for (const ing of mealIngs) {
        const nutrition = ing.nutrition || [];
        if (!Array.isArray(nutrition)) continue;
        
        const multiplier = UNIT_TO_GRAMS[(ing.unit || "").toLowerCase()] ?? 80;
        const grams = (ing.quantity || 1) * multiplier;
        const scale = grams / 100;
        
        for (const n of nutrition) {
          const name = n.nutrientName || "";
          if (keyNutrients.some(key => name.includes(key))) {
            if (!micros[name]) {
              micros[name] = { value: 0, unit: n.unitName || "" };
            }
            micros[name].value += (n.value || 0) * scale;
          }
        }
      }
    }
    
    return micros;
  };

  // Calculate food group servings
  const getDayFoodGroups = (day) => {
    const dayMeals = mealsByDay[day] || [];
    const groups = {
      vegetables: 0,
      fruits: 0,
      protein: 0,
      grains: 0,
      dairy: 0,
    };
    
    const UNIT_TO_GRAMS = {
      oz: 28.35, g: 1, grams: 1, gram: 1,
      cup: 150, cups: 150, tbsp: 15, tablespoon: 15, tsp: 5, teaspoon: 5,
      piece: 50, pieces: 50, slice: 20, slices: 20,
      serving: 100, eggs: 50, egg: 50,
      pill: 0, pills: 0, capsule: 0, capsules: 0, l: 0,
      liter: 1000, ml: 1,
    };
    
    // Food group keywords
    const VEGETABLES = ['lettuce', 'spinach', 'arugula', 'kale', 'cabbage', 'broccoli', 'carrot', 'tomato', 'cucumber', 'pepper', 'onion', 'garlic', 'celery', 'mushroom', 'zucchini', 'squash', 'eggplant', 'asparagus', 'green bean', 'bean sprout', 'cabbage', 'cauliflower', 'brussels', 'radish', 'turnip', 'beet', 'corn', 'pea', 'bean', 'salsa', 'vegetable'];
    const FRUITS = ['apple', 'apples', 'banana', 'bananas', 'orange', 'oranges', 'berry', 'berries', 'strawberry', 'strawberries', 'blueberry', 'blueberries', 'raspberry', 'raspberries', 'blackberry', 'blackberries', 'grape', 'grapes', 'mango', 'mangoes', 'pineapple', 'pineapples', 'kiwi', 'kiwis', 'peach', 'peaches', 'pear', 'pears', 'plum', 'plums', 'cherry', 'cherries', 'melon', 'melons', 'watermelon', 'watermelons', 'cantaloupe', 'cantaloupes', 'avocado', 'avocados', 'lemon', 'lemons', 'lime', 'limes', 'coconut', 'coconuts'];
    const PROTEIN = ['chicken', 'beef', 'pork', 'turkey', 'lamb', 'fish', 'salmon', 'tuna', 'sardine', 'shrimp', 'crab', 'lobster', 'egg', 'tofu', 'tempeh', 'bean', 'lentil', 'chickpea', 'protein', 'meat', 'sausage', 'bacon', 'ham', 'burger', 'patty', 'wing', 'breast', 'thigh', 'steak', 'rib'];
    const GRAINS = ['bread', 'toast', 'bagel', 'rice', 'pasta', 'noodle', 'quinoa', 'oats', 'oatmeal', 'cereal', 'cracker', 'tortilla', 'wrap', 'pita', 'flour', 'wheat', 'barley', 'rye', 'millet', 'couscous'];
    const DAIRY = ['milk', 'cheese', 'yogurt', 'butter', 'cream', 'sour cream', 'cottage cheese', 'greek yogurt', 'kefir'];
    
    for (const meal of dayMeals) {
      const mealIngs = ingredients[meal.id] || [];
      for (const ing of mealIngs) {
        const name = ing.name.toLowerCase();
        const category = ing.category || 'food';
        
        // Skip supplements and drinks for food groups
        if (category === 'supplement' || category === 'drink') continue;
        
        const qty = ing.quantity || 1;
        const unit = (ing.unit || '').toLowerCase();
        
        // Categorize and count servings
        // Check fruits first (before vegetables, since some might overlap)
        if (FRUITS.some(f => name.includes(f))) {
          // Fruits: 1 cup or 1 medium piece = 1 serving
          if (unit === 'cup' || unit === 'cups') {
            groups.fruits += qty;
          } else if (unit === 'piece' || unit === 'pieces') {
            groups.fruits += qty;
          } else {
            const grams = qty * (UNIT_TO_GRAMS[unit] || 80);
            groups.fruits += grams / 150;
          }
        } else if (VEGETABLES.some(v => name.includes(v))) {
          // Vegetables: 1 cup = 1 serving
          if (unit === 'cup' || unit === 'cups') {
            groups.vegetables += qty;
          } else if (unit === 'piece' || unit === 'pieces') {
            groups.vegetables += qty * 0.5; // rough estimate
          } else {
            const grams = qty * (UNIT_TO_GRAMS[unit] || 80);
            groups.vegetables += grams / 150; // 1 cup ≈ 150g
          }
        } else if (PROTEIN.some(p => name.includes(p))) {
          // Protein: 3-4 oz meat, 1 egg, 0.5 cup beans = 1 serving
          if (unit === 'oz') {
            groups.protein += qty / 3.5; // ~3.5 oz per serving
          } else if (unit === 'egg' || unit === 'eggs') {
            groups.protein += qty;
          } else if (unit === 'cup' || unit === 'cups') {
            groups.protein += qty * 2; // 0.5 cup = 1 serving
          } else {
            const grams = qty * (UNIT_TO_GRAMS[unit] || 80);
            groups.protein += grams / 100; // ~100g per serving
          }
        } else if (GRAINS.some(g => name.includes(g))) {
          // Grains: 1 slice bread, 0.5 cup rice/pasta = 1 serving
          if (unit === 'slice' || unit === 'slices') {
            groups.grains += qty;
          } else if (unit === 'cup' || unit === 'cups') {
            groups.grains += qty * 2; // 0.5 cup = 1 serving
          } else {
            const grams = qty * (UNIT_TO_GRAMS[unit] || 80);
            groups.grains += grams / 40; // ~40g per serving
          }
        } else if (DAIRY.some(d => name.includes(d))) {
          // Dairy: 1 cup milk, 1 oz cheese = 1 serving
          if (unit === 'cup' || unit === 'cups') {
            groups.dairy += qty;
          } else if (unit === 'oz') {
            groups.dairy += qty;
          } else {
            const grams = qty * (UNIT_TO_GRAMS[unit] || 80);
            groups.dairy += grams / 240; // 1 cup ≈ 240g
          }
        }
      }
    }
    
    return groups;
  };

  return (
    <div className="min-h-screen bg-slate-50 p-4">
      {/* Week Navigation Header */}
      <div className="flex items-center justify-between mb-4">
        <button
          onClick={() => setWeekOffset(w => w - 1)}
          className="px-3 py-2 bg-slate-200 rounded-lg hover:bg-slate-300 transition-colors"
        >
          ← Prev
        </button>
        
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-bold text-slate-800">{getWeekLabel()}</h1>
          <button
            onClick={() => setShowCalendar(!showCalendar)}
            className="text-xl hover:scale-110 transition-transform"
            title="Jump to date"
          >
            📅
          </button>
          {weekOffset !== 0 && (
            <button
              onClick={() => setWeekOffset(0)}
              className="text-sm text-blue-500 hover:underline"
            >
              Today
            </button>
          )}
        </div>
        
        <button
          onClick={() => setWeekOffset(w => w + 1)}
          className="px-3 py-2 bg-slate-200 rounded-lg hover:bg-slate-300 transition-colors"
          disabled={weekOffset >= 0}
        >
          Next →
        </button>
      </div>

      {/* Calendar Picker */}
      {showCalendar && (
        <div className="mb-4 p-4 bg-white rounded-xl shadow-lg">
          <div className="flex items-center justify-between mb-2">
            <span className="font-medium">Jump to date:</span>
            <button onClick={() => setShowCalendar(false)} className="text-gray-400 hover:text-gray-600">✕</button>
          </div>
          <input
            type="date"
            className="w-full p-2 border rounded-lg"
            onChange={(e) => jumpToDate(e.target.value)}
            max={new Date().toISOString().split('T')[0]}
          />
          {/* Quick jump buttons */}
          <div className="flex gap-2 mt-2 flex-wrap">
            {[
              { label: "Oct 2025", date: "2025-10-01" },
              { label: "Nov 2025", date: "2025-11-01" },
              { label: "Dec 2025", date: "2025-12-01" },
              { label: "Jan 2026", date: "2026-01-01" },
            ].map(({ label, date }) => (
              <button
                key={date}
                onClick={() => jumpToDate(date)}
                className="px-3 py-1 text-sm bg-slate-100 rounded-full hover:bg-slate-200"
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Loading indicator */}
      {loading && (
        <div className="mb-4">
          <div className="flex items-center justify-center gap-2 text-slate-500 mb-2">
            <div className="animate-spin h-4 w-4 border-2 border-slate-300 border-t-slate-600 rounded-full"></div>
            <span>Loading meals for {days[0]} to {days[6]}...</span>
          </div>
          <div className="h-1 bg-slate-200 rounded-full overflow-hidden">
            <div className="h-full bg-blue-500 rounded-full animate-pulse" style={{width: '60%'}}></div>
          </div>
        </div>
      )}

      {/* No meals message */}
      {!loading && meals.length === 0 && (
        <div className="mb-4 p-4 bg-amber-50 border border-amber-200 rounded-lg text-center">
          <p className="text-amber-700">No meals found for this week</p>
          <p className="text-amber-500 text-sm">Try navigating to a different week</p>
        </div>
      )}
      
      <div className="grid grid-cols-7 gap-2">
        {days.map((day) => {
          const macros = getDayMacros(day);
          const micros = getDayMicros(day);
          const foodGroups = getDayFoodGroups(day);
          const hasMacros = macros.calories > 0;
          const hasMicros = Object.keys(micros).length > 0;
          const hasFoodGroups = Object.values(foodGroups).some(v => v > 0);
          
          return (
            <div key={day} className="flex flex-col">
              {/* Day header - clickable to view details */}
              <div 
                onClick={() => navigate(`/day/${day}`)}
                className="bg-slate-800 text-white px-3 py-2 rounded-t-lg text-center cursor-pointer hover:bg-slate-700 transition-colors"
              >
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
              
              {/* Daily micronutrient summary */}
              {hasMicros && (
                <div className="bg-slate-600 text-white px-2 py-1 text-[9px]">
                  {micros["Fiber, total dietary"] && (
                    <div className="flex justify-between">
                      <span>🌾 Fiber:</span>
                      <span>{Math.round(micros["Fiber, total dietary"].value)}g</span>
                    </div>
                  )}
                  {micros["Calcium, Ca"] && (
                    <div className="flex justify-between">
                      <span>🥛 Ca:</span>
                      <span>{Math.round(micros["Calcium, Ca"].value)}mg</span>
                    </div>
                  )}
                  {micros["Iron, Fe"] && (
                    <div className="flex justify-between">
                      <span>⚙️ Fe:</span>
                      <span>{Math.round(micros["Iron, Fe"].value)}mg</span>
                    </div>
                  )}
                  {micros["Sodium, Na"] && (
                    <div className="flex justify-between">
                      <span>🧂 Na:</span>
                      <span>{Math.round(micros["Sodium, Na"].value)}mg</span>
                    </div>
                  )}
                </div>
              )}
              
              {/* Food group servings */}
              {hasFoodGroups && (
                <div className="bg-slate-500 text-white px-2 py-1 text-[9px]">
                  {foodGroups.vegetables > 0 && (
                    <div className="flex justify-between">
                      <span>🥬 Veg:</span>
                      <span>{foodGroups.vegetables.toFixed(1)}</span>
                    </div>
                  )}
                  {foodGroups.fruits > 0 && (
                    <div className="flex justify-between">
                      <span>🍎 Fruit:</span>
                      <span>{foodGroups.fruits.toFixed(1)}</span>
                    </div>
                  )}
                  {foodGroups.protein > 0 && (
                    <div className="flex justify-between">
                      <span>🥩 Protein:</span>
                      <span>{foodGroups.protein.toFixed(1)}</span>
                    </div>
                  )}
                  {foodGroups.grains > 0 && (
                    <div className="flex justify-between">
                      <span>🌾 Grain:</span>
                      <span>{foodGroups.grains.toFixed(1)}</span>
                    </div>
                  )}
                  {foodGroups.dairy > 0 && (
                    <div className="flex justify-between">
                      <span>🥛 Dairy:</span>
                      <span>{foodGroups.dairy.toFixed(1)}</span>
                    </div>
                  )}
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
  const [expanded, setExpanded] = useState(false);
  const hasImage = !!meal.image;
  const hasText = !!(meal.text && meal.text.trim());
  const text = hasText ? meal.text : "";
  const truncated = text.length > 50 ? text.slice(0, 50) + "..." : text;
  
  // PocketBase file URL: /api/files/{collectionId}/{recordId}/{filename}
  const imageUrl = hasImage 
    ? `${PB_URL}/api/files/${meal.collectionId}/${meal.id}/${meal.image}?thumb=200x200`
    : null;
  
  // Extract macros and micronutrients from ingredients
  const extractNutrients = (ing) => {
    const nutrition = ing.nutrition || [];
    if (!Array.isArray(nutrition) || nutrition.length === 0) return { macros: {}, micros: {} };
    
    const UNIT_TO_GRAMS = {
      oz: 28.35, g: 1, grams: 1, gram: 1,
      cup: 150, cups: 150, tbsp: 15, tablespoon: 15, tsp: 5, teaspoon: 5,
      piece: 50, pieces: 50, slice: 20, slices: 20,
      serving: 100, eggs: 50, egg: 50,
      pill: 0, pills: 0, capsule: 0, capsules: 0, l: 0,
      liter: 1000, ml: 1,
    };
    
    const multiplier = UNIT_TO_GRAMS[(ing.unit || "").toLowerCase()] ?? 80;
    const grams = (ing.quantity || 1) * multiplier;
    const scale = grams / 100;
    
    const macros = { calories: 0, protein: 0, carbs: 0, fat: 0 };
    const micros = {};
    const keyNutrients = [
      "Fiber, total dietary", "Calcium, Ca", "Iron, Fe", "Sodium, Na",
      "Potassium, K", "Magnesium, Mg", "Zinc, Zn",
      "Vitamin C", "Thiamin", "Riboflavin", "Niacin", "Vitamin B-6",
      "Folate, total", "Vitamin E (alpha-tocopherol)", "Vitamin K (phylloquinone)",
      "Vitamin A", "Vitamin D"
    ];
    
    for (const n of nutrition) {
      const name = (n.nutrientName || "").toLowerCase();
      const value = (n.value || 0) * scale;
      const unit = n.unitName || "";
      
      // Extract macros
      if (name.includes("energy") && unit === "KCAL") {
        macros.calories = value;
      } else if (name === "protein") {
        macros.protein = value;
      } else if (name.includes("carbohydrate")) {
        macros.carbs = value;
      } else if (name.includes("total lipid") || name === "fat") {
        macros.fat = value;
      }
      
      // Extract micronutrients
      if (keyNutrients.some(key => n.nutrientName?.includes(key))) {
        micros[n.nutrientName] = { value, unit };
      }
    }
    
    return { macros, micros };
  };
  
  // Calculate total macros and micronutrients for this meal
  const mealMacros = { calories: 0, protein: 0, carbs: 0, fat: 0 };
  const mealMicros = {};
  for (const ing of ingredients) {
    const { macros, micros } = extractNutrients(ing);
    mealMacros.calories += macros.calories || 0;
    mealMacros.protein += macros.protein || 0;
    mealMacros.carbs += macros.carbs || 0;
    mealMacros.fat += macros.fat || 0;
    
    for (const [name, data] of Object.entries(micros)) {
      if (!mealMicros[name]) {
        mealMicros[name] = { value: 0, unit: data.unit };
      }
      mealMicros[name].value += data.value;
    }
  }
  
  const hasNutrients = mealMacros.calories > 0 || Object.keys(mealMicros).length > 0;
  
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
          
          {/* Expandable nutrients (macros + micros) */}
          {hasNutrients && (
            <div className="mt-2">
              <button
                onClick={() => setExpanded(!expanded)}
                className="text-[10px] text-slate-400 hover:text-slate-600 flex items-center gap-1"
              >
                {expanded ? "▼" : "▶"} Nutrients
              </button>
              {expanded && (
                <div className="mt-1 pt-1 border-t border-slate-200 text-[10px] text-slate-500">
                  {/* Macros */}
                  {mealMacros.calories > 0 && (
                    <div className="mb-2">
                      <div className="font-semibold text-slate-600 mb-1">Macros:</div>
                      <div className="grid grid-cols-2 gap-x-2 gap-y-0.5">
                        <div className="flex justify-between">
                          <span>🔥 Calories:</span>
                          <span className="text-slate-600">{Math.round(mealMacros.calories)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span>🥩 Protein:</span>
                          <span className="text-slate-600">{Math.round(mealMacros.protein)}g</span>
                        </div>
                        <div className="flex justify-between">
                          <span>🍞 Carbs:</span>
                          <span className="text-slate-600">{Math.round(mealMacros.carbs)}g</span>
                        </div>
                        <div className="flex justify-between">
                          <span>🧈 Fat:</span>
                          <span className="text-slate-600">{Math.round(mealMacros.fat)}g</span>
                        </div>
                      </div>
                    </div>
                  )}
                  
                  {/* Micronutrients */}
                  {Object.keys(mealMicros).length > 0 && (
                    <div>
                      <div className="font-semibold text-slate-600 mb-1">Micronutrients:</div>
                      <div className="grid grid-cols-2 gap-x-2 gap-y-0.5">
                        {Object.entries(mealMicros).map(([name, data]) => {
                          const shortName = name.replace(/Vitamin |, total|, Ca|, Fe|, Na|, K|, Mg|, Zn| \(alpha-tocopherol\)| \(phylloquinone\)/g, "");
                          const displayValue = data.value < 1 ? data.value.toFixed(2) : Math.round(data.value);
                          return (
                            <div key={name} className="flex justify-between">
                              <span>{shortName}:</span>
                              <span className="text-slate-600">{displayValue} {data.unit}</span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
