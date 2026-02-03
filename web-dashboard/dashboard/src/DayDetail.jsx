import { useEffect, useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { fetchMealsForDateRange, fetchIngredients, fetchHasNonFoodLogs, correctIngredient, updateIngredientWithNutrition, getLearnedPatterns, getLearningStats, removeLearnedPattern, parseAndSaveMeal, clearMealIngredients, clearNonFoodClassification, sendCorrectionMessage, saveCorrection, getParseApiUrl } from "./api";

// Determine if an ingredient is low confidence (needs review)
function isLowConfidence(ing) {
  // No USDA match = GPT guessed it
  if (!ing.usdaCode) return true;
  // Source is explicitly GPT without USDA validation
  if (ing.source === "gpt" && !ing.nutrition?.length) return true;
  return false;
}

export default function DayDetail() {
  const { date } = useParams();
  const navigate = useNavigate();
  const [meals, setMeals] = useState([]);
  const [totals, setTotals] = useState({ calories: 0 });
  const [showLearning, setShowLearning] = useState(false);

  useEffect(() => {
    async function load() {
      // Fetch meals for this specific day only
      const dayMeals = await fetchMealsForDateRange(date, date);
      
      // Sort by timestamp (earliest first for chronological order)
      const parseTimestamp = (ts) => {
        if (!ts) return 0;
        return new Date(ts.replace(' ', 'T')).getTime() || 0;
      };
      
      const sortedMeals = [...dayMeals].sort((a, b) => parseTimestamp(a.timestamp) - parseTimestamp(b.timestamp));
      
      console.log(`📅 ${date}: ${sortedMeals.length} meals loaded`);
      setMeals(sortedMeals);

      let totalCals = 0;
      for (const meal of dayMeals) {
        const ingredients = await fetchIngredients(meal.id);
        for (const ing of ingredients) {
            let nutritionData = ing.nutrition;
            if (typeof nutritionData === "string") {
                try {
                nutritionData = JSON.parse(nutritionData);
                } catch {
                nutritionData = null;
                }
            }
            if (Array.isArray(ing.nutrition)) {
                const energy = ing.nutrition.find((n) => n.nutrientName === "Energy");
                if (energy && energy.value) {
                    totalCals += parseFloat(energy.value);
                }
                }

            }

      }
      setTotals({ calories: totalCals });
    }
    load();
  }, [date]);

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

      <div className="bg-white p-4 rounded-xl shadow mb-6">
        <p className="font-semibold">Approx. Calories: {Math.round(totals.calories)}</p>
      </div>

      {meals.map((meal) => (
        <MealCard
          key={meal.id}
          meal={meal}
          onMealUpdated={(mid, updates) =>
            setMeals((prev) => prev.map((m) => (m.id === mid ? { ...m, ...updates } : m)))
          }
        />
      ))}

      {/* Learning Panel */}
      {showLearning && (
        <LearningPanel onClose={() => setShowLearning(false)} />
      )}
    </div>
  );
}

