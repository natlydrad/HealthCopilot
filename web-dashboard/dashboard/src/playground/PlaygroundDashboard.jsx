import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchMealsForDateRange, fetchIngredients, createMeal, parseAndSaveMeal } from "../api";
import { computeServingsByFramework } from "../utils/foodFrameworks";

function getNutritionArray(ing) {
  let raw = ing?.nutrition ?? ing?.scaled_nutrition;
  if (typeof raw === "string") {
    try { raw = JSON.parse(raw); } catch { return []; }
  }
  if (Array.isArray(raw) && raw.length > 0) return raw;
  return [];
}

function parseTimestamp(ts) {
  if (!ts) return null;
  return new Date(ts.replace(" ", "T"));
}

export default function PlaygroundDashboard() {
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

  const [weekOffset, setWeekOffset] = useState(() => {
    const saved = localStorage.getItem("healthcopilot_weekOffset");
    return saved ? parseInt(saved, 10) : 0;
  });

  useEffect(() => {
    localStorage.setItem("healthcopilot_weekOffset", weekOffset.toString());
  }, [weekOffset]);

  const getDaysForWeek = (offset) => {
    const result = [];
    for (let i = 6; i >= 0; i--) {
      const d = new Date();
      d.setDate(d.getDate() - i + (offset * 7));
      const year = d.getFullYear();
      const month = String(d.getMonth() + 1).padStart(2, "0");
      const date = String(d.getDate()).padStart(2, "0");
      result.push(`${year}-${month}-${date}`);
    }
    return result;
  };

  const days = getDaysForWeek(weekOffset);

  useEffect(() => {
    async function loadWeek() {
      setLoading(true);
      const weekDays = getDaysForWeek(weekOffset);
      const startDate = weekDays[0];
      const endDate = weekDays[6];
      try {
        const mealItems = await fetchMealsForDateRange(startDate, endDate);
        setMeals(mealItems);
        const ingMap = {};
        if (mealItems.length > 0) {
          const results = await Promise.all(
            mealItems.map((m) =>
              fetchIngredients(m.id).catch(() => [])
            )
          );
          mealItems.forEach((m, i) => {
            ingMap[m.id] = results[i] || [];
          });
        }
        setIngredients(ingMap);
      } catch (e) {
        console.error("Failed to load:", e);
      } finally {
        setLoading(false);
      }
    }
    loadWeek();
  }, [weekOffset, refreshTrigger]);

  const getWeekLabel = () => {
    if (weekOffset === 0) return "This Week";
    if (weekOffset === -1) return "Last Week";
    if (weekOffset === 1) return "Next Week";
    const startDate = new Date(days[0] + "T12:00:00");
    const endDate = new Date(days[6] + "T12:00:00");
    return `${startDate.toLocaleDateString("en-US", { month: "short", day: "numeric" })} – ${endDate.toLocaleDateString("en-US", { month: "short", day: "numeric" })}`;
  };

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

  const jumpToDate = (dateStr) => {
    const targetDate = new Date(dateStr);
    const today = new Date();
    const diffTime = today - targetDate;
    const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
    setWeekOffset(-Math.floor(diffDays / 7));
    setShowCalendar(false);
  };

  const mealsByDay = {};
  for (const day of days) {
    const dayMeals = meals.filter((m) => {
      const mealDate = parseTimestamp(m.timestamp);
      if (!mealDate || isNaN(mealDate.getTime())) return false;
      const year = mealDate.getFullYear();
      const month = String(mealDate.getMonth() + 1).padStart(2, "0");
      const date = String(mealDate.getDate()).padStart(2, "0");
      return `${year}-${month}-${date}` === day;
    });
    dayMeals.sort((a, b) => (parseTimestamp(a.timestamp)?.getTime() || 0) - (parseTimestamp(b.timestamp)?.getTime() || 0));
    mealsByDay[day] = dayMeals;
  }

  const getDayMacros = (day) => {
    const dayMeals = mealsByDay[day] || [];
    const totals = { calories: 0, protein: 0, carbs: 0, fat: 0 };
    for (const meal of dayMeals) {
      for (const ing of ingredients[meal.id] || []) {
        const nutritionData = getNutritionArray(ing);
        for (const n of nutritionData) {
          const name = (n.nutrientName || "").toLowerCase();
          const value = parseFloat(n.value) || 0;
          if ((name.includes("energy") && (n.unitName || "").toUpperCase() === "KCAL") || (name === "energy" && !n.unitName)) {
            totals.calories += value;
          } else if (name === "protein") totals.protein += value;
          else if (name.includes("carbohydrate")) totals.carbs += value;
          else if (name.includes("total lipid") || name === "fat") totals.fat += value;
        }
      }
    }
    return totals;
  };

  const getDayFoodGroups = (day) => {
    const dayMeals = mealsByDay[day] || [];
    const allIngredients = [];
    for (const meal of dayMeals) allIngredients.push(...(ingredients[meal.id] || []));
    const { myPlate } = computeServingsByFramework(allIngredients);
    return {
      vegetables: myPlate.vegetables ?? 0,
      fruits: myPlate.fruits ?? 0,
      protein: myPlate.protein ?? 0,
      grains: myPlate.grains ?? 0,
      dairy: myPlate.dairy ?? 0,
    };
  };

  const formatDay = (dateStr) => {
    const d = new Date(dateStr + "T12:00:00");
    const today = new Date().toISOString().split("T")[0];
    const yesterday = new Date(Date.now() - 86400000).toISOString().split("T")[0];
    if (dateStr === today) return "Today";
    if (dateStr === yesterday) return "Yesterday";
    return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
  };

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <p className="text-amber-700/80">Loading meals…</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold text-stone-700">{getWeekLabel()}</h1>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setWeekOffset((w) => w - 1)}
            className="rounded-2xl bg-amber-100 px-4 py-2 text-sm font-medium text-amber-900 transition hover:bg-amber-200"
          >
            ← Prev
          </button>
          {weekOffset !== 0 && (
            <button
              type="button"
              onClick={() => setWeekOffset(0)}
              className="rounded-2xl bg-amber-100 px-3 py-2 text-sm font-medium text-amber-900 transition hover:bg-amber-200"
            >
              Today
            </button>
          )}
          <button
            type="button"
            onClick={() => setShowCalendar(!showCalendar)}
            className="rounded-2xl bg-amber-100 px-3 py-2 text-sm font-medium text-amber-900 transition hover:bg-amber-200"
            title="Jump to date"
          >
            📅
          </button>
          <button
            type="button"
            onClick={openAddMeal}
            className="rounded-2xl bg-emerald-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-emerald-600"
          >
            Add Meal
          </button>
          <button
            type="button"
            onClick={() => setWeekOffset((w) => w + 1)}
            disabled={weekOffset >= 0}
            className="rounded-2xl bg-amber-100 px-4 py-2 text-sm font-medium text-amber-900 transition hover:bg-amber-200 disabled:opacity-50 disabled:hover:bg-amber-100"
          >
            Next →
          </button>
        </div>
      </div>

      {showAddMeal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-3xl bg-white p-6 shadow-xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-stone-800">Add Meal</h2>
              <button
                type="button"
                onClick={() => { setShowAddMeal(false); setAddMealError(null); }}
                className="text-stone-400 hover:text-stone-600"
              >
                ✕
              </button>
            </div>
            <textarea
              value={addMealText}
              onChange={(e) => setAddMealText(e.target.value)}
              placeholder="Describe your meal…"
              className="mb-3 min-h-[100px] w-full resize-y rounded-2xl border border-amber-200/80 p-3 focus:border-amber-400 focus:outline-none"
              disabled={addingMeal}
            />
            <label className="mb-1 block text-sm text-stone-600">When</label>
            <input
              type="datetime-local"
              value={addMealTimestamp}
              onChange={(e) => setAddMealTimestamp(e.target.value)}
              className="mb-4 w-full rounded-2xl border border-amber-200/80 p-2 focus:border-amber-400 focus:outline-none"
              disabled={addingMeal}
            />
            {addMealError && <p className="mb-3 text-sm text-red-600">{addMealError}</p>}
            <button
              type="button"
              onClick={handleAddMeal}
              disabled={addingMeal}
              className="w-full rounded-2xl bg-emerald-500 py-2.5 font-medium text-white transition hover:bg-emerald-600 disabled:opacity-50"
            >
              {addingMeal ? "Adding…" : "Add Meal"}
            </button>
          </div>
        </div>
      )}

      {showCalendar && (
        <div className="rounded-3xl border border-amber-200/60 bg-white p-4 shadow-sm">
          <div className="mb-2 flex items-center justify-between">
            <span className="font-medium text-stone-700">Jump to date</span>
            <button type="button" onClick={() => setShowCalendar(false)} className="text-stone-400 hover:text-stone-600">✕</button>
          </div>
          <input
            type="date"
            className="mb-2 w-full rounded-2xl border border-amber-200/80 p-2"
            onChange={(e) => jumpToDate(e.target.value)}
            max={new Date().toISOString().split("T")[0]}
          />
          <div className="flex flex-wrap gap-2">
            {["2025-10-01", "2025-11-01", "2025-12-01", "2026-01-01"].map((date) => (
              <button
                key={date}
                type="button"
                onClick={() => jumpToDate(date)}
                className="rounded-full bg-amber-100 px-3 py-1 text-sm text-amber-900 hover:bg-amber-200"
              >
                {new Date(date + "T12:00:00").toLocaleDateString("en-US", { month: "short", year: "numeric" })}
              </button>
            ))}
          </div>
        </div>
      )}

      {!loading && meals.length === 0 && (
        <div className="rounded-3xl border border-amber-200/60 bg-amber-50/80 p-6 text-center">
          <p className="text-amber-800">No meals this week</p>
          <p className="mt-1 text-sm text-amber-700">Try another week or add a meal!</p>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-7">
        {days.map((day) => {
          const macros = getDayMacros(day);
          const foodGroups = getDayFoodGroups(day);
          const dayMeals = mealsByDay[day] || [];
          const hasData = macros.calories > 0 || dayMeals.length > 0;

          return (
            <button
              key={day}
              type="button"
              onClick={() => navigate(`/play/day/${day}`)}
              className="flex flex-col rounded-3xl border border-amber-200/60 bg-white p-4 text-left shadow-sm transition hover:border-amber-300 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-amber-300"
            >
              <div className="mb-2 font-semibold text-stone-800">{formatDay(day)}</div>
              <div className="mb-2 text-xs text-stone-500">{day}</div>
              {hasData ? (
                <>
                  <div className="mb-1 text-sm text-stone-600">
                    🔥 {Math.round(macros.calories)} cal · 🥩 {Math.round(macros.protein)}g P
                  </div>
                  <div className="text-xs text-stone-500">
                    🥬 {foodGroups.vegetables.toFixed(1)} 🍎 {foodGroups.fruits.toFixed(1)} 🥩 {foodGroups.protein.toFixed(1)} 🌾 {foodGroups.grains.toFixed(1)} 🥛 {foodGroups.dairy.toFixed(1)}
                  </div>
                  <div className="mt-2 text-xs text-amber-700">{dayMeals.length} meal{dayMeals.length !== 1 ? "s" : ""}</div>
                </>
              ) : (
                <p className="text-sm text-stone-400">No meals</p>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
