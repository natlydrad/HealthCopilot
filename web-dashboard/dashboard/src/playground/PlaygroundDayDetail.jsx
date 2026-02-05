import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { fetchMealsForDateRange, fetchIngredients } from "../api";
import { computeServingsByFramework, MYPLATE_TARGETS, MATCHED_TO_EMOJI } from "../utils/foodFrameworks";

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

export default function PlaygroundDayDetail() {
  const { date } = useParams();
  const navigate = useNavigate();
  const [meals, setMeals] = useState([]);
  const [ingredients, setIngredients] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!date) return;
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const mealItems = await fetchMealsForDateRange(date, date);
        if (cancelled) return;
        setMeals(mealItems);
        const ingMap = {};
        for (const m of mealItems) {
          const ings = await fetchIngredients(m.id).catch(() => []);
          if (cancelled) return;
          ingMap[m.id] = ings;
        }
        setIngredients(ingMap);
      } catch (e) {
        if (!cancelled) console.error("Failed to load day:", e);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [date]);

  const allIngredients = [];
  for (const meal of meals) {
    allIngredients.push(...(ingredients[meal.id] || []));
  }

  const { myPlate } = computeServingsByFramework(allIngredients);
  const dayMacros = { calories: 0, protein: 0, carbs: 0, fat: 0 };
  for (const ing of allIngredients) {
    const nutritionData = getNutritionArray(ing);
    for (const n of nutritionData) {
      const name = (n.nutrientName || "").toLowerCase();
      const value = parseFloat(n.value) || 0;
      if ((name.includes("energy") && (n.unitName || "").toUpperCase() === "KCAL") || (name === "energy" && !n.unitName)) {
        dayMacros.calories += value;
      } else if (name === "protein") dayMacros.protein += value;
      else if (name.includes("carbohydrate")) dayMacros.carbs += value;
      else if (name.includes("total lipid") || name === "fat") dayMacros.fat += value;
    }
  }

  const formatTime = (ts) => {
    const d = parseTimestamp(ts);
    return d ? d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }) : "";
  };

  const formatDayLabel = () => {
    if (!date) return "";
    const d = new Date(date + "T12:00:00");
    const today = new Date().toISOString().split("T")[0];
    if (date === today) return "Today";
    return d.toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" });
  };

  if (!date) {
    return (
      <div className="rounded-3xl border border-amber-200/60 bg-white p-6 text-center">
        <p className="text-stone-500">No date selected.</p>
        <button
          type="button"
          onClick={() => navigate("/play")}
          className="mt-4 rounded-2xl bg-amber-100 px-4 py-2 text-sm font-medium text-amber-900 hover:bg-amber-200"
        >
          Back to week
        </button>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <p className="text-amber-700/80">Loading day…</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <button
            type="button"
            onClick={() => navigate("/play")}
            className="mb-2 text-sm font-medium text-amber-700 hover:text-amber-800"
          >
            ← Back to week
          </button>
          <h1 className="text-2xl font-semibold text-stone-800">{formatDayLabel()}</h1>
          <p className="text-sm text-stone-500">{date}</p>
        </div>
        <a
          href={`/day/${date}`}
          className="rounded-2xl bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-200"
        >
          Edit on main dashboard →
        </a>
      </div>

      <div className="rounded-3xl border border-amber-200/60 bg-white p-6 shadow-sm">
        <h2 className="mb-4 text-lg font-semibold text-stone-700">Totals</h2>
        <div className="flex flex-wrap gap-4 text-sm">
          <span className="text-stone-600">🔥 {Math.round(dayMacros.calories)} cal</span>
          <span className="text-stone-600">🥩 {Math.round(dayMacros.protein)}g protein</span>
          <span className="text-stone-600">🍞 {Math.round(dayMacros.carbs)}g carbs</span>
          <span className="text-stone-600">🧈 {Math.round(dayMacros.fat)}g fat</span>
        </div>
        <div className="mt-4 flex flex-wrap gap-2 text-xs text-stone-500">
          {Object.entries(MYPLATE_TARGETS).filter(([, v]) => v > 0).map(([key]) => (
            <span key={key}>
              {MATCHED_TO_EMOJI[key] || "•"} {key}: {(myPlate[key] ?? 0).toFixed(1)}
            </span>
          ))}
        </div>
      </div>

      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-stone-700">Meals</h2>
        {meals.length === 0 ? (
          <p className="rounded-3xl border border-amber-200/60 bg-amber-50/80 p-6 text-center text-amber-800">No meals this day.</p>
        ) : (
          meals
            .sort((a, b) => (parseTimestamp(a.timestamp)?.getTime() || 0) - (parseTimestamp(b.timestamp)?.getTime() || 0))
            .map((meal) => (
              <div
                key={meal.id}
                className="rounded-3xl border border-amber-200/60 bg-white p-4 shadow-sm"
              >
                <div className="mb-2 text-sm text-stone-500">{formatTime(meal.timestamp)}</div>
                {meal.text && (
                  <p className="mb-3 text-stone-700">{meal.text}</p>
                )}
                <ul className="space-y-1 text-sm text-stone-600">
                  {(ingredients[meal.id] || []).map((ing) => (
                    <li key={ing.id}>
                      {ing.name}
                      {ing.quantity != null && ing.unit ? ` (${ing.quantity} ${ing.unit})` : ""}
                    </li>
                  ))}
                </ul>
              </div>
            ))
        )}
      </div>
    </div>
  );
}