function MealCard({ meal, onMealUpdated }) {
  const [ingredients, setIngredients] = useState([]);
  const [correcting, setCorrecting] = useState(null);
  const [parsing, setParsing] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [clearingNonFood, setClearingNonFood] = useState(false);
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
  const handleParse = async () => {
    if (!meal.text?.trim() && !meal.image) {
      setParseError("Add a caption or photo first.");
      return;
    }
    setParsing(true);
    setParseError(null);
    setClassificationResult(null);
    setEmptyParseMessage(null);
    setEmptyParseReason(null);
    try {
      const result = await parseAndSaveMeal(meal);
      const data = result?.ingredients !== undefined ? result : { ingredients: result, classificationResult: null };
      const ingredientsList = Array.isArray(data.ingredients) ? data.ingredients : [];
      setIngredients(ingredientsList);
      setClassificationResult(data.classificationResult || null);
      if (data.classificationResult === "not_food" || data.isFood === false) {
        setHasNonFoodLogs(true);
        onMealUpdated?.(meal.id, { isFood: false });
      }
      if (ingredientsList.length === 0 && data.classificationResult !== "not_food") {
        let msg = result?.message || "No ingredients detected. Add a caption or try a clearer photo.";
        if (result?.source === "gpt_image" && msg.includes("No ingredients detected")) {
          msg += " If this meal has a photo, the image may not have loaded — restart or redeploy the Parse API, or add a short caption and parse again.";
        }
        setEmptyParseMessage(msg);
        setEmptyParseReason(result?.reason || null);
      }
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
    try {
      await clearMealIngredients(meal.id);
      setIngredients([]);
    } catch (err) {
      console.error("Clear failed:", err);
      alert(`Clear failed: ${err.message}`);
    } finally {
      setClearing(false);
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

      {/* Ingredients list */}
      {ingredients.length > 0 && (
        <div>
          <div className="flex justify-between items-center mb-2">
            <span className="text-xs text-gray-400">{ingredients.length} ingredient{ingredients.length !== 1 ? 's' : ''}</span>
            <button
              onClick={handleClear}
              disabled={clearing}
              className="text-xs text-red-400 hover:text-red-600 disabled:opacity-50"
            >
              {clearing ? "Clearing..." : "🗑️ Clear"}
            </button>
          </div>
          <ul className="text-sm text-gray-700 space-y-1">
          {ingredients.map((ing) => {
            const nutrients = Array.isArray(ing.nutrition) ? ing.nutrition : [];
            const energy = nutrients.find((n) => n.nutrientName === "Energy");
            const protein = nutrients.find((n) => n.nutrientName === "Protein");
            const carbs = nutrients.find((n) => n.nutrientName.includes("Carbohydrate"));
            const fat = nutrients.find((n) => n.nutrientName.includes("Total lipid"));
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
                className={`rounded-lg transition-colors ${lowConf ? 'bg-amber-50' : ''}`}
              >
                <div
                  onClick={() => setCorrecting(ing)}
                  className={`flex items-center gap-2 p-2 cursor-pointer ${lowConf ? 'hover:bg-amber-100' : 'hover:bg-gray-50'}`}
                >
                  {/* Low confidence indicator */}
                  {lowConf && (
                    <span 
                      className="text-amber-500 text-xs" 
                      title={ing.parsingMetadata?.partialLabel 
                        ? "Label was partially visible – nutrition from USDA. Re-photo with full label for exact values." 
                        : "Tap to correct"}
                    >
                      ?
                    </span>
                  )}
                  
                  <span className="font-medium">{ing.name}</span>
                  
                  {/* Source badge */}
                  <span className={`text-[10px] px-1.5 py-0.5 rounded ${sourceInfo.color}`}>
                    {sourceInfo.label}
                  </span>
                  {ing.parsingMetadata?.partialLabel && (
                    <span 
                      className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-700"
                      title="Label was partially visible – nutrition from USDA. Re-photo with full label for exact values."
                    >
                      Partial label
                    </span>
                  )}
                  
                  {ing.quantity && ing.unit && (
                    <span className="text-gray-400 text-xs">
                      ({ing.quantity} {ing.unit})
                    </span>
                  )}
                  
                  {energy || protein || carbs || fat ? (
                    <span className="text-gray-500 text-xs ml-auto">
                      {energy ? `${Math.round(energy.value)} cal` : ""}
                      {protein ? ` · ${Math.round(protein.value)}g P` : ""}
                    </span>
                  ) : (
                    <span className="text-gray-400 text-xs ml-auto italic">no data</span>
                  )}
                  
                  {/* View nutrients toggle */}
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); setExpandedNutrientId(showNutrients ? null : ing.id); }}
                    className="text-[10px] text-gray-400 hover:text-gray-600"
                  >
                    {showNutrients ? "▼ Nutrients" : "▶ Nutrients"}
                  </button>
                  <span className="text-gray-300 text-xs">tap to edit</span>
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
            // missing_item: add new ingredient, keep current unchanged
            if (result.addedIngredient) {
              setIngredients(prev => [...prev, result.addedIngredient]);
              // Refetch so list is in sync with server (ensures new item shows)
              fetchIngredients(meal.id).then((ings) => setIngredients(ings)).catch(() => {});
            } else if (result.ingredient) {
              // Normal correction: update this ingredient
              setIngredients(prev => prev.map(i => 
                i.id === correcting.id ? { ...i, ...result.ingredient } : i
              ));
            }
            setCorrecting(null);
          }}
        />
      )}
    </div>
  );
}

