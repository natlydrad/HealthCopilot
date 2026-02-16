import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  fetchRegressionSuite,
  runRegressionMeal,
  runGoldenSet,
  fetchRecentMealsForGolden,
  goldenAddBulk,
  goldenClear,
} from "./api";

const REGRESSION_CONCURRENCY = 3;

/** Extract calories from ingredient nutrition array. */
function getCalories(ing) {
  const nut = ing?.nutrition;
  if (!Array.isArray(nut)) return null;
  const n = nut.find(
    (x) =>
      x?.nutrientName &&
      x.nutrientName.toLowerCase().includes("energy") &&
      !x.nutrientName.toLowerCase().includes("kj")
  );
  return n != null ? Number(n.value) : null;
}

/** Extract key nutrients from ingredient nutrition array (matches backend _get_nutrients). */
function getNutrients(ing) {
  const nut = ing?.nutrition;
  if (!Array.isArray(nut)) return {};
  const out = { calories: null, protein: null, carbs: null, fat: null, fiber_g: null, sugar_g: null, sodium_mg: null, caffeine_mg: null };
  for (const n of nut) {
    if (!n || typeof n !== "object") continue;
    const nn = (n.nutrientName || "").toLowerCase();
    const un = (n.unitName || "").toUpperCase();
    const val = Number(n.value);
    if (Number.isNaN(val)) continue;
    if (nn.includes("energy") && !nn.includes("kj")) out.calories = val;
    else if (nn === "protein") out.protein = val;
    else if (nn.includes("carbohydrate")) out.carbs = val;
    else if (nn.includes("lipid") || nn === "fat") out.fat = val;
    else if (nn.includes("fiber") && nn.includes("dietary") && un === "G") out.fiber_g = val;
    else if ((nn.includes("sugars") || nn.includes("sugar")) && un === "G") out.sugar_g = val;
    else if (nn.includes("sodium") && nn.includes("na") && un === "MG") out.sodium_mg = val;
    else if (nn === "caffeine" && un === "MG") out.caffeine_mg = val;
  }
  return out;
}

async function runWithConcurrency(tasks, maxConcurrent, onProgress) {
  const results = [];
  let completed = 0;
  let next = 0;

  const runOne = async (index) => {
    if (index >= tasks.length) return;
    try {
      const value = await tasks[index]();
      results[index] = { status: "fulfilled", value };
    } catch (err) {
      results[index] = { status: "rejected", reason: err };
    } finally {
      completed++;
      onProgress?.(completed, tasks.length);
      if (next < tasks.length) {
        await runOne(next++);
      }
    }
  };

  const workers = [];
  for (let i = 0; i < Math.min(maxConcurrent, tasks.length); i++) {
    workers.push(runOne(next++));
  }
  await Promise.all(workers);
  return results;
}

