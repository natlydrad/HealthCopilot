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

  // Get last 7 days
  const days = [];
  for (let i = 6; i >= 0; i--) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    days.push(d.toISOString().split("T")[0]);
  }

  // Group meals by day (handle both "T" and space separator in timestamps)
  const mealsByDay = {};
  for (const day of days) {
    mealsByDay[day] = meals.filter((m) => {
      if (!m.timestamp) return false;
      // Handle both ISO format (T separator) and space separator
      const mealDay = m.timestamp.split(/[T ]/)[0];
      return mealDay === day;
    });
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

  return (
    <div className="min-h-screen bg-slate-50 p-4">
      <h1 className="text-2xl font-bold text-slate-800 mb-4">This Week</h1>
      
      <div className="grid grid-cols-7 gap-2">
        {days.map((day) => (
          <div key={day} className="flex flex-col">
            {/* Day header */}
            <div className="bg-slate-800 text-white px-3 py-2 rounded-t-lg text-center">
              <div className="font-semibold text-sm">{formatDay(day)}</div>
              <div className="text-xs text-slate-300">{day.slice(5)}</div>
            </div>
            
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
        ))}
      </div>
    </div>
  );
}

function MealCard({ meal, ingredients, formatTime }) {
  const text = meal.text || "(no description)";
  const truncated = text.length > 60 ? text.slice(0, 60) + "..." : text;
  
  return (
    <div className="bg-slate-50 rounded-lg p-2 text-xs border border-slate-100">
      <div className="text-slate-400 text-[10px] mb-1">{formatTime(meal.timestamp)}</div>
      <div className="text-slate-700 font-medium leading-tight">{truncated}</div>
      
      {ingredients.length > 0 && (
        <div className="mt-2 pt-2 border-t border-slate-200">
          <div className="text-slate-500 space-y-0.5">
            {ingredients.slice(0, 4).map((ing) => {
              const qty = ing.quantity;
              const unit = ing.unit && ing.unit !== "serving" ? ing.unit : "";
              const qtyStr = qty && qty !== 1 ? `${qty}${unit ? " " + unit : ""}` : "";
              return (
                <div key={ing.id} className="flex items-center gap-1">
                  <span className="text-green-500">•</span>
                  <span>{ing.name}</span>
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