// Natural language correction chat component
function CorrectionChat({ ingredient, meal, onClose, onSave }) {
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [pendingCorrection, setPendingCorrection] = useState(null);
  const [pendingLearned, setPendingLearned] = useState(null);
  const [pendingReason, setPendingReason] = useState(null);
  const [pendingShouldLearn, setPendingShouldLearn] = useState(false);
  const [conversationHistory, setConversationHistory] = useState([]);
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
    const greeting = `I identified this as **${ingredient.name}** (${ingredient.quantity || '?'} ${ingredient.unit || 'serving'}).

**My reasoning:** ${reasoning}

What would you like to change? You can tell me naturally, like "that's actually banana peppers" or "it was more like 4 oz".`;
    
    setMessages([{ from: "bot", text: greeting }]);
  }, [ingredient, reasoning]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!inputValue.trim() || loading) return;

    const userMessage = inputValue.trim();
    setInputValue("");
    
    // Add user message to UI
    setMessages(prev => [...prev, { from: "user", text: userMessage }]);
    setLoading(true);

    try {
      // Send to correction API
      const result = await sendCorrectionMessage(
        ingredient.id,
        userMessage,
        conversationHistory
      );

      // Add bot response
      setMessages(prev => [...prev, { from: "bot", text: result.reply }]);

      // Update conversation history for context
      setConversationHistory(prev => [
        ...prev,
        { role: "user", content: userMessage },
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

      // If complete, show save button
      if (result.complete && result.correction) {
        const updatedConversation = [
          ...conversationHistory,
          { role: "user", content: userMessage },
          { role: "assistant", content: result.reply }
        ];
        setTimeout(async () => {
          await handleSave(result.correction, result.learned, result.correctionReason, result.shouldLearn, updatedConversation);
        }, 500);
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
        
        const doneMsg = result.addedIngredient
          ? `Done! Added ${result.addedIngredient.name} (${result.addedIngredient.quantity || 1} ${result.addedIngredient.unit || "serving"}) as a new ingredient. ${ingredient.name} was left unchanged.${learnedMsg}${usdaMsg}`
          : `Done! Updated to ${correction.name || ingredient.name} (${correction.quantity || ingredient.quantity} ${correction.unit || ingredient.unit}).${learnedMsg}${usdaMsg}`;
        setMessages(prev => [...prev, { from: "bot", text: doneMsg }]);

        // Close after brief delay; pass full result so parent can add new ingredient or update existing
        setTimeout(() => onSave(result), 1500);
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
          {loading && (
            <div className="flex justify-start">
              <div className="bg-gray-100 text-gray-500 px-4 py-2 rounded-2xl rounded-bl-md">
                Thinking...
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="p-4 border-t bg-gray-50">
          <form onSubmit={handleSubmit} className="flex gap-2">
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Tell me what to correct..."
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
          
          {/* Quick suggestions */}
          <div className="flex flex-wrap gap-2 mt-2">
            <button
              onClick={() => setInputValue("That's not what this is")}
              className="text-xs px-3 py-1 bg-white border rounded-full hover:bg-gray-50"
            >
              Wrong item
            </button>
            <button
              onClick={() => setInputValue("The amount is wrong")}
              className="text-xs px-3 py-1 bg-white border rounded-full hover:bg-gray-50"
            >
              Wrong amount
            </button>
            <button
              onClick={() => {
                setMessages(prev => [...prev, { from: "bot", text: "No changes needed. Closing..." }]);
                setTimeout(onClose, 1000);
              }}
              className="text-xs px-3 py-1 bg-green-50 border-green-200 border rounded-full text-green-700 hover:bg-green-100"
            >
              Looks correct
            </button>
          </div>
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
