import { useEffect, useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { fetchMealsForDateRange, fetchIngredients, fetchHasNonFoodLogs, correctIngredient, updateIngredientWithNutrition, getLearnedPatterns, getLearningStats, removeLearnedPattern, parseAndSaveMeal, clearMealIngredients, clearNonFoodClassification, sendCorrectionMessage, previewCorrection, saveCorrection, reparseIngredientFromText, getParseApiUrl, deleteIngredient, addIngredients, updateIngredientPortion } from "./api";
import { computeServingsByFramework, MYPLATE_TARGETS, DAILY_DOZEN_TARGETS, LONGEVITY_TARGETS, MATCHED_TO_EMOJI } from "./utils/foodFrameworks";
import * as flowLog from "./utils/flowLog";

/** Normalize nutrition from ingredient - handles string, object, scaled_nutrition fallback */
function getNutritionArray(ing) {
  let raw = ing?.nutrition ?? ing?.scaled_nutrition;
  if (typeof raw === "string") {
    try { raw = JSON.parse(raw); } catch { return []; }
  }
  if (Array.isArray(raw) && raw.length > 0) return raw;
  return [];
}

// Format nutrition array for display (cal, protein, carbs, fat)
function formatNutritionSummary(nutrition) {
  if (!Array.isArray(nutrition) || nutrition.length === 0) return "";
  const getVal = (name) => {
    const n = nutrition.find((x) =>
      (x.nutrientName || "").toLowerCase().includes(name.toLowerCase())
    );
    return n?.value != null ? Math.round(n.value) : null;
  };
  const cal = getVal("energy") ?? getVal("Energy");
  const protein = getVal("protein");
  const carbs = getVal("carbohydrate") ?? getVal("Carbohydrate");
  const fat = getVal("lipid") ?? getVal("fat") ?? getVal("Total lipid");
  const parts = [];
  if (cal != null) parts.push(`${cal} cal`);
  if (protein != null) parts.push(`${protein}g protein`);
  if (carbs != null) parts.push(`${carbs}g carbs`);
  if (fat != null) parts.push(`${fat}g fat`);
  return parts.length ? parts.join(", ") : "";
}

// Vague names that should always be treated as low-confidence
const VAGUE_NAME_PATTERNS = /pizza toppings|salad stuff|sandwich fillings|leftover food|toppings\b|leftover(s)?\b|generic salad|stuff\b|fillings\b/i;

function FrameworkProgress({ title, data, targets, units, labels }) {
  const entries = Object.keys(targets).filter((k) => targets[k] > 0);
  if (entries.length === 0) return null;
  return (
    <div className="bg-slate-800 rounded-lg p-3">
      <div className="text-sm font-semibold text-slate-100 mb-3">{title}</div>
      <div className="space-y-3">
        {entries.map((key) => {
          const val = data[key] ?? 0;
          const target = Math.max(1, Math.round(targets[key]));
          const overflow = Math.max(0, val - target);
          const overflowCount = Math.min(Math.ceil(overflow), Math.max(0, 8 - target));
          const numCircles = Math.min(target + overflowCount, 8);
          const unitStr = units && units[key] ? units[key] : "sv";
          const label = labels && labels[key] ? labels[key] : key;
          return (
            <div key={key} className="flex items-center gap-2">
              <span className="text-sm text-slate-100 w-32 shrink-0">{label}</span>
              <div className="flex gap-1 items-center">
                {Array.from({ length: numCircles }, (_, i) => {
                  if (i < target) {
                    const fill = i < Math.floor(val) ? 1 : i < val ? val - Math.floor(val) : 0;
                    return (
                      <div
                        key={i}
                        className="w-5 h-5 rounded-full flex-shrink-0 border-2 border-emerald-400/70 overflow-hidden"
                        style={{
                          background: fill >= 1 ? "rgb(16 185 129)" : fill > 0 ? `conic-gradient(rgb(16 185 129) ${fill * 360}deg, transparent ${fill * 360}deg)` : "transparent",
                        }}
                        title={`${val.toFixed(1)} / ${targets[key]} ${unitStr}`}
                      />
                    );
                  }
                  const j = i - target;
                  const overflowFill = j < Math.floor(overflow) ? 1 : j < overflow ? overflow - Math.floor(overflow) : 0;
                  return (
                    <div
                      key={i}
                      className="w-5 h-5 rounded-full flex-shrink-0 border-2 border-slate-500 overflow-hidden"
                      style={{
                        background: overflowFill >= 1 ? "rgb(100 116 139)" : overflowFill > 0 ? `conic-gradient(rgb(100 116 139) ${overflowFill * 360}deg, transparent ${overflowFill * 360}deg)` : "transparent",
                      }}
                      title={`${val.toFixed(1)} / ${targets[key]} ${unitStr} (overflow)`}
                    />
                  );
                })}
              </div>
              <span className="text-sm text-slate-200 w-16 text-right shrink-0">
                {val.toFixed(1)}/{targets[key]}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function formatContrib(obj) {
  const parts = [];
  for (const [k, v] of Object.entries(obj)) {
    if (v > 0) parts.push(`${k} +${v.toFixed(1)}`);
  }
  return parts.length ? parts.join(", ") : "—";
}

function IngredientBreakdown({ byIngredient, unmatched }) {
  const contributed = byIngredient.filter((i) => i.contributed);
  return (
    <div className="border-t border-slate-600 pt-3 space-y-3">
      <div className="text-sm font-semibold text-slate-100">How each ingredient was categorized</div>
      <div className="space-y-1.5 text-sm">
        {contributed.map((item, idx) => (
          <div key={idx} className="py-1 border-b border-slate-700/50 last:border-0">
            <div className="flex items-baseline gap-2">
              <span className="font-medium text-slate-100">{item.name}</span>
              <span className="text-slate-400 text-xs">({item.quantity} {item.unit})</span>
              <span className="text-emerald-400 text-xs">→ {item.matched}</span>
            </div>
            <div className="text-xs text-slate-500 mt-0.5 pl-1">
              MyPlate: {formatContrib(item.myPlate)} · Dozen: {formatContrib(item.dailyDozen)} · Longevity: {formatContrib(item.longevity)}
            </div>
          </div>
        ))}
      </div>
      {unmatched.length > 0 && (
        <div>
          <div className="text-sm font-semibold text-amber-300 mb-1">Did not contribute to any category</div>
          <div className="text-sm text-slate-400">
            {unmatched.map((item, idx) => (
              <div key={idx}>
                {item.name} ({item.quantity} {item.unit})
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// Determine if an ingredient is low confidence (needs review)
function isLowConfidence(ing) {
  const name = (ing.name || "").trim();
  // Vague name heuristic: treat known vague terms as low-confidence
  if (VAGUE_NAME_PATTERNS.test(name)) return true;
  // No USDA match = GPT guessed it
  if (!ing.usdaCode) return true;
  // Source is explicitly GPT without USDA validation
  if (ing.source === "gpt" && getNutritionArray(ing).length === 0) return true;
  return false;
}

export default function DayDetail() {
  const { date } = useParams();
  const navigate = useNavigate();
  const [meals, setMeals] = useState([]);
  const [totals, setTotals] = useState({ macros: { calories: 0, protein: 0, carbs: 0, fat: 0 }, micros: {}, foodGroups: { vegetables: 0, fruits: 0, protein: 0, grains: 0, dairy: 0 }, frameworks: null });
  const [showLearning, setShowLearning] = useState(false);
  const [showFrameworkCompare, setShowFrameworkCompare] = useState(false);
  const [totalsRefreshTrigger, setTotalsRefreshTrigger] = useState(0);

  const refreshTotals = () => setTotalsRefreshTrigger((t) => t + 1);

  useEffect(() => {
    async function load() {
      const dayMeals = await fetchMealsForDateRange(date, date);
      const parseTimestamp = (ts) => {
        if (!ts) return 0;
        return new Date(ts.replace(' ', 'T')).getTime() || 0;
      };
      const sortedMeals = [...dayMeals].sort((a, b) => parseTimestamp(a.timestamp) - parseTimestamp(b.timestamp));
      console.log(`📅 ${date}: ${sortedMeals.length} meals loaded`);
      setMeals(sortedMeals);

      const macros = { calories: 0, protein: 0, carbs: 0, fat: 0 };
      const micros = {};
      const foodGroups = { vegetables: 0, fruits: 0, protein: 0, grains: 0, dairy: 0 };
      const allIngredients = [];

      const UNIT_TO_GRAMS = { oz: 28.35, g: 1, grams: 1, gram: 1, cup: 150, cups: 150, tbsp: 15, tablespoon: 15, tsp: 5, teaspoon: 5, piece: 50, pieces: 50, slice: 20, slices: 20, serving: 100, eggs: 50, egg: 50, pill: 0, pills: 0, capsule: 0, capsules: 0, l: 0, liter: 1000, ml: 1 };
      const VEGETABLES = ['lettuce', 'spinach', 'arugula', 'kale', 'cabbage', 'broccoli', 'carrot', 'tomato', 'cucumber', 'pepper', 'onion', 'garlic', 'celery', 'mushroom', 'zucchini', 'squash', 'eggplant', 'asparagus', 'green bean', 'bean sprout', 'cauliflower', 'brussels', 'radish', 'turnip', 'beet', 'corn', 'pea', 'bean', 'salsa', 'vegetable'];
      const FRUITS = ['apple', 'apples', 'banana', 'bananas', 'orange', 'oranges', 'berry', 'berries', 'strawberry', 'strawberries', 'blueberry', 'blueberries', 'raspberry', 'raspberries', 'blackberry', 'blackberries', 'grape', 'grapes', 'mango', 'mangoes', 'pineapple', 'pineapples', 'kiwi', 'kiwis', 'peach', 'peaches', 'pear', 'pears', 'plum', 'plums', 'cherry', 'cherries', 'melon', 'melons', 'watermelon', 'watermelons', 'cantaloupe', 'cantaloupes', 'avocado', 'avocados', 'lemon', 'lemons', 'lime', 'limes', 'coconut', 'coconuts'];
      const PROTEIN = ['chicken', 'beef', 'pork', 'turkey', 'lamb', 'fish', 'salmon', 'tuna', 'sardine', 'shrimp', 'crab', 'lobster', 'egg', 'tofu', 'tempeh', 'bean', 'lentil', 'chickpea', 'protein', 'meat', 'sausage', 'bacon', 'ham', 'burger', 'patty', 'wing', 'breast', 'thigh', 'steak', 'rib'];
      const GRAINS = ['bread', 'toast', 'bagel', 'rice', 'pasta', 'noodle', 'quinoa', 'oats', 'oatmeal', 'cereal', 'cracker', 'tortilla', 'wrap', 'pita', 'flour', 'wheat', 'barley', 'rye', 'millet', 'couscous', 'focaccia', 'pizza', 'crust', 'flatbread', 'naan', 'ciabatta', 'bun', 'roll', 'muffin'];
      const DAIRY = ['milk', 'cheese', 'yogurt', 'butter', 'cream', 'sour cream', 'cottage cheese', 'greek yogurt', 'kefir'];

      const addFromKeywords = (ing, name, qty, unit) => {
        if (FRUITS.some(f => name.includes(f))) {
          if (unit === 'cup' || unit === 'cups') foodGroups.fruits += qty;
          else if (unit === 'piece' || unit === 'pieces') foodGroups.fruits += qty;
          else foodGroups.fruits += (qty * (UNIT_TO_GRAMS[unit] || 80)) / 150;
        } else if (VEGETABLES.some(v => name.includes(v))) {
          if (unit === 'cup' || unit === 'cups') foodGroups.vegetables += qty;
          else if (unit === 'piece' || unit === 'pieces') foodGroups.vegetables += qty * 0.5;
          else foodGroups.vegetables += (qty * (UNIT_TO_GRAMS[unit] || 80)) / 150;
        } else if (PROTEIN.some(p => name.includes(p))) {
          if (unit === 'oz') foodGroups.protein += qty / 3.5;
          else if (unit === 'egg' || unit === 'eggs') foodGroups.protein += qty;
          else if (unit === 'cup' || unit === 'cups') foodGroups.protein += qty * 2;
          else foodGroups.protein += (qty * (UNIT_TO_GRAMS[unit] || 80)) / 100;
        } else if (GRAINS.some(g => name.includes(g))) {
          if (unit === 'slice' || unit === 'slices') foodGroups.grains += qty;
          else if (unit === 'piece' || unit === 'pieces') foodGroups.grains += qty; // 1 piece focaccia/bread ≈ 1 serving
          else if (unit === 'cup' || unit === 'cups') foodGroups.grains += qty * 2; // ½ cup cooked = 1 serving
          else foodGroups.grains += (qty * (UNIT_TO_GRAMS[unit] || 80)) / 28; // 28g ≈ 1 oz-equivalent
        } else if (DAIRY.some(d => name.includes(d))) {
          if (unit === 'cup' || unit === 'cups') foodGroups.dairy += qty;
          else if (unit === 'oz') foodGroups.dairy += qty;
          else foodGroups.dairy += (qty * (UNIT_TO_GRAMS[unit] || 80)) / 240;
        }
      };

      for (const meal of dayMeals) {
        const ingredients = await fetchIngredients(meal.id);
        for (const ing of ingredients) {
          allIngredients.push(ing);
          const category = ing.category || 'food';
          if (category === 'supplement' || category === 'drink') { /* skip for food groups */ }

          const fg = ing.parsingMetadata?.foodGroupServings;
          if (fg && typeof fg === 'object' && category !== 'supplement' && category !== 'drink') {
            foodGroups.vegetables += Number(fg.vegetables) || 0;
            foodGroups.fruits += Number(fg.fruits) || 0;
            foodGroups.protein += Number(fg.protein) || 0;
            foodGroups.grains += Number(fg.grains) || 0;
            foodGroups.dairy += Number(fg.dairy) || 0;
          } else if (category !== 'supplement' && category !== 'drink') {
            const name = (ing.name || '').toLowerCase();
            const qty = ing.quantity || 1;
            const unit = (ing.unit || '').toLowerCase();
            addFromKeywords(ing, name, qty, unit);
          }

          const nutritionData = getNutritionArray(ing);
          if (nutritionData.length === 0) continue;
          for (const n of nutritionData) {
            const name = (n.nutrientName || "").toLowerCase();
            const value = parseFloat(n.value) || 0;
            const key = n.nutrientName;
            if ((name.includes("energy") && (n.unitName || "").toUpperCase() === "KCAL") || (name === "energy" && !n.unitName)) {
              macros.calories += value;
            } else if (name === "protein") {
              macros.protein += value;
            } else if (name.includes("carbohydrate")) {
              macros.carbs += value;
            } else if (name.includes("total lipid") || name === "fat") {
              macros.fat += value;
            } else if (key && (name.includes("fiber") || (name.includes("sugars") && name.includes("added")) || name.includes("sodium") || name.includes("caffeine"))) {
              if (!micros[key]) micros[key] = { value: 0, unit: n.unitName || "" };
              micros[key].value += value;
            }
          }
        }
      }
      const frameworks = computeServingsByFramework(allIngredients);
      setTotals({ macros, micros, foodGroups, frameworks });
    }
    load();
  }, [date, totalsRefreshTrigger]);

  return (
    <div className="p-8 bg-gray-50 min-h-screen">
      <div className="flex items-center justify-between mb-4">
        <button
          onClick={() => navigate(-1)}
          className="text-blue-500 underline"
        >
          ← Back
        </button>
        <button
          onClick={() => setShowLearning(true)}
          className="text-sm bg-purple-100 text-purple-700 px-3 py-1 rounded-full hover:bg-purple-200"
        >
          🧠 What I've Learned
        </button>
      </div>
      
      <h1 className="text-2xl font-bold mb-4">{date}</h1>

      <div className="bg-white rounded-xl shadow mb-6 overflow-hidden">
        <div className="bg-slate-800 text-white px-4 py-3">
          <div className="text-sm font-semibold text-slate-300 mb-2">Daily totals</div>
          <div className="flex flex-wrap gap-4 items-center">
            <span>🔥 {Math.round(totals.macros.calories)} cal</span>
            <span>🥩 {Math.round(totals.macros.protein)}g protein</span>
            <span>🍞 {Math.round(totals.macros.carbs)}g carbs</span>
            <span>🧈 {Math.round(totals.macros.fat)}g fat</span>
            {totals.macros.calories > 0 && (() => {
              const pCal = totals.macros.protein * 4;
              const cCal = totals.macros.carbs * 4;
              const fCal = totals.macros.fat * 9;
              const total = pCal + cCal + fCal;
              if (total <= 0) return null;
              const pPct = (pCal / total) * 100;
              const cPct = (cCal / total) * 100;
              const fPct = (fCal / total) * 100;
              return (
                <div className="flex items-center gap-3 ml-auto">
                  <div
                    className="w-12 h-12 rounded-full shrink-0"
                    style={{
                      background: `conic-gradient(
                        #60a5fa ${pPct}%,
                        #fbbf24 ${pPct}% ${pPct + cPct}%,
                        #f97316 ${pPct + cPct}% 100%
                      )`
                    }}
                    title="Calories from macros"
                  />
                  <div className="flex flex-col text-xs gap-0.5">
                    <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-blue-400 shrink-0" /> {pPct.toFixed(0)}% protein</span>
                    <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-amber-400 shrink-0" /> {cPct.toFixed(0)}% carbs</span>
                    <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-orange-400 shrink-0" /> {fPct.toFixed(0)}% fat</span>
                  </div>
                </div>
              );
            })()}
          </div>
        </div>
        {Object.keys(totals.micros).length > 0 && (
          <div className="bg-slate-700 text-white px-4 py-2 text-sm flex flex-wrap gap-4">
            {totals.micros["Fiber, total dietary"] && (
              <span>🌾 Fiber: {Math.round(totals.micros["Fiber, total dietary"].value)}g</span>
            )}
            {(() => {
              const entry = totals.micros["Sugars, added"] ?? totals.micros["Sugars, added (by difference)"]
                ?? Object.entries(totals.micros).find(([k]) => k.toLowerCase().includes("sugar") && k.toLowerCase().includes("added"));
              const val = entry?.value ?? entry?.[1]?.value;
              return val != null && <span>🍬 Added sugar: {Math.round(val)}g</span>;
            })()}
            {totals.micros["Sodium, Na"] && (
              <span>🧂 Na: {Math.round(totals.micros["Sodium, Na"].value)}mg</span>
            )}
            {totals.micros["Caffeine"] && (
              <span>☕ Caffeine: {Math.round(totals.micros["Caffeine"].value)}mg</span>
            )}
          </div>
        )}
        {totals.foodGroups && Object.values(totals.foodGroups).some(v => v > 0) && (
          <div className="bg-slate-600 text-white px-4 py-2 text-sm flex flex-wrap gap-4">
            <span className="text-slate-300 font-medium">Servings:</span>
            {totals.foodGroups.vegetables > 0 && <span>🥬 Veg: {totals.foodGroups.vegetables.toFixed(1)}</span>}
            {totals.foodGroups.fruits > 0 && <span>🍎 Fruit: {totals.foodGroups.fruits.toFixed(1)}</span>}
            {totals.foodGroups.protein > 0 && <span>🥩 Protein: {totals.foodGroups.protein.toFixed(1)}</span>}
            {totals.foodGroups.grains > 0 && <span>🌾 Grain: {totals.foodGroups.grains.toFixed(1)}</span>}
            {totals.foodGroups.dairy > 0 && <span>🥛 Dairy: {totals.foodGroups.dairy.toFixed(1)}</span>}
          </div>
        )}
        {totals.frameworks && (
          <div className="border-t border-slate-500 bg-slate-700">
            <button
              type="button"
              onClick={() => setShowFrameworkCompare((v) => !v)}
              className="w-full px-4 py-2 text-left text-sm font-medium text-slate-100 hover:bg-slate-600 flex items-center justify-between"
            >
              📊 Compare to MyPlate, Daily Dozen & Longevity
              <span className="text-slate-300">{showFrameworkCompare ? "▼" : "▶"}</span>
            </button>
            {showFrameworkCompare && (
              <div className="px-4 pb-4 pt-2 space-y-4 bg-slate-800">
                <FrameworkProgress title="MyPlate (2000 cal)" data={totals.frameworks.myPlate} targets={MYPLATE_TARGETS} units={{ grains: "oz", vegetables: "c", fruits: "c", protein: "oz", dairy: "c" }} labels={{ grains: "🌾 Grains", vegetables: "🥬 Vegetables", fruits: "🍎 Fruits", protein: "🥩 Protein", dairy: "🥛 Dairy" }} />
                <FrameworkProgress title="Dr. Gregor's Daily Dozen" data={totals.frameworks.dailyDozen} targets={DAILY_DOZEN_TARGETS} units={{}} labels={{ beans: "🫘 Beans", berries: "🫐 Berries", otherFruits: "🍎 Other Fruits", cruciferous: "🥦 Cruciferous", greens: "🥬 Greens", otherVeg: "🥕 Other Veg", flaxseed: "🌾 Flaxseed", nuts: "🥜 Nuts", spices: "🌿 Spices", wholeGrains: "🌾 Whole Grains" }} />
                <FrameworkProgress title="Longevity (plant-forward)" data={totals.frameworks.longevity} targets={LONGEVITY_TARGETS} units={{}} labels={{ legumes: "🫘 Legumes", wholeGrains: "🌾 Whole Grains", vegetables: "🥬 Vegetables", fruits: "🍎 Fruits", nuts: "🥜 Nuts" }} />
                {totals.frameworks.byIngredient?.length > 0 && (
                  <IngredientBreakdown byIngredient={totals.frameworks.byIngredient} unmatched={totals.frameworks.unmatched || []} />
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {meals.map((meal) => (
        <MealCard
          key={meal.id}
          meal={meal}
          onMealUpdated={(mid, updates) =>
            setMeals((prev) => prev.map((m) => (m.id === mid ? { ...m, ...updates } : m)))
          }
          onTotalsRefresh={refreshTotals}
          frameworkAttribution={totals.frameworks?.byIngredient?.reduce((acc, item) => {
            if (item.id && item.contributed) acc[item.id] = { matched: item.matched, emoji: MATCHED_TO_EMOJI[item.matched] || "•" };
            return acc;
          }, {}) || {}}
        />
      ))}

      {/* Learning Panel */}
      {showLearning && (
        <LearningPanel onClose={() => setShowLearning(false)} />
      )}
    </div>
  );
}

function MealCard({ meal, onMealUpdated, onTotalsRefresh, frameworkAttribution }) {
  const [ingredients, setIngredients] = useState([]);
  const [correcting, setCorrecting] = useState(null);
  const [parsing, setParsing] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [clearingNonFood, setClearingNonFood] = useState(false);
  const [addingIngredients, setAddingIngredients] = useState(false);
  const [showAddIngredients, setShowAddIngredients] = useState(false);
  const [addIngredientsText, setAddIngredientsText] = useState("");
  const [deletingId, setDeletingId] = useState(null);
  const [editingPortionId, setEditingPortionId] = useState(null);
  const [editingQty, setEditingQty] = useState("");
  const [editingUnit, setEditingUnit] = useState("serving");
  const [updatingPortionId, setUpdatingPortionId] = useState(null);
  const [portionEstimateNote, setPortionEstimateNote] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const [expandedNutrientId, setExpandedNutrientId] = useState(null);

  const [hasNonFoodLogs, setHasNonFoodLogs] = useState(false);

  useEffect(() => {
    async function loadIngredients() {
      console.log("🔍 Fetching ingredients for meal:", meal.id, meal.text);
      const ings = await fetchIngredients(meal.id);
      console.log("✅ Ingredients response:", ings);
      setIngredients(ings);
      setLoaded(true);
      // If no ingredients and has content, check if it was classified as non-food (persisted)
      if (ings.length === 0 && (meal.text?.trim() || meal.image)) {
        const hasLogs = await fetchHasNonFoodLogs(meal.id);
        setHasNonFoodLogs(hasLogs);
      } else {
        setHasNonFoodLogs(false);
      }
    }
    loadIngredients();
  }, [meal.id, meal.text, meal.image]);

  // Parse meal on demand (works with text OR images via backend API)
  const [parseError, setParseError] = useState(null);
  const [classificationResult, setClassificationResult] = useState(null); // "not_food" when classified as non-food
  const [emptyParseMessage, setEmptyParseMessage] = useState(null); // when parse returns 0 ingredients (so user isn't stuck in a loop)
  const [emptyParseReason, setEmptyParseReason] = useState(null);   // API reason/debug (e.g. "from text: 0, from image: 0")
  const [parseSuccessMessage, setParseSuccessMessage] = useState(null); // "Added: X, Y, Z" after successful parse
  const handleParse = async () => {
    if (!meal.text?.trim() && !meal.image) {
      setParseError("Add a caption or photo first.");
      return;
    }
    flowLog.add({ type: "action", message: "Parse clicked", detail: { mealId: meal.id, textPreview: (meal.text || "").slice(0, 50) } });
    setParsing(true);
    setParseError(null);
    setClassificationResult(null);
    setEmptyParseMessage(null);
    setEmptyParseReason(null);
    setParseSuccessMessage(null);
    try {
      const result = await parseAndSaveMeal(meal);
      const data = result?.ingredients !== undefined ? result : { ingredients: result, classificationResult: null };
      const ingredientsList = Array.isArray(data.ingredients) ? data.ingredients : [];
      setIngredients(ingredientsList);
      flowLog.add({ type: "result", message: "Ingredients set", detail: { count: ingredientsList.length } });
      setClassificationResult(data.classificationResult || null);
      if (data.classificationResult === "not_food" || data.isFood === false) {
        setHasNonFoodLogs(true);
        onMealUpdated?.(meal.id, { isFood: false, categories: data.categories || [] });
      }
      if (ingredientsList.length === 0 && data.classificationResult !== "not_food") {
        let msg = result?.message || "No ingredients detected. Add a caption or try a clearer photo.";
        if (result?.source === "gpt_image" && msg.includes("No ingredients detected")) {
          msg += " If this meal has a photo, the image may not have loaded — restart or redeploy the Parse API, or add a short caption and parse again.";
        }
        setEmptyParseMessage(msg);
        setEmptyParseReason(result?.reason || null);
      } else if (ingredientsList.length > 0) {
        const names = ingredientsList.map((i) => i.name || "?").join(", ");
        setParseSuccessMessage(`Added: ${names}`);
        setTimeout(() => setParseSuccessMessage(null), 5000);
      }
      onTotalsRefresh?.();
    } catch (err) {
      const message = err?.message || String(err);
      console.error("Parse failed:", message);
      setParseError(message);
    } finally {
      setParsing(false);
    }
  };

  // Clear all ingredients for this meal
  const handleClear = async () => {
    if (!confirm("Delete all parsed ingredients for this meal?")) return;
    setClearing(true);
    setEmptyParseMessage(null);
    setEmptyParseReason(null);
    setParseSuccessMessage(null);
    try {
      await clearMealIngredients(meal.id);
      setIngredients([]);
      onTotalsRefresh?.();
    } catch (err) {
      console.error("Clear failed:", err);
      alert(`Clear failed: ${err.message}`);
    } finally {
      setClearing(false);
    }
  };

  // Delete single ingredient
  const handleDeleteIngredient = async (ing) => {
    if (!confirm(`Remove "${ing.name}" from this meal?`)) return;
    setDeletingId(ing.id);
    try {
      await deleteIngredient(ing.id);
      setIngredients((prev) => prev.filter((i) => i.id !== ing.id));
      onTotalsRefresh?.();
    } catch (err) {
      console.error("Delete ingredient failed:", err);
      alert(`Delete failed: ${err.message}`);
    } finally {
      setDeletingId(null);
    }
  };

  // Quick-edit portion (amount) without opening correction chat
  const handleStartPortionEdit = (ing) => {
    setEditingPortionId(ing.id);
    setEditingQty(String(ing.quantity ?? 1));
    setEditingUnit(ing.unit || "serving");
  };
  const handlePortionUpdate = async () => {
    if (!editingPortionId) return;
    const qty = parseFloat(editingQty);
    if (isNaN(qty) || qty <= 0) {
      setEditingPortionId(null);
      return;
    }
    setUpdatingPortionId(editingPortionId);
    setPortionEstimateNote(null);
    try {
      const result = await updateIngredientPortion(editingPortionId, qty, editingUnit);
      const saved = result.ingredient;
      setIngredients((prev) => prev.map((i) => (i.id === editingPortionId ? { ...i, ...saved } : i)));
      onTotalsRefresh?.();
      setEditingPortionId(null);
      if (result.pieceWeightEstimated) {
        setPortionEstimateNote("⚠️ Used estimated piece weight (50g) — verify calories if something looks off.");
        setTimeout(() => setPortionEstimateNote(null), 8000);
      }
    } catch (err) {
      console.error("Portion update failed:", err);
      alert(`Update failed: ${err.message}`);
    } finally {
      setUpdatingPortionId(null);
    }
  };

  // Add multiple ingredients from text
  const handleAddIngredients = async () => {
    const text = addIngredientsText.trim();
    if (!text) return;
    setAddingIngredients(true);
    try {
      const result = await addIngredients(meal.id, text);
      const added = result.ingredients || [];
      if (added.length > 0) {
        setIngredients((prev) => [...prev, ...added]);
        onTotalsRefresh?.();
        setAddIngredientsText("");
        setShowAddIngredients(false);
      }
    } catch (err) {
      console.error("Add ingredients failed:", err);
      alert(`Add ingredients failed: ${err.message}`);
    } finally {
      setAddingIngredients(false);
    }
  };

  // Clear non-food classification (allows re-parsing as food)
  const handleClearNonFood = async () => {
    if (!confirm("Remove non-food classification? You can parse again as food.")) return;
    setClearingNonFood(true);
    try {
      await clearNonFoodClassification(meal.id);
      setClassificationResult(null);
      setHasNonFoodLogs(false);
      onMealUpdated?.(meal.id, { isFood: null });
    } catch (err) {
      console.error("Clear non-food failed:", err);
      alert(`Clear failed: ${err.message}`);
    } finally {
      setClearingNonFood(false);
    }
  };

  // Check if this meal needs parsing (either text or image)
  const hasContent = meal.text?.trim() || meal.image;
  // Non-food: from current parse session OR non_food_logs OR meal metadata (isFood=false + categories set)
  // Use meal.isFood+categories as fallback when PocketBase listRules hide non_food_logs from user
  const fromMealMeta = meal.isFood === false && Array.isArray(meal.categories) && meal.categories.length > 0;
  const isNonFood = classificationResult === "not_food" || hasNonFoodLogs || fromMealMeta;
  const needsParsing = loaded && ingredients.length === 0 && hasContent && !isNonFood;

  // Build image URL if meal has an image
  const imageUrl = meal.image ? 
    `https://pocketbase-1j2x.onrender.com/api/files/meals/${meal.id}/${meal.image}` : null;

  // Zoom modal: click thumbnail to open, rotate 90°
  const [showZoom, setShowZoom] = useState(false);
  const [rotation, setRotation] = useState(0);

  return (
    <div className="bg-white p-4 rounded-xl shadow mb-4">
      <div className="flex gap-4">
        {/* Image thumbnail if exists — click to zoom */}
        {imageUrl && (
          <button
            type="button"
            onClick={() => { setShowZoom(true); setRotation(0); }}
            className="flex-shrink-0 rounded-lg overflow-hidden focus:outline-none focus:ring-2 focus:ring-purple-400"
          >
            <img 
              src={imageUrl} 
              alt="Meal" 
              className="w-20 h-20 object-cover rounded-lg hover:opacity-90"
            />
          </button>
        )}
        {/* Zoom modal */}
        {showZoom && imageUrl && (
          <div 
            className="fixed inset-0 z-[100] bg-black/80 flex items-center justify-center p-4"
            onClick={() => setShowZoom(false)}
          >
            <div 
              className="relative max-w-[90vw] max-h-[90vh] flex flex-col items-center"
              onClick={(e) => e.stopPropagation()}
            >
              <img 
                src={imageUrl} 
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
        
        <div className="flex-1">
          <h2 className="font-semibold mb-1">
            {meal.text || (meal.image ? "(image only)" : "(empty entry)")}
          </h2>
          <p className="text-gray-500 text-sm mb-2">
            {meal.timestamp ? new Date(meal.timestamp.replace(' ', 'T')).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }) : ''}
          </p>
        </div>
      </div>

      {/* Empty parse result (0 ingredients) — so user knows why and can try again */}
      {emptyParseMessage && !parsing && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-center">
          <p className="text-amber-800 text-sm font-medium">Parse result</p>
          <p className="text-amber-700 text-xs mt-1">{emptyParseMessage}</p>
          {emptyParseReason && (
            <p className="text-amber-600 text-xs mt-1.5 font-mono" title="Why the parse returned no ingredients">
              Why: {emptyParseReason}
            </p>
          )}
          <p className="text-amber-600 text-xs mt-2 font-mono" title="Parse API this dashboard is calling">
            Parse API: {getParseApiUrl()}
          </p>
          <button
            type="button"
            onClick={() => { setEmptyParseMessage(null); setEmptyParseReason(null); }}
            className="mt-2 text-xs text-amber-600 hover:underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Needs parsing state (hide when we already got "not food" or showing empty-parse message) */}
      {needsParsing && !parsing && classificationResult !== "not_food" && !emptyParseMessage && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-center">
          <p className="text-blue-700 text-sm mb-2">Not parsed yet</p>
          <button
            onClick={handleParse}
            className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 text-sm"
          >
            🧠 Parse Now
          </button>
        </div>
      )}

      {/* Parsing state */}
      {parsing && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-center">
          <p className="text-blue-700 text-sm">🧠 Parsing...</p>
        </div>
      )}

      {/* Parse success confirmation */}
      {parseSuccessMessage && !parsing && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-3 flex items-center justify-between gap-2">
          <p className="text-green-800 text-sm">✓ {parseSuccessMessage}</p>
          <button type="button" onClick={() => setParseSuccessMessage(null)} className="text-green-600 hover:text-green-800 shrink-0">✕</button>
        </div>
      )}

      {/* Parse error */}
      {parseError && !parsing && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-center">
          <p className="text-red-700 text-sm font-medium">Parse failed</p>
          <p className="text-red-600 text-xs mt-1 break-words">{parseError}</p>
          <button
            type="button"
            onClick={() => setParseError(null)}
            className="mt-2 text-xs text-red-500 hover:underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Non-food item (parsed, no ingredients) — show Clear like ingredients */}
      {isNonFood && ingredients.length === 0 && !parsing && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
          <div className="flex justify-between items-center">
            <p className="text-amber-800 text-sm font-medium">Non-food item</p>
            <button
              type="button"
              onClick={handleClearNonFood}
              disabled={clearingNonFood}
              className="text-xs text-amber-600 hover:text-amber-800 hover:underline disabled:opacity-50"
            >
              {clearingNonFood ? "Clearing..." : "🗑️ Clear"}
            </button>
          </div>
          <p className="text-amber-700 text-xs mt-1">Classified as non-food — no ingredients added.</p>
        </div>
      )}

      {/* Portion estimate warning (when piece weight not in our list) */}
      {portionEstimateNote && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-2 mb-2 flex items-center justify-between gap-2">
          <p className="text-amber-800 text-xs">{portionEstimateNote}</p>
          <button type="button" onClick={() => setPortionEstimateNote(null)} className="text-amber-600 hover:text-amber-800 shrink-0">✕</button>
        </div>
      )}

      {/* Ingredients list */}
      {ingredients.length > 0 && (
        <div>
          <div className="flex justify-between items-center mb-2">
            <span className="text-xs text-gray-400 flex items-center gap-2">
              {ingredients.length} ingredient{ingredients.length !== 1 ? 's' : ''}
              {(() => {
                const needReview = ingredients.filter(ing => isLowConfidence(ing)).length;
                return needReview > 0 ? (
                  <span className="px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 text-[10px] font-medium">
                    {needReview} need{needReview === 1 ? 's' : ''} review
                  </span>
                ) : null;
              })()}
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowAddIngredients(true)}
                className="text-xs text-blue-600 hover:text-blue-800"
              >
                + Add
              </button>
              <button
                onClick={handleClear}
                disabled={clearing}
                className="text-xs text-red-400 hover:text-red-600 disabled:opacity-50"
              >
                {clearing ? "Clearing..." : "🗑️ Clear"}
              </button>
            </div>
          </div>
          <ul className="text-sm text-gray-700 space-y-1">
          {ingredients.map((ing) => {
            const nutrients = getNutritionArray(ing);
            // Prefer Energy in KCAL (USDA has both KCAL and kJ); fallback to first Energy
            const energy = nutrients.find((n) => (n.nutrientName === "Energy" || (n.nutrientName || "").toLowerCase() === "energy") && (n.unitName || "").toUpperCase() === "KCAL")
              ?? nutrients.find((n) => (n.nutrientName || "").toLowerCase().includes("energy"));
            const protein = nutrients.find((n) => (n.nutrientName || "").toLowerCase().includes("protein"));
            const carbs = nutrients.find((n) => (n.nutrientName || "").toLowerCase().includes("carbohydrate"));
            const fat = nutrients.find((n) => (n.nutrientName || "").toLowerCase().includes("lipid") || (n.nutrientName || "").toLowerCase().includes("fat"));
            const lowConf = isLowConfidence(ing);

            // Source label helper
            const getSourceLabel = () => {
              if (ing.source === 'usda') return { label: 'USDA', color: 'bg-green-100 text-green-700' };
              if (ing.source === 'brand') return { label: 'Brand', color: 'bg-blue-100 text-blue-700' };
              if (ing.source === 'learned') return { label: 'Learned', color: 'bg-purple-100 text-purple-700' };
              if (ing.source === 'simple') return { label: 'Parsed', color: 'bg-gray-100 text-gray-500' };
              return { label: 'GPT', color: 'bg-amber-100 text-amber-700' };
            };
            const sourceInfo = getSourceLabel();

            const showNutrients = expandedNutrientId === ing.id;
            const fg = ing.parsingMetadata?.foodGroupServings;

            return (
              <li 
                key={ing.id}
                className={`rounded-lg transition-colors ${lowConf ? 'bg-amber-50 border-l-4 border-amber-400' : ''}`}
              >
                <div
                  onClick={() => setCorrecting(ing)}
                  className={`flex items-center gap-2 p-2 cursor-pointer flex-wrap ${lowConf ? 'hover:bg-amber-100' : 'hover:bg-gray-50'}`}
                >
                  {/* Low confidence indicator */}
                  {lowConf && (
                    <span 
                      className="text-[10px] px-1.5 py-0.5 rounded font-medium bg-amber-200 text-amber-800 shrink-0"
                      title={ing.parsingMetadata?.partialLabel 
                        ? "Label was partially visible – nutrition from USDA. Re-photo with full label for exact values." 
                        : "Needs review — tap to fix"}
                    >
                      Review
                    </span>
                  )}
                  
                  {/* Name + amount + framework + calories — grouped together */}
                  <span className="font-medium shrink-0">{ing.name}</span>
                  {editingPortionId === ing.id ? (
                    <div
                      className="flex items-center gap-1 shrink-0"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <input
                        type="number"
                        min="0.25"
                        step="0.25"
                        value={editingQty}
                        onChange={(e) => setEditingQty(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handlePortionUpdate();
                          if (e.key === "Escape") setEditingPortionId(null);
                        }}
                        className="w-14 px-1 py-0.5 text-xs border rounded"
                        autoFocus
                      />
                      <select
                        value={editingUnit}
                        onChange={(e) => setEditingUnit(e.target.value)}
                        className="text-xs border rounded py-0.5"
                      >
                        {["serving", "cup", "cups", "oz", "g", "tbsp", "tsp", "piece", "pieces", "slice", "slices", "egg", "eggs"].map((u) => (
                          <option key={u} value={u}>{u}</option>
                        ))}
                      </select>
                      <button
                        type="button"
                        onClick={handlePortionUpdate}
                        disabled={updatingPortionId === ing.id || isNaN(parseFloat(editingQty)) || parseFloat(editingQty) <= 0}
                        className="text-[10px] px-1.5 py-0.5 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
                      >
                        {updatingPortionId === ing.id ? "…" : "✓"}
                      </button>
                      <button
                        type="button"
                        onClick={() => setEditingPortionId(null)}
                        className="text-[10px] px-1.5 py-0.5 text-gray-500 hover:text-gray-700"
                      >
                        ✕
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); handleStartPortionEdit(ing); }}
                      className="text-gray-500 text-xs hover:text-blue-600 hover:underline shrink-0"
                      title="Click to change amount (saves for learning)"
                    >
                      ({ing.quantity ?? 1} {ing.unit || "serving"})
                    </button>
                  )}
                  {frameworkAttribution?.[ing.id] && (
                    <span className="text-sm shrink-0" title={frameworkAttribution[ing.id].matched}>
                      {frameworkAttribution[ing.id].emoji}
                    </span>
                  )}
                  {energy || protein || carbs || fat ? (
                    <span className="text-gray-600 text-xs shrink-0">
                      {energy ? `${Math.round(energy.value)} cal` : ""}
                      {protein ? ` · ${Math.round(protein.value)}g P` : ""}
                    </span>
                  ) : (
                    <span className="text-gray-400 text-xs shrink-0 italic">no data</span>
                  )}
                  
                  {/* Source badge */}
                  <span className={`text-[10px] px-1.5 py-0.5 rounded shrink-0 ${sourceInfo.color}`}>
                    {sourceInfo.label}
                  </span>
                  {ing.parsingMetadata?.partialLabel && (
                    <span 
                      className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 shrink-0"
                      title="Label was partially visible – nutrition from USDA. Re-photo with full label for exact values."
                    >
                      Partial label
                    </span>
                  )}
                  
                  {/* View nutrients toggle */}
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); setExpandedNutrientId(showNutrients ? null : ing.id); }}
                    className="text-[10px] text-gray-400 hover:text-gray-600"
                  >
                    {showNutrients ? "▼ Nutrients" : "▶ Nutrients"}
                  </button>
                  <span className={`text-xs shrink-0 ${lowConf ? 'text-amber-600' : 'text-gray-300'}`}>
                    {lowConf ? 'Needs review — tap to fix' : 'tap to edit'}
                  </span>
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); handleDeleteIngredient(ing); }}
                    disabled={deletingId === ing.id}
                    className="ml-auto p-1 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded disabled:opacity-50 shrink-0"
                    title="Remove ingredient"
                  >
                    {deletingId === ing.id ? "…" : "🗑"}
                  </button>
                </div>
                {/* Expanded: full macro/micro list */}
                {showNutrients && (
                  <div 
                    className="px-2 pb-2 pt-0 border-t border-gray-100"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {nutrients.length > 0 ? (
                      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-[11px] text-gray-600">
                        {nutrients.map((n, i) => (
                          <span key={i}>
                            {n.nutrientName?.replace(/,.*$/, "")}: {n.value != null ? (n.value < 1 ? n.value.toFixed(2) : Math.round(n.value)) : "—"} {n.unitName || ""}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <p className="text-[11px] text-gray-400 italic">No nutrient data stored.</p>
                    )}
                    {fg && (fg.grains || fg.protein || fg.vegetables || fg.fruits || fg.dairy || fg.fats) && (
                      <p className="text-[10px] text-purple-600 mt-1.5">
                        Food groups: grains {fg.grains || 0} · protein {fg.protein || 0} · veg {fg.vegetables || 0} · fruit {fg.fruits || 0} · dairy {fg.dairy || 0} · fats {fg.fats || 0}
                      </p>
                    )}
                  </div>
                )}
              </li>
            );
          })}
          </ul>
        </div>
      )}

      {/* Correction Chat Modal */}
      {correcting && (
        <CorrectionChat 
          ingredient={correcting} 
          meal={meal}
          onClose={() => setCorrecting(null)}
          onSave={(result) => {
            if (result.addedIngredient) {
              setIngredients(prev => [...prev, result.addedIngredient]);
              fetchIngredients(meal.id).then((ings) => { setIngredients(ings); onTotalsRefresh?.(); }).catch(() => {});
            } else if (result.ingredient) {
              const saved = result.ingredient;
              setIngredients(prev => prev.map(i => i.id === correcting.id ? { ...i, ...saved } : i));
              setCorrecting((prev) => ({ ...prev, ...saved }));
              onTotalsRefresh?.();
            }
            // Never auto-close; user exits on their own
          }}
        />
      )}

      {/* Add ingredients modal */}
      {showAddIngredients && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white w-full max-w-md rounded-2xl shadow-xl p-4">
            <h3 className="font-semibold text-lg mb-2">Add ingredients</h3>
            <p className="text-sm text-gray-600 mb-3">
              Describe what to add (e.g. sardines 1 can, marinara 2 tbsp, olives 5)
            </p>
            <textarea
              value={addIngredientsText}
              onChange={(e) => setAddIngredientsText(e.target.value)}
              placeholder="sardines 1 can, marinara 2 tbsp"
              className="w-full px-4 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
              rows={3}
              disabled={addingIngredients}
            />
            <div className="flex gap-2 mt-4 justify-end">
              <button
                onClick={() => { setShowAddIngredients(false); setAddIngredientsText(""); }}
                disabled={addingIngredients}
                className="px-4 py-2 text-gray-600 hover:text-gray-800 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleAddIngredients}
                disabled={addingIngredients || !addIngredientsText.trim()}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {addingIngredients ? "Adding…" : "Add"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Natural language correction chat component
function CorrectionChat({ ingredient, meal, onClose, onSave }) {
  const lowConf = isLowConfidence(ingredient);
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [reDescribeMode, setReDescribeMode] = useState(false);
  const inputRef = useRef(null);
  const [pendingCorrection, setPendingCorrection] = useState(null);
  const [pendingLearned, setPendingLearned] = useState(null);
  const [pendingReason, setPendingReason] = useState(null);
  const [pendingShouldLearn, setPendingShouldLearn] = useState(false);
  const [conversationHistory, setConversationHistory] = useState([]);
  const [pendingPreview, setPendingPreview] = useState(null); // { previewResult, correction, learned, reason, shouldLearn, conversation, selectedUsdaOption? }
  const [loadingPreview, setLoadingPreview] = useState(false);
  const messagesEndRef = useRef(null);

  // Build the meal image URL
  const imageUrl = meal?.image ? 
    `https://pocketbase-1j2x.onrender.com/api/files/meals/${meal.id}/${meal.image}` : null;

  // Get the reasoning from parsing metadata
  const reasoning = ingredient.parsingMetadata?.reasoning || "No reasoning recorded";

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Initial greeting with reasoning
  useEffect(() => {
    const source = ingredient.source || "";
    const usdaHint = source.toLowerCase() === "usda"
      ? "\n\n_If the calories seem way off (e.g. 450 for one orange), say so and I'll use a better estimate._"
      : "";
    const greeting = `I identified this as **${ingredient.name}** (${ingredient.quantity || '?'} ${ingredient.unit || 'serving'}).

**My reasoning:** ${reasoning}

What would you like to change? You can tell me naturally, like "that's actually banana peppers", "it was more like 4 oz", or "the calories are way too high".${usdaHint}`;
    
    setMessages([{ from: "bot", text: greeting }]);
  }, [ingredient, reasoning]);

  const sendMessage = async (userMessage) => {
    const msg = (userMessage || "").trim();
    if (!msg || loading) return;

    // Add user message to UI
    setMessages(prev => [...prev, { from: "user", text: msg }]);
    setLoading(true);

    try {
      // Send to correction API
      const result = await sendCorrectionMessage(
        ingredient.id,
        msg,
        conversationHistory
      );

      // Add bot response — but skip when we'll show a preview (avoid "here's the correction" with no details)
      if (!(result.complete && result.correction)) {
        setMessages(prev => [...prev, { from: "bot", text: result.reply }]);
      }

      // Update conversation history for context (always, for API)
      setConversationHistory(prev => [
        ...prev,
        { role: "user", content: msg },
        { role: "assistant", content: result.reply }
      ]);

      // Store pending correction if any
      if (result.correction) {
        setPendingCorrection(result.correction);
      }
      if (result.learned) {
        setPendingLearned(result.learned);
      }
      if (result.correctionReason) {
        setPendingReason(result.correctionReason);
      }
      setPendingShouldLearn(result.shouldLearn || false);

      // If complete, preview first — show what would change, user confirms before save
      // Don't add the GPT reply when we'll show a preview; show "Loading preview..." instead
      // so the user doesn't see "here's the correction" with no details.
      if (result.complete && result.correction) {
        setLoadingPreview(true);
        const updatedConversation = [
          ...conversationHistory,
          { role: "user", content: msg },
          { role: "assistant", content: result.reply }
        ];
        try {
          const previewResult = await previewCorrection(
            ingredient.id,
            result.correction,
            result.learned,
            result.correctionReason,
            result.shouldLearn,
            updatedConversation
          );
          setPendingPreview({
            previewResult,
            correction: result.correction,
            learned: result.learned,
            reason: result.correctionReason,
            shouldLearn: result.shouldLearn,
            conversation: updatedConversation,
          });
          const toShow = previewResult.addedIngredient || previewResult.ingredient;
          const nutText = toShow ? formatNutritionSummary(getNutritionArray(toShow)) : "";
          const opts = previewResult.usdaOptions || [];
          const hasExact = previewResult.hasExactUsdaMatch;
          let previewMsg;
          if (!toShow) {
            previewMsg = "Preview unavailable — you can try confirming anyway, or cancel and correct again.";
          } else {
            previewMsg = previewResult.addedIngredient
              ? `Here's what I'll add:\n\n**${toShow.name}** — ${toShow.quantity ?? 1} ${toShow.unit || "serving"}${nutText ? "\n" + nutText : ""}\n\nConfirm to save, or cancel to edit.`
              : `Here's what I'll change it to:\n\n**${toShow.name}** — ${toShow.quantity ?? 1} ${toShow.unit || "serving"}${nutText ? "\n" + nutText : ""}\n\nConfirm to save, or cancel to edit.`;
          }
          if (opts.length > 0) {
            previewMsg += `\n\n${!hasExact ? "No exact USDA match for \"" + (result.correction?.name || ingredient.name) + "\". " : ""}Choose an option below or confirm to use the default.`;
          }
          setMessages(prev => [...prev, { from: "bot", text: previewMsg, isPreview: true, usdaOptions: opts }]);
        } catch (err) {
          setMessages(prev => [...prev, { from: "bot", text: `Could not preview: ${err.message}. You can try again.` }]);
        } finally {
          setLoadingPreview(false);
        }
      }

    } catch (err) {
      console.error("Correction chat error:", err);
      setMessages(prev => [...prev, { 
        from: "bot", 
        text: "Sorry, I had trouble processing that. The correction API might not be running. You can try again or close this dialog." 
      }]);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e) => {
    e?.preventDefault?.();
    const msg = inputValue.trim();
    if (msg) {
      setInputValue("");
      setReDescribeMode(false);
      sendMessage(msg);
    }
  };

  const handleConfirmPreview = async () => {
    if (!pendingPreview) return;
    const { correction, learned, reason, shouldLearn, conversation, selectedUsdaOption } = pendingPreview;
    const toSave = { ...correction };
    if (selectedUsdaOption) {
      toSave.chosenUsdaOption = selectedUsdaOption;
    }
    setPendingPreview(null);
    await handleSave(toSave, learned, reason, shouldLearn, conversation);
  };

  const handleCancelPreview = () => {
    setPendingPreview(null);
    setMessages(prev => [...prev, { from: "bot", text: "Cancelled. You can correct again or close when ready." }]);
  };

  const handleSave = async (correction = pendingCorrection, learned = pendingLearned, reason = pendingReason, shouldLearn = pendingShouldLearn, conversationOverride = null) => {
    if (!correction) return;

    setMessages(prev => [...prev, { from: "bot", text: "Saving your correction..." }]);

    try {
      const conversationToSend = conversationOverride ?? conversationHistory;
      const result = await saveCorrection(ingredient.id, correction, learned, reason, shouldLearn, conversationToSend);
      
      if (result.success) {
        let learnedMsg = "";
        if (result.shouldLearn && learned) {
          learnedMsg = ` I'll remember that "${learned.mistaken}" is actually "${learned.actual}" for next time.`;
        } else if (result.correctionReason && result.correctionReason !== "misidentified") {
          // Explain why we're not learning
          const reasonExplanations = {
            "added_after": "Since this was added after the photo, I won't learn from this.",
            "portion_estimate": "Since this was a portion estimate issue, I won't generalize from this.",
            "brand_specific": "Noted the brand info for this meal.",
            "missing_item": "Added the missing item to this meal.",
            "poor_usda_match": "Found a better USDA match or switched to an estimate.",
          };
          learnedMsg = ` ${reasonExplanations[result.correctionReason] || ""}`;
        }
        
        // Add USDA match info if applicable
        let usdaMsg = "";
        if (result.usdaMatch) {
          if (result.usdaMatch.found) {
            if (!result.usdaMatch.isExactMatch) {
              usdaMsg = ` (Note: Couldn't find exact nutrition for "${result.usdaMatch.searchedFor}" - using USDA data for "${result.usdaMatch.matchedName}" instead.)`;
            }
          } else {
            usdaMsg = ` (Note: No nutrition data found for "${result.usdaMatch.searchedFor}" in USDA database.)`;
          }
        }
        
        // Use result.ingredient (server response) as source of truth for the confirmation message
        const saved = result.ingredient || {};
        const displayName = saved.name ?? correction.name ?? ingredient.name;
        const displayQty = saved.quantity != null ? saved.quantity : (correction.quantity ?? ingredient.quantity);
        const displayUnit = saved.unit || correction.unit || ingredient.unit || "serving";

        const doneMsg = result.addedIngredient
          ? `Done! Added ${result.addedIngredient.name} (${result.addedIngredient.quantity || 1} ${result.addedIngredient.unit || "serving"}) as a new ingredient. ${ingredient.name} was left unchanged.${learnedMsg}${usdaMsg}`
          : `Done! Saved:\n\n**${displayName}** — ${displayQty} ${displayUnit}${learnedMsg}${usdaMsg}\n\nYou can close when ready or correct something else.`;
        setMessages(prev => [...prev, { from: "bot", text: doneMsg }]);

        // Sync parent state; keep modal open
        onSave(result);
      }
    } catch (err) {
      console.error("Save error:", err);
      setMessages(prev => [...prev, { from: "bot", text: "Failed to save. Please try again." }]);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white w-full max-w-lg rounded-2xl max-h-[90vh] flex flex-col shadow-xl">
        {/* Header with image */}
        <div className="flex items-center gap-3 p-4 border-b">
          {imageUrl && (
            <img 
              src={imageUrl} 
              alt="Meal" 
              className="w-12 h-12 object-cover rounded-lg"
            />
          )}
          <div className="flex-1">
            <h3 className="font-semibold">Correct: {ingredient.name}</h3>
            <p className="text-xs text-gray-500">
              {ingredient.quantity} {ingredient.unit} · {ingredient.source || 'GPT'} identified
            </p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl">
            ✕
          </button>
        </div>

        {/* Chat Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3 min-h-[200px]">
          {messages.map((msg, i) => (
            <div 
              key={i} 
              className={`flex ${msg.from === "user" ? "justify-end" : "justify-start"}`}
            >
              <div 
                className={`max-w-[85%] px-4 py-2 rounded-2xl whitespace-pre-wrap ${
                  msg.from === "user" 
                    ? "bg-blue-500 text-white rounded-br-md" 
                    : "bg-gray-100 text-gray-800 rounded-bl-md"
                }`}
              >
                {/* Simple markdown bold support */}
                {msg.text.split(/\*\*(.*?)\*\*/).map((part, j) => 
                  j % 2 === 1 ? <strong key={j}>{part}</strong> : part
                )}
              </div>
            </div>
          ))}
          {(loading || loadingPreview) && (
            <div className="flex justify-start">
              <div className="bg-gray-100 text-gray-500 px-4 py-2 rounded-2xl rounded-bl-md max-w-[85%]">
                {loadingPreview ? (
                  <div>
                    <p className="text-sm">Loading preview...</p>
                    <div className="mt-2 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                      <div className="h-full bg-blue-500 rounded-full animate-pulse" style={{ width: "60%" }} />
                    </div>
                  </div>
                ) : (
                  "Thinking..."
                )}
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Quick actions + Input */}
        <div className="p-4 border-t bg-gray-50 space-y-3">
          {/* Low-confidence quick actions */}
          {lowConf && !pendingPreview && (
            <div className="flex flex-wrap gap-2 pb-1 border-b border-amber-200/50">
              <span className="text-xs text-amber-700 font-medium w-full">Quick fix:</span>
              <button
                type="button"
                onClick={() => sendMessage("This is wrong, please be more specific")}
                disabled={loading}
                className="text-xs px-3 py-2 bg-amber-100 border border-amber-300 rounded-lg text-amber-800 hover:bg-amber-200 font-medium disabled:opacity-50"
              >
                👎 Wrong
              </button>
              <button
                type="button"
                onClick={() => { setReDescribeMode(true); inputRef.current?.focus(); }}
                disabled={loading}
                className="text-xs px-3 py-2 bg-amber-100 border border-amber-300 rounded-lg text-amber-800 hover:bg-amber-200 font-medium disabled:opacity-50"
              >
                ✏️ Re-describe
              </button>
            </div>
          )}
          {/* USDA options when preview has them */}
          {pendingPreview?.previewResult?.usdaOptions?.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs font-medium text-gray-600">Pick a USDA match:</p>
              <div className="max-h-48 overflow-y-auto flex flex-col gap-2">
                {pendingPreview.previewResult.usdaOptions.map((opt) => {
                  const isSelected = pendingPreview.selectedUsdaOption?.usdaCode === opt.usdaCode;
                  const nut = [opt.calories != null && `${opt.calories} cal`, opt.protein != null && `${opt.protein}g protein`, opt.carbs != null && `${opt.carbs}g carbs`].filter(Boolean).join(", ");
                  return (
                    <button
                      key={opt.usdaCode}
                      type="button"
                      onClick={() => setPendingPreview((p) => p ? { ...p, selectedUsdaOption: isSelected ? null : opt } : null)}
                      className={`text-left px-3 py-2.5 rounded-lg border min-h-[3rem] ${isSelected ? "border-green-500 bg-green-50" : "border-gray-200 hover:bg-gray-50"}`}
                    >
                      <div className="font-medium text-sm leading-snug break-words">{opt.name}</div>
                      {nut && <div className="text-gray-500 text-xs mt-0.5">{nut}</div>}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
          {/* Confirm/Cancel when preview is pending */}
          {pendingPreview && (
            <div className="flex gap-2">
              <button
                onClick={handleConfirmPreview}
                disabled={loading}
                className="flex-1 px-4 py-2 bg-green-600 text-white rounded-lg font-medium hover:bg-green-700 disabled:opacity-50"
              >
                ✓ Confirm & save
              </button>
              <button
                onClick={handleCancelPreview}
                disabled={loading}
                className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg font-medium hover:bg-gray-300 disabled:opacity-50"
              >
                Cancel
              </button>
            </div>
          )}
          {/* Quick action buttons - above text input, send directly (no autofill) */}
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => {
                setMessages(prev => [...prev, { from: "bot", text: "No changes needed." }]);
                onClose();
              }}
              className="text-xs px-3 py-2 bg-green-50 border border-green-200 rounded-lg text-green-700 hover:bg-green-100 font-medium flex items-center gap-1.5"
            >
              <span>✓</span> Looks great!
            </button>
            <button
              onClick={() => sendMessage("You misidentified something in the image")}
              disabled={loading}
              className="text-xs px-3 py-2 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 font-medium flex items-center gap-1.5 disabled:opacity-50"
            >
              <span>🤖</span> You misidentified something in the image
            </button>
            <button
              onClick={() => sendMessage("You identified correctly, but the nutrition looks off")}
              disabled={loading}
              className="text-xs px-3 py-2 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 font-medium flex items-center gap-1.5 disabled:opacity-50"
            >
              <span>🔍</span> You identified correctly, but the nutrition looks off
            </button>
            <button
              onClick={() => sendMessage("I want to add or clarify information about this item (e.g. brand, specific type)")}
              disabled={loading}
              className="text-xs px-3 py-2 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 font-medium flex items-center gap-1.5 disabled:opacity-50"
            >
              <span>📝</span> Add information to this item
            </button>
            <button
              onClick={() => sendMessage("I need to add a completely new ingredient that you missed")}
              disabled={loading}
              className="text-xs px-3 py-2 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 font-medium flex items-center gap-1.5 disabled:opacity-50"
            >
              <span>➕</span> Add a new ingredient to this meal
            </button>
          </div>

          {/* Text input - always available */}
          <form onSubmit={handleSubmit} className="flex gap-2">
            <input
              ref={inputRef}
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder={reDescribeMode ? "Describe in your own words (e.g. 2 slices pepperoni pizza)" : "Tell me what to correct..."}
              className="flex-1 px-4 py-2 border rounded-full text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              autoFocus
              disabled={loading}
            />
            <button 
              type="submit"
              disabled={loading || !inputValue.trim()}
              className="px-4 py-2 bg-blue-500 text-white rounded-full text-sm hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Send
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

// Learning Panel - shows what the app has learned
function LearningPanel({ onClose }) {
  const [patterns, setPatterns] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('patterns'); // patterns | timeline
  const [unlearning, setUnlearning] = useState(null);

  const load = async () => {
    try {
      const [p, s] = await Promise.all([
        getLearnedPatterns(),
        getLearningStats()
      ]);
      setPatterns(p);
      setStats(s);
    } catch (err) {
      console.error("Failed to load learning data:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleUnlearn = async (p) => {
    if (!confirm(`Unlearn "${p.original}" → "${p.learned}"? This will stop the app from suggesting this correction in future parses.`)) return;
    setUnlearning(p.original + "→" + p.learned);
    try {
      await removeLearnedPattern(p.original, p.learned, p.correctionIds || []);
      await load();
    } catch (err) {
      console.error("Unlearn failed:", err);
      alert("Could not unlearn. Please try again.");
    } finally {
      setUnlearning(null);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white w-full max-w-lg rounded-2xl max-h-[90vh] flex flex-col shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b">
          <h3 className="font-semibold text-lg">🧠 What I've Learned</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl">
            ✕
          </button>
        </div>

        {/* Stats Summary */}
        {stats?.summary && (
          <div className="bg-gradient-to-r from-purple-50 to-blue-50 p-4 border-b">
            <div className="grid grid-cols-3 gap-4 text-center">
              <div>
                <div className="text-2xl font-bold text-purple-600">{stats.summary.totalCorrections}</div>
                <div className="text-xs text-gray-500">Corrections</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-blue-600">{stats.summary.uniquePatterns}</div>
                <div className="text-xs text-gray-500">Patterns</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-green-600">{stats.summary.confidentPatterns}</div>
                <div className="text-xs text-gray-500">Confident</div>
              </div>
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="flex border-b">
          {[
            { id: 'patterns', label: 'Patterns' },
            { id: 'timeline', label: 'Timeline' },
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 py-2 text-sm font-medium transition-colors ${
                activeTab === tab.id 
                  ? 'text-purple-600 border-b-2 border-purple-600' 
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <p className="text-gray-400 text-center py-8">Loading...</p>
          ) : (
            <>
              {/* Patterns Tab */}
              {activeTab === 'patterns' && (
                <div>
                  {patterns.length === 0 ? (
                    <p className="text-gray-400 text-sm text-center py-8">No patterns yet. Correct some ingredients!</p>
                  ) : (
                    <div className="space-y-2">
                      <p className="text-xs text-gray-500 mb-2">
                        Tap ✕ to unlearn a pattern that was learned by mistake.
                      </p>
                      {patterns.map((p, i) => (
                        <div key={i} className="flex items-center justify-between bg-gray-50 p-3 rounded-lg group">
                          <div>
                            <span className="text-gray-500">"{p.original}"</span>
                            <span className="mx-2">→</span>
                            <span className="font-medium">{p.learned}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-gray-400">{p.count}x</span>
                            <span className={`text-xs px-2 py-0.5 rounded-full ${
                              p.status === 'confident' ? 'bg-green-100 text-green-700' : 
                              'bg-yellow-100 text-yellow-700'
                            }`}>
                              {p.status === 'confident' ? '✓ Confident' : 'Learning'}
                            </span>
                            <button
                              type="button"
                              onClick={() => handleUnlearn(p)}
                              disabled={unlearning === p.original + "→" + p.learned}
                              className="text-gray-400 hover:text-red-600 hover:bg-red-50 p-1 rounded text-sm transition-colors"
                              title="Unlearn this pattern"
                            >
                              {unlearning === p.original + "→" + p.learned ? "…" : "✕"}
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Timeline Tab */}
              {activeTab === 'timeline' && (
                <div>
                  {!stats?.timeline?.length ? (
                    <p className="text-gray-400 text-sm text-center py-8">No timeline data yet.</p>
                  ) : (
                    <div className="space-y-3">
                      <p className="text-sm text-gray-500 mb-4">
                        See how the system adapts as you make corrections (batches of 5)
                      </p>
                      {stats.timeline.map((point, i) => (
                        <div key={i} className="relative pl-6 pb-4 border-l-2 border-purple-200 last:border-l-0">
                          {/* Milestone dot */}
                          <div className={`absolute -left-2 w-4 h-4 rounded-full ${
                            point.confidentPatterns > 0 ? 'bg-green-500' : 'bg-purple-400'
                          }`} />
                          
                          <div className="bg-gray-50 p-3 rounded-lg">
                            <div className="flex justify-between items-center mb-2">
                              <span className="font-medium text-purple-700">
                                Correction #{point.correctionNum}
                              </span>
                              <span className="text-xs text-gray-400">
                                {new Date(point.date).toLocaleDateString()}
                              </span>
                            </div>
                            
                            <div className="grid grid-cols-2 gap-2 text-sm">
                              <div className="bg-white p-2 rounded">
                                <span className="text-blue-600 font-medium">{point.uniquePatterns}</span>
                                <span className="text-gray-500 text-xs ml-1">unique patterns</span>
                              </div>
                              <div className="bg-white p-2 rounded">
                                <span className="text-green-600 font-medium">{point.confidentPatterns}</span>
                                <span className="text-gray-500 text-xs ml-1">confident</span>
                              </div>
                            </div>
                            
                            {point.latestCorrection?.from && (
                              <div className="mt-2 text-xs text-gray-500">
                                Latest: "{point.latestCorrection.from}" → "{point.latestCorrection.to}"
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t bg-gray-50 text-center text-xs text-gray-500">
          {stats?.summary?.learningRate > 0 
            ? `${stats.summary.learningRate}% of patterns are confident (3+ corrections)`
            : "I learn from your corrections instantly!"}
        </div>
      </div>
    </div>
  );
}