export default function RegressionSuite() {
  const navigate = useNavigate();
  const [suite, setSuite] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [results, setResults] = useState({}); // mealId -> { passed, failures, ingredients }
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState({ current: 0, total: 0 });
  const [expandedId, setExpandedId] = useState(null);
  const [goldenResults, setGoldenResults] = useState([]); // [ { id, text, passed, failures, actualIngredients }, ... ]
  const [goldenRunning, setGoldenRunning] = useState(false);
  const [goldenExpandedId, setGoldenExpandedId] = useState(null);
  const [builderMeals, setBuilderMeals] = useState([]);
  const [builderLoading, setBuilderLoading] = useState(false);
  const [builderSelected, setBuilderSelected] = useState(new Set());
  const [builderCategory, setBuilderCategory] = useState({});
  const [builderAdding, setBuilderAdding] = useState(false);
  const [builderClearing, setBuilderClearing] = useState(false);
  const [builderEditId, setBuilderEditId] = useState(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchRegressionSuite();
        setSuite(data);
      } catch (err) {
        setError(err.message || "Failed to load regression suite");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const handleRunAll = async () => {
    if (!suite?.meals?.length) return;
    setRunning(true);
    setResults({});
    setProgress({ current: 0, total: suite.meals.length });

    const tasks = suite.meals.map((meal) => () =>
      runRegressionMeal(meal.text, meal.expectations || {})
    );

    const raw = await runWithConcurrency(
      tasks,
      REGRESSION_CONCURRENCY,
      (current, total) => setProgress({ current, total })
    );

    const next = {};
    suite.meals.forEach((meal, i) => {
      const r = raw[i];
      if (r?.status === "fulfilled") {
        next[meal.id] = {
          passed: r.value.passed,
          failures: r.value.failures || [],
          ingredients: r.value.ingredients || [],
          checkDetails: r.value.checkDetails || [],
        };
      } else {
        next[meal.id] = {
          passed: false,
          failures: [r?.reason?.message || "Request failed"],
          ingredients: [],
          checkDetails: [],
        };
      }
    });
    setResults(next);
    setRunning(false);
    setProgress({ current: 0, total: 0 });
  };

  const handleRunOne = async (meal) => {
    setRunning(true);
    try {
      const data = await runRegressionMeal(meal.text, meal.expectations || {});
      setResults((prev) => ({
        ...prev,
        [meal.id]: {
          passed: data.passed,
          failures: data.failures || [],
          ingredients: data.ingredients || [],
          checkDetails: data.checkDetails || [],
        },
      }));
      setExpandedId(meal.id);
    } catch (err) {
      setResults((prev) => ({
        ...prev,
        [meal.id]: {
          passed: false,
          failures: [err.message || "Request failed"],
          ingredients: [],
          checkDetails: [],
        },
      }));
      setExpandedId(meal.id);
    } finally {
      setRunning(false);
    }
  };

  const handleRunGoldenSet = async () => {
    setGoldenRunning(true);
    setGoldenResults([]);
    try {
      const data = await runGoldenSet();
      setGoldenResults(data.results || []);
    } catch (err) {
      setGoldenResults([{ id: "_error", text: "", passed: false, failures: [err.message || "Failed to run golden set"], actualIngredients: [] }]);
    } finally {
      setGoldenRunning(false);
    }
  };

  const handleLoadRecentMeals = async () => {
    setBuilderLoading(true);
    try {
      const data = await fetchRecentMealsForGolden(200);
      setBuilderMeals(data.meals || []);
      setBuilderSelected(new Set());
      setBuilderCategory({});
    } catch (err) {
      setBuilderMeals([]);
    } finally {
      setBuilderLoading(false);
    }
  };

  const toggleBuilderSelected = (id) => {
    setBuilderSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleAddSelectedToGolden = async () => {
    const entries = builderMeals
      .filter((m) => builderSelected.has(m.id) && !m.inGoldenSet)
      .map((m) => ({
        mealId: m.id,
        text: m.text || "",
        ingredients: m.ingredients || [],
        category: builderCategory[m.id] || "normal",
      }));
    if (!entries.length) return;
    setBuilderAdding(true);
    try {
      await goldenAddBulk(entries);
      await handleLoadRecentMeals();
      setBuilderSelected(new Set());
    } finally {
      setBuilderAdding(false);
    }
  };

  const handleClearGoldenSet = async () => {
    if (!window.confirm("Clear the entire golden set? This cannot be undone.")) return;
    setBuilderClearing(true);
    try {
      await goldenClear(true);
      await handleLoadRecentMeals();
      setGoldenResults([]);
    } finally {
      setBuilderClearing(false);
    }
  };

  const setBuilderMealIngredients = (mealId, ingredients) => {
    setBuilderMeals((prev) =>
      prev.map((m) => (m.id === mealId ? { ...m, ingredients: ingredients || [] } : m))
    );
    setBuilderEditId(null);
  };

  const meals = suite?.meals || [];
  const passedCount = Object.values(results).filter((r) => r?.passed).length;
  const failedCount = Object.values(results).filter((r) => r && !r.passed).length;
  const hasResults = Object.keys(results).length > 0;

  return (
    <div className="p-8 bg-gray-50 min-h-screen">
      <div className="flex items-center justify-between mb-4">
        <button
          onClick={() => navigate("/")}
          className="text-blue-500 underline"
        >
          Back to Dashboard
        </button>
      </div>

      <h1 className="text-2xl font-bold mb-2">Regression Suite</h1>
      <p className="text-sm text-gray-600 mb-4">
        Uses REGRESSION_MODE (temp 0). Restart Parse API after code changes.
      </p>
      <p className="text-xs text-amber-700 mb-4">
        Path mismatch: Regression is text-only. Production has classifier, image, pantry, learned corrections. Some production bugs may not reproduce.
      </p>

      {loading && <p className="text-gray-500">Loading suite...</p>}
      {error && (
        <p className="text-red-600 mb-4">
          {error} — Ensure Parse API is running and regression_meals.json exists.
        </p>
      )}

      {suite && (
        <>
          <h2 className="text-xl font-semibold mb-2">Golden set builder</h2>
          <p className="text-sm text-gray-600 mb-3">
            Load recent meals, then add selected ones to the golden set (or clear and start over). Use mealId so the same meal is not added twice.
          </p>
          <div className="flex flex-wrap items-center gap-3 mb-4">
            <button
              type="button"
              onClick={handleLoadRecentMeals}
              disabled={builderLoading}
              className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-200 rounded-lg hover:bg-gray-300 disabled:opacity-50"
            >
              {builderLoading ? "Loading…" : "Load recent meals"}
            </button>
            <button
              type="button"
              onClick={handleAddSelectedToGolden}
              disabled={builderAdding || builderSelected.size === 0}
              className="px-3 py-1.5 text-sm font-medium text-amber-700 bg-amber-100 rounded-lg hover:bg-amber-200 disabled:opacity-50"
            >
              {builderAdding ? "Adding…" : `Add selected (${builderSelected.size}) to golden set`}
            </button>
            <button
              type="button"
              onClick={handleClearGoldenSet}
              disabled={builderClearing}
              className="px-3 py-1.5 text-sm font-medium text-red-700 bg-red-100 rounded-lg hover:bg-red-200 disabled:opacity-50"
            >
              {builderClearing ? "Clearing…" : "Clear golden set"}
            </button>
          </div>
          {builderMeals.length > 0 && (
            <div className="border border-gray-200 rounded-lg bg-white overflow-hidden mb-6">
              <div className="max-h-96 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-100 sticky top-0">
                    <tr>
                      <th className="text-left p-2 w-8">Add</th>
                      <th className="text-left p-2">Text</th>
                      <th className="text-left p-2 w-24">Date</th>
                      <th className="text-left p-2 w-20">Ingredients</th>
                      <th className="text-left p-2 w-24">Category</th>
                      <th className="text-left p-2 w-16">Edit</th>
                    </tr>
                  </thead>
                  <tbody>
                    {builderMeals.map((m) => (
                      <tr key={m.id} className="border-t border-gray-100 hover:bg-gray-50">
                        <td className="p-2">
                          {!m.inGoldenSet && (
                            <input
                              type="checkbox"
                              checked={builderSelected.has(m.id)}
                              onChange={() => toggleBuilderSelected(m.id)}
                            />
                          )}
                          {m.inGoldenSet && <span className="text-xs text-green-600">In set</span>}
                        </td>
                        <td className="p-2 truncate max-w-xs" title={m.text}>
                          {m.text || "(empty)"}
                        </td>
                        <td className="p-2 text-gray-500">
                          {m.timestamp ? new Date(m.timestamp).toLocaleDateString() : "—"}
                        </td>
                        <td className="p-2">{Array.isArray(m.ingredients) ? m.ingredients.length : 0}</td>
                        <td className="p-2">
                          {!m.inGoldenSet && (
                            <select
                              value={builderCategory[m.id] || "normal"}
                              onChange={(e) => setBuilderCategory((prev) => ({ ...prev, [m.id]: e.target.value }))}
                              className="text-xs border border-gray-300 rounded px-1 py-0.5"
                            >
                              <option value="easy">easy</option>
                              <option value="normal">normal</option>
                              <option value="evil">evil</option>
                            </select>
                          )}
                        </td>
                        <td className="p-2">
                          {!m.inGoldenSet && (
                            <button
                              type="button"
                              onClick={() => setBuilderEditId(m.id)}
                              className="text-xs text-blue-600 hover:underline"
                            >
                              Edit
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          {builderEditId && (
            <EditGoldenIngredientsModal
              meal={builderMeals.find((m) => m.id === builderEditId)}
              onSave={(ingredients) => setBuilderMealIngredients(builderEditId, ingredients)}
              onClose={() => setBuilderEditId(null)}
            />
          )}

          <hr className="my-8 border-gray-200" />
          <h2 className="text-xl font-semibold mb-2">Golden set (run)</h2>
          <p className="text-sm text-gray-600 mb-3">
            Run regression against the golden set (meals marked as correct outcome). Pass = same ingredient count/names and production checks.
          </p>
          <div className="flex items-center gap-3 mb-4">
            <button
              type="button"
              onClick={handleRunGoldenSet}
              disabled={goldenRunning}
              className="px-3 py-1.5 text-sm font-medium text-amber-700 bg-amber-100 rounded-lg hover:bg-amber-200 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {goldenRunning ? "Running…" : "Run golden set"}
            </button>
            {goldenResults.length > 0 && (
              <span className="text-sm text-gray-600">
                {goldenResults.filter((r) => r.passed).length} passed, {goldenResults.filter((r) => !r.passed).length} failed
              </span>
            )}
          </div>
          <div className="space-y-2">
            {goldenResults.map((r) => {
              const isExpanded = goldenExpandedId === r.id;
              return (
                <div
                  key={r.id}
                  className="border border-gray-200 rounded-lg bg-white overflow-hidden"
                >
                  <div
                    className="flex items-center gap-3 p-3 cursor-pointer hover:bg-gray-50"
                    onClick={() => setGoldenExpandedId(isExpanded ? null : r.id)}
                  >
                    <span
                      className={`w-16 shrink-0 text-xs font-medium px-2 py-0.5 rounded ${
                        r.passed ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"
                      }`}
                    >
                      {r.passed ? "PASS" : "FAIL"}
                    </span>
                    <span className="flex-1 truncate text-sm" title={r.text}>
                      {r.text || "(empty)"}
                    </span>
                    <span className="text-xs text-gray-500">{r.id}</span>
                  </div>
                  {isExpanded && (
                    <div className="border-t border-gray-200 p-4 bg-gray-50 text-sm space-y-3">
                      {r.failures?.length > 0 && (
                        <div>
                          <div className="font-medium text-red-700 mb-1">Failures</div>
                          <ul className="list-disc list-inside text-red-700 space-y-0.5">
                            {r.failures.map((f, i) => (
                              <li key={i}>{f}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {r.actualIngredients?.length > 0 && (
                        <div>
                          <div className="font-medium text-gray-700 mb-1">Actual ingredients</div>
                          <ul className="space-y-2 text-gray-600">
                            {r.actualIngredients.map((ing, i) => {
                              const nutrients = getNutrients(ing);
                              const parts = [];
                              if (nutrients.calories != null) parts.push(`Cal: ${Math.round(nutrients.calories)}`);
                              if (nutrients.protein != null) parts.push(`P: ${nutrients.protein}g`);
                              if (nutrients.carbs != null) parts.push(`C: ${nutrients.carbs}g`);
                              if (nutrients.fat != null) parts.push(`F: ${nutrients.fat}g`);
                              if (nutrients.fiber_g != null) parts.push(`Fiber: ${nutrients.fiber_g}g`);
                              if (nutrients.sugar_g != null) parts.push(`Sugar: ${nutrients.sugar_g}g`);
                              if (nutrients.sodium_mg != null) parts.push(`Na: ${nutrients.sodium_mg}mg`);
                              if (nutrients.caffeine_mg != null) parts.push(`Caff: ${nutrients.caffeine_mg}mg`);
                              return (
                                <li key={i} className="border-b border-gray-100 pb-2 last:border-0 last:pb-0">
                                  {ing.name} — {ing.quantity} {ing.unit} (source: {ing.source || "?"})
                                  {ing.usda_matched_name && (
                                    <span className="text-gray-500 text-xs block">USDA: {ing.usda_matched_name}</span>
                                  )}
                                  {parts.length > 0 && (
                                    <span className="text-gray-500 text-xs block">{parts.join(" · ")}</span>
                                  )}
                                </li>
                              );
                            })}
                          </ul>
                        </div>
                      )}
                      {r.nutrientDetails?.length > 0 && (
                        <div>
                          <div className="font-medium text-gray-700 mb-1">Nutrient comparison (expected vs actual)</div>
                          <div className="space-y-3">
                            {r.nutrientDetails.map((nd, idx) => (
                              <div key={idx} className="border border-gray-200 rounded p-2 bg-white">
                                <div className="font-medium text-gray-800 text-xs mb-1">{nd.ingredientName}</div>
                                <div className="flex flex-wrap gap-2">
                                  {nd.nutrients?.map((n, j) => (
                                    <span
                                      key={j}
                                      className={`text-xs px-2 py-0.5 rounded ${
                                        n.passed ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"
                                      }`}
                                      title={n.passed ? "pass" : "fail"}
                                    >
                                      {n.key}: {n.expected} → {n.actual != null ? n.actual : "—"} {n.passed ? "✓" : "✗"}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                      {r.expectedIngredients?.length > 0 && (
                        <details className="text-xs text-gray-500">
                          <summary className="cursor-pointer font-medium text-gray-600">Expected ingredients (reference)</summary>
                          <ul className="mt-1 space-y-0.5 list-disc list-inside">
                            {r.expectedIngredients.map((ing, i) => (
                              <li key={i}>{ing.name} — {ing.quantity} {ing.unit}</li>
                            ))}
                          </ul>
                        </details>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <hr className="my-8 border-gray-200" />
          <h2 className="text-xl font-semibold mb-2">Regression suite (fixed meals)</h2>
          <p className="text-sm text-gray-600 mb-4">
            Uses regression_meals.json. Run All to parse each meal and evaluate expectations.
          </p>
          <div className="flex items-center gap-3 mb-4">
            <button
              type="button"
              onClick={handleRunAll}
              disabled={running || meals.length === 0}
              className="px-3 py-1.5 text-sm font-medium text-blue-700 bg-blue-100 rounded-lg hover:bg-blue-200 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {running ? "Running…" : "Run All"}
            </button>
            {hasResults && (
              <span className="text-sm text-gray-600">
                {passedCount} passed, {failedCount} failed
              </span>
            )}
          </div>

          {running && progress.total > 0 && (
            <div className="mb-4 w-full max-w-md">
              <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                <div
                  className="h-full bg-blue-500 rounded-full transition-all duration-300"
                  style={{
                    width: `${(progress.current / progress.total) * 100}%`,
                  }}
                />
              </div>
              <span className="text-xs text-gray-600">
                Meal {progress.current} of {progress.total}
              </span>
            </div>
          )}

          <div className="space-y-2">
            {meals.map((meal) => {
              const r = results[meal.id];
              const isExpanded = expandedId === meal.id;

              return (
                <div
                  key={meal.id}
                  className="border border-gray-200 rounded-lg bg-white overflow-hidden"
                >
                  <div
                    className="flex items-center gap-3 p-3 cursor-pointer hover:bg-gray-50"
                    onClick={() => setExpandedId(isExpanded ? null : meal.id)}
                  >
                    <span
                      className={`w-16 shrink-0 text-xs font-medium px-2 py-0.5 rounded ${
                        r === undefined
                          ? "bg-gray-200 text-gray-600"
                          : r.passed
                          ? "bg-green-100 text-green-800"
                          : "bg-red-100 text-red-800"
                      }`}
                    >
                      {r === undefined ? "—" : r.passed ? "PASS" : "FAIL"}
                    </span>
                    <span className="flex-1 truncate text-sm" title={meal.text}>
                      {meal.text || "(empty)"}
                    </span>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleRunOne(meal);
                      }}
                      disabled={running}
                      className="text-xs text-blue-600 hover:underline disabled:opacity-50"
                    >
                      Run
                    </button>
                  </div>

                  {isExpanded && (
                    <div className="border-t border-gray-200 p-4 bg-gray-50 text-sm space-y-3">
                      {meal.note && (
                        <p className="text-gray-600 italic">Note: {meal.note}</p>
                      )}
                      {r?.failures?.length > 0 && (
                        <div>
                          <div className="font-medium text-red-700 mb-1">
                            Failures
                          </div>
                          <ul className="list-disc list-inside text-red-700 space-y-0.5">
                            {r.failures.map((f, i) => (
                              <li key={i}>{f}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {r?.ingredients?.length > 0 && (
                        <div>
                          <div className="font-medium text-gray-700 mb-1">
                            Parsed ingredients
                          </div>
                          <ul className="space-y-2 text-gray-600">
                            {r.ingredients.map((ing, i) => {
                              const nutrients = getNutrients(ing);
                              const parts = [];
                              if (nutrients.calories != null) parts.push(`Cal: ${Math.round(nutrients.calories)}`);
                              if (nutrients.protein != null) parts.push(`P: ${nutrients.protein}g`);
                              if (nutrients.carbs != null) parts.push(`C: ${nutrients.carbs}g`);
                              if (nutrients.fat != null) parts.push(`F: ${nutrients.fat}g`);
                              if (nutrients.fiber_g != null) parts.push(`Fiber: ${nutrients.fiber_g}g`);
                              if (nutrients.sugar_g != null) parts.push(`Sugar: ${nutrients.sugar_g}g`);
                              if (nutrients.sodium_mg != null) parts.push(`Na: ${nutrients.sodium_mg}mg`);
                              if (nutrients.caffeine_mg != null) parts.push(`Caff: ${nutrients.caffeine_mg}mg`);
                              return (
                                <li key={i} className="border-b border-gray-100 pb-2 last:border-0 last:pb-0">
                                  <span>
                                    {ing.name} — {ing.quantity} {ing.unit} (source: {ing.source || "?"})
                                    {ing.usda_matched_name && (
                                      <span className="text-gray-500 text-xs ml-1">
                                        USDA: {ing.usda_matched_name}
                                      </span>
                                    )}
                                  </span>
                                  {parts.length > 0 && (
                                    <span className="text-gray-500 text-xs block mt-0.5">
                                      {parts.join(" · ")}
                                    </span>
                                  )}
                                </li>
                              );
                            })}
                          </ul>
                        </div>
                      )}
                      {r?.checkDetails?.length > 0 && (
                        <div>
                          <div className="font-medium text-gray-700 mb-1">
                            Check results
                          </div>
                          <ul className="space-y-1">
                            {r.checkDetails.map((c, i) => (
                              <li
                                key={i}
                                className={`text-xs px-2 py-1 rounded inline-block mr-1 mb-1 ${
                                  c.passed ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"
                                }`}
                              >
                                {c.checkType}: {typeof c.expected === "object" && c.expected != null
                                  ? JSON.stringify(c.expected)
                                  : String(c.expected)}{" "}
                                → {typeof c.actual === "object" && c.actual != null
                                  ? JSON.stringify(c.actual)
                                  : String(c.actual)}{" "}
                                {c.passed ? "✓" : "✗"}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

        </>
      )}
    </div>
  );
}

function EditGoldenIngredientsModal({ meal, onSave, onClose }) {
  const [raw, setRaw] = useState(
    () => (meal?.ingredients ? JSON.stringify(meal.ingredients, null, 2) : "[]")
  );
  const [error, setError] = useState(null);

  const handleSave = () => {
    setError(null);
    try {
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) throw new Error("Must be a JSON array");
      onSave(parsed);
    } catch (e) {
      setError(e.message || "Invalid JSON");
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl max-w-2xl w-full max-h-[80vh] flex flex-col p-4">
        <div className="flex justify-between items-center mb-2">
          <h3 className="text-lg font-semibold">Edit ingredients (JSON)</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            ✕
          </button>
        </div>
        <p className="text-xs text-gray-500 mb-2 truncate" title={meal?.text}>
          {meal?.text || ""}
        </p>
        <textarea
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
          className="flex-1 min-h-[200px] font-mono text-sm border border-gray-300 rounded p-2"
          spellCheck={false}
        />
        {error && <p className="text-sm text-red-600 mt-1">{error}</p>}
        <div className="flex gap-2 mt-3">
          <button
            type="button"
            onClick={handleSave}
            className="px-3 py-1.5 text-sm font-medium text-white bg-amber-500 rounded-lg hover:bg-amber-600"
          >
            Save
          </button>
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-200 rounded-lg hover:bg-gray-300"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
