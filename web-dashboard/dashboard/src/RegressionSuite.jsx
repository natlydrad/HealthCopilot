import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchRegressionSuite, runRegressionMeal } from "./api";

const REGRESSION_CONCURRENCY = 3;

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
        };
      } else {
        next[meal.id] = {
          passed: false,
          failures: [r?.reason?.message || "Request failed"],
          ingredients: [],
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
        },
      }));
      setExpandedId(meal.id);
    } finally {
      setRunning(false);
    }
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
                          <ul className="space-y-0.5 text-gray-600">
                            {r.ingredients.map((ing, i) => (
                              <li key={i}>
                                {ing.name} — {ing.quantity} {ing.unit} (source:{" "}
                                {ing.source || "?"})
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
