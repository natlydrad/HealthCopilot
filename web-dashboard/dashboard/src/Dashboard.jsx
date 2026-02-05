import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { fetchMealsForDateRange, fetchIngredients, createMeal, parseAndSaveMeal } from "./api";
import { computeServingsByFramework } from "./utils/foodFrameworks";

/** Normalize nutrition from ingredient - same as DayDetail: handles nutrition, scaled_nutrition, string */
function getNutritionArray(ing) {
  let raw = ing?.nutrition ?? ing?.scaled_nutrition;
  if (typeof raw === "string") {
    try { raw = JSON.parse(raw); } catch { return []; }
  }
  if (Array.isArray(raw) && raw.length > 0) return raw;
  return [];
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [meals, setMeals] = useState([]);
  const [ingredients, setIngredients] = useState({});
  const [loading, setLoading] = useState(true);
  const [showCalendar, setShowCalendar] = useState(false);
  const [showAddMeal, setShowAddMeal] = useState(false);
  const [addMealText, setAddMealText] = useState("");
  const [addMealTimestamp, setAddMealTimestamp] = useState("");
  const [addingMeal, setAddingMeal] = useState(false);
  const [addMealError, setAddMealError] = useState(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  
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
        // Fetch meals first, then ingredients per meal (avoids bulk fetch + listRule edge cases)
        const mealItems = await fetchMealsForDateRange(startDate, endDate);
        console.log(`✅ Got ${mealItems.length} meals`);
        setMeals(mealItems);

        const ingMap = {};
        if (mealItems.length > 0) {
          const results = await Promise.all(
            mealItems.map((m) =>
              fetchIngredients(m.id).catch((err) => {
                console.warn("Failed ingredients for meal", m.id, err);
                return [];
              })
            )
          );
          mealItems.forEach((m, i) => {
            ingMap[m.id] = results[i] || [];
          });
        }
        setIngredients(ingMap);
      } catch (e) {
        console.error("❌ Failed to load:", e);
      } finally {
        setLoading(false);
      }
    }
    loadWeek();
  }, [weekOffset, refreshTrigger]); // Also re-run when refreshTrigger changes (e.g. after Add Meal)

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

  // Open Add Meal modal with sensible default timestamp (local time, not UTC)
  const openAddMeal = () => {
    const now = new Date();
    let defaultTs;
    if (weekOffset < 0 && days[0]) {
      defaultTs = days[0] + "T12:00";
    } else {
      const y = now.getFullYear();
      const m = String(now.getMonth() + 1).padStart(2, "0");
      const d = String(now.getDate()).padStart(2, "0");
      const h = String(now.getHours()).padStart(2, "0");
      const min = String(now.getMinutes()).padStart(2, "0");
      defaultTs = `${y}-${m}-${d}T${h}:${min}`;
    }
    setAddMealTimestamp(defaultTs);
    setAddMealText("");
    setAddMealError(null);
    setShowAddMeal(true);
  };

  const handleAddMeal = async () => {
    const text = addMealText.trim();
    if (!text) {
      setAddMealError("Describe the meal first.");
      return;
    }
    setAddingMeal(true);
    setAddMealError(null);
    try {
      const newMeal = await createMeal(text, addMealTimestamp || new Date());
      await parseAndSaveMeal(newMeal);
      setShowAddMeal(false);
      setAddMealText("");
      setAddMealTimestamp("");
      setRefreshTrigger((t) => t + 1);
    } catch (err) {
      setAddMealError(err?.message || "Failed to add meal");
    } finally {
      setAddingMeal(false);
    }
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

  // Calculate daily macro totals from actual stored nutrition (same as DayDetail - values are already scaled)
  const getDayMacros = (day) => {
    const dayMeals = mealsByDay[day] || [];
    const totals = { calories: 0, protein: 0, carbs: 0, fat: 0 };
    for (const meal of dayMeals) {
      const mealIngs = ingredients[meal.id] || [];
      for (const ing of mealIngs) {
        const nutritionData = getNutritionArray(ing);
        for (const n of nutritionData) {
          const name = (n.nutrientName || "").toLowerCase();
          const value = parseFloat(n.value) || 0;
          if ((name.includes("energy") && (n.unitName || "").toUpperCase() === "KCAL") || (name === "energy" && !n.unitName)) {
            totals.calories += value;
          } else if (name === "protein") {
            totals.protein += value;
          } else if (name.includes("carbohydrate")) {
            totals.carbs += value;
          } else if (name.includes("total lipid") || name === "fat") {
            totals.fat += value;
          }
        }
      }
    }
    return totals;
  };

  // Calculate daily micronutrient totals from actual stored nutrition (same as DayDetail - values already scaled)
  const getDayMicros = (day) => {
    const dayMeals = mealsByDay[day] || [];
    const micros = {};
    const keyNutrients = [
      "Fiber, total dietary", "Calcium, Ca", "Iron, Fe", "Sodium, Na",
      "Potassium, K", "Magnesium, Mg", "Zinc, Zn",
      "Vitamin C", "Thiamin", "Riboflavin", "Niacin", "Vitamin B-6",
      "Folate, total", "Vitamin E (alpha-tocopherol)", "Vitamin K (phylloquinone)"
    ];
    for (const meal of dayMeals) {
      const mealIngs = ingredients[meal.id] || [];
      for (const ing of mealIngs) {
        const nutritionData = getNutritionArray(ing);
        for (const n of nutritionData) {
          const name = n.nutrientName || "";
          if (keyNutrients.some(key => name.includes(key))) {
            if (!micros[name]) {
              micros[name] = { value: 0, unit: n.unitName || "" };
            }
            micros[name].value += parseFloat(n.value) || 0;
          }
        }
      }
    }
    return micros;
  };

  // Calculate food group servings using same logic as DayDetail (computeServingsByFramework)
  const getDayFoodGroups = (day) => {
    const dayMeals = mealsByDay[day] || [];
    const allIngredients = [];
    for (const meal of dayMeals) {
      allIngredients.push(...(ingredients[meal.id] || []));
    }
    const { myPlate } = computeServingsByFramework(allIngredients);
    return {
      vegetables: myPlate.vegetables ?? 0,
      fruits: myPlate.fruits ?? 0,
      protein: myPlate.protein ?? 0,
      grains: myPlate.grains ?? 0,
      dairy: myPlate.dairy ?? 0,
    };
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
        
        <div className="flex items-center gap-2">
          <button
            onClick={openAddMeal}
            className="px-3 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
          >
            Add Meal
          </button>
          <button
            onClick={() => setWeekOffset(w => w + 1)}
            className="px-3 py-2 bg-slate-200 rounded-lg hover:bg-slate-300 transition-colors"
            disabled={weekOffset >= 0}
          >
            Next →
          </button>
          <Link
            to="/play"
            className="px-3 py-2 text-sm text-slate-600 hover:text-slate-800 rounded-lg hover:bg-slate-100 transition-colors"
          >
            Playground
          </Link>
        </div>
      </div>

      {/* Add Meal Modal */}
      {showAddMeal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-4">
            <div className="flex justify-between items-center mb-3">
              <h2 className="text-lg font-semibold text-slate-800">Add Meal</h2>
              <button
                onClick={() => { setShowAddMeal(false); setAddMealError(null); }}
                className="text-slate-400 hover:text-slate-600"
              >
                ✕
              </button>
            </div>
            <textarea
              value={addMealText}
              onChange={(e) => setAddMealText(e.target.value)}
              placeholder="Describe meal…"
              className="w-full p-3 border border-slate-300 rounded-lg min-h-[100px] resize-y mb-3"
              disabled={addingMeal}
            />
            <div className="mb-3">
              <label className="block text-sm text-slate-600 mb-1">When</label>
              <input
                type="datetime-local"
                value={addMealTimestamp}
                onChange={(e) => setAddMealTimestamp(e.target.value)}
                className="w-full p-2 border border-slate-300 rounded-lg"
                disabled={addingMeal}
              />
            </div>
            {addMealError && (
              <p className="text-red-600 text-sm mb-3">{addMealError}</p>
            )}
            <button
              onClick={handleAddMeal}
              disabled={addingMeal}
              className="w-full py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50"
            >
              {addingMeal ? "Adding…" : "Add Meal"}
            </button>
          </div>
        </div>
      )}

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
  const [showZoom, setShowZoom] = useState(false);
  const [rotation, setRotation] = useState(0);
  const hasImage = !!meal.image;
  const hasText = !!(meal.text && meal.text.trim());
  const text = hasText ? meal.text : "";
  const truncated = text.length > 50 ? text.slice(0, 50) + "..." : text;
  
  // PocketBase file URL: /api/files/{collectionId}/{recordId}/{filename}
  const imageUrl = hasImage 
    ? `${PB_URL}/api/files/${meal.collectionId}/${meal.id}/${meal.image}?thumb=200x200`
    : null;
  const imageUrlFull = hasImage 
    ? `${PB_URL}/api/files/${meal.collectionId}/${meal.id}/${meal.image}`
    : null;
  
  // Sum macros and micros from actual stored nutrition (same as DayDetail - values already scaled)
  const mealMacros = { calories: 0, protein: 0, carbs: 0, fat: 0 };
  const mealMicros = {};
  const keyNutrients = [
    "Fiber, total dietary", "Calcium, Ca", "Iron, Fe", "Sodium, Na",
    "Potassium, K", "Magnesium, Mg", "Zinc, Zn",
    "Vitamin C", "Thiamin", "Riboflavin", "Niacin", "Vitamin B-6",
    "Folate, total", "Vitamin E (alpha-tocopherol)", "Vitamin K (phylloquinone)",
    "Vitamin A", "Vitamin D"
  ];
  for (const ing of ingredients) {
    const nutritionData = getNutritionArray(ing);
    for (const n of nutritionData) {
      const name = (n.nutrientName || "").toLowerCase();
      const value = parseFloat(n.value) || 0;
      if ((name.includes("energy") && (n.unitName || "").toUpperCase() === "KCAL") || (name === "energy" && !n.unitName)) {
        mealMacros.calories += value;
      } else if (name === "protein") {
        mealMacros.protein += value;
      } else if (name.includes("carbohydrate")) {
        mealMacros.carbs += value;
      } else if (name.includes("total lipid") || name === "fat") {
        mealMacros.fat += value;
      }
      if (keyNutrients.some(key => n.nutrientName?.includes(key))) {
        if (!mealMicros[n.nutrientName]) {
          mealMicros[n.nutrientName] = { value: 0, unit: n.unitName || "" };
        }
        mealMicros[n.nutrientName].value += value;
      }
    }
  }
  
  const hasNutrients = mealMacros.calories > 0 || Object.keys(mealMicros).length > 0;
  
  return (
    <div className="bg-slate-50 rounded-lg p-2 text-xs border border-slate-100">
      <div className="text-slate-400 text-[10px] mb-1">{formatTime(meal.timestamp)}</div>
      
      {/* Photo thumbnail — click to zoom and rotate */}
      {imageUrl && (
        <div className="mb-2">
          <button
            type="button"
            onClick={() => { setShowZoom(true); setRotation(0); }}
            className="block w-full rounded focus:outline-none focus:ring-2 focus:ring-purple-400"
          >
            <img 
              src={imageUrl} 
              alt="meal" 
              className="w-full h-24 object-cover rounded hover:opacity-90"
              loading="lazy"
            />
          </button>
          {showZoom && imageUrlFull && (
            <div 
              className="fixed inset-0 z-[100] bg-black/80 flex items-center justify-center p-4"
              onClick={() => setShowZoom(false)}
            >
              <div 
                className="relative max-w-[90vw] max-h-[90vh] flex flex-col items-center"
                onClick={(e) => e.stopPropagation()}
              >
                <img 
                  src={imageUrlFull} 
                  alt="Meal zoomed" 
                  className="max-w-full max-h-[85vh] object-contain rounded-lg shadow-2xl"
                  style={{ transform: `rotate(${rotation}deg)` }}
                />
                <div className="flex gap-2 mt-3">
                  <button
                    type="button"
                    onClick={() => setRotation((r) => (r + 90) % 360)}
                    className="px-4 py-2 bg-white/90 text-gray-800 rounded-lg text-sm font-medium hover:bg-white"
                  >
                    Rotate 90°
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowZoom(false)}
                    className="px-4 py-2 bg-white/90 text-gray-800 rounded-lg text-sm font-medium hover:bg-white"
                  >
                    Close
                  </button>
                </div>
              </div>
            </div>
          )}
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
