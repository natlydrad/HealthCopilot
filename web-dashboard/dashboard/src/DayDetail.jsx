import { useEffect, useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { fetchMealsForDateRange, fetchIngredients, correctIngredient, updateIngredientWithNutrition, getLearnedPatterns, getCorrections, getLearningStats, parseAndSaveMeal, deleteCorrection, clearMealIngredients, sendCorrectionMessage, saveCorrection } from "./api";

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
        <MealCard key={meal.id} meal={meal} />
      ))}

      {/* Learning Panel */}
      {showLearning && (
        <LearningPanel onClose={() => setShowLearning(false)} />
      )}
    </div>
  );
}

function MealCard({ meal }) {
  const [ingredients, setIngredients] = useState([]);
  const [correcting, setCorrecting] = useState(null);
  const [parsing, setParsing] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    async function loadIngredients() {
      console.log("🔍 Fetching ingredients for meal:", meal.id, meal.text);
      const ings = await fetchIngredients(meal.id);
      console.log("✅ Ingredients response:", ings);
      setIngredients(ings);
      setLoaded(true);
    }
    loadIngredients();
  }, [meal.id]);

  // Parse meal on demand (works with text OR images via backend API)
  const handleParse = async () => {
    if (!meal.text?.trim() && !meal.image) return;
    setParsing(true);
    try {
      const saved = await parseAndSaveMeal(meal);
      setIngredients(saved);
    } catch (err) {
      console.error("Parse failed:", err);
    } finally {
      setParsing(false);
    }
  };

  // Clear all ingredients for this meal
  const handleClear = async () => {
    if (!confirm("Delete all parsed ingredients for this meal?")) return;
    setClearing(true);
    try {
      await clearMealIngredients(meal.id);
      setIngredients([]);
    } catch (err) {
      console.error("Clear failed:", err);
    } finally {
      setClearing(false);
    }
  };

  // Check if this meal needs parsing (either text or image)
  const hasContent = meal.text?.trim() || meal.image;
  const needsParsing = loaded && ingredients.length === 0 && hasContent;

  // Build image URL if meal has an image
  const imageUrl = meal.image ? 
    `https://pocketbase-1j2x.onrender.com/api/files/meals/${meal.id}/${meal.image}` : null;

  return (
    <div className="bg-white p-4 rounded-xl shadow mb-4">
      <div className="flex gap-4">
        {/* Image thumbnail if exists */}
        {imageUrl && (
          <img 
            src={imageUrl} 
            alt="Meal" 
            className="w-20 h-20 object-cover rounded-lg flex-shrink-0"
          />
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

      {/* Needs parsing state */}
      {needsParsing && !parsing && (
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

            return (
              <li 
                key={ing.id}
                onClick={() => setCorrecting(ing)}
                className={`flex items-center gap-2 p-2 rounded-lg cursor-pointer transition-colors
                  ${lowConf ? 'bg-amber-50 hover:bg-amber-100' : 'hover:bg-gray-50'}`}
              >
                {/* Low confidence indicator */}
                {lowConf && (
                  <span className="text-amber-500 text-xs" title="Tap to correct">?</span>
                )}
                
                <span className="font-medium">{ing.name}</span>
                
                {/* Source badge */}
                <span className={`text-[10px] px-1.5 py-0.5 rounded ${sourceInfo.color}`}>
                  {sourceInfo.label}
                </span>
                
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
                
                {/* Edit hint */}
                <span className="text-gray-300 text-xs">tap to edit</span>
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
          onSave={(correction) => {
            // Update local state optimistically
            setIngredients(prev => prev.map(i => 
              i.id === correcting.id ? { ...i, ...correction } : i
            ));
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
        // Auto-save after a brief delay
        setTimeout(async () => {
          await handleSave(result.correction, result.learned, result.correctionReason, result.shouldLearn);
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

  const handleSave = async (correction = pendingCorrection, learned = pendingLearned, reason = pendingReason, shouldLearn = pendingShouldLearn) => {
    if (!correction) return;

    setMessages(prev => [...prev, { from: "bot", text: "Saving your correction..." }]);

    try {
      const result = await saveCorrection(ingredient.id, correction, learned, reason, shouldLearn, conversationHistory);
      
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
        
        setMessages(prev => [...prev, { 
          from: "bot", 
          text: `Done! Updated to ${correction.name || ingredient.name} (${correction.quantity || ingredient.quantity} ${correction.unit || ingredient.unit}).${learnedMsg}` 
        }]);

        // Close after brief delay
        setTimeout(() => onSave(result.ingredient), 1500);
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
  const [recentCorrections, setRecentCorrections] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('patterns'); // patterns | timeline | history

  useEffect(() => {
    async function load() {
      try {
        const [p, c, s] = await Promise.all([
          getLearnedPatterns(),
          getCorrections(50),
          getLearningStats()
        ]);
        setPatterns(p);
        setRecentCorrections(c);
        setStats(s);
      } catch (err) {
        console.error("Failed to load learning data:", err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

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
            { id: 'history', label: 'History' },
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
                      {patterns.map((p, i) => (
                        <div key={i} className="flex items-center justify-between bg-gray-50 p-3 rounded-lg">
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

              {/* History Tab */}
              {activeTab === 'history' && (
                <div>
                  {recentCorrections.length === 0 ? (
                    <p className="text-gray-400 text-sm text-center py-8">No corrections yet.</p>
                  ) : (
                    <div className="space-y-2">
                      {recentCorrections.map((c, i) => (
                        <div key={c.id || i} className="text-sm bg-gray-50 p-3 rounded-lg">
                          <div className="flex justify-between items-start">
                            <div className="flex-1">
                              <span className="text-gray-500">{c.originalParse?.name}</span>
                              <span className="mx-2">→</span>
                              <span className="font-medium">{c.userCorrection?.name}</span>
                            </div>
                            <div className="flex items-center gap-2">
                              <span className="text-xs text-gray-400 whitespace-nowrap">
                                {new Date(c.created).toLocaleString()}
                              </span>
                              {/* Delete button */}
                              <button
                                onClick={async (e) => {
                                  e.stopPropagation();
                                  if (confirm("Delete this correction? The system will 'unlearn' this.")) {
                                    try {
                                      await deleteCorrection(c.id);
                                      setRecentCorrections(prev => prev.filter(x => x.id !== c.id));
                                      // Refresh stats
                                      const [p, s] = await Promise.all([getLearnedPatterns(), getLearningStats()]);
                                      setPatterns(p);
                                      setStats(s);
                                    } catch (err) {
                                      console.error("Failed to delete:", err);
                                    }
                                  }
                                }}
                                className="text-red-400 hover:text-red-600 text-xs"
                                title="Delete correction"
                              >
                                ✕
                              </button>
                            </div>
                          </div>
                          <div className="flex flex-wrap gap-1 mt-1">
                            {/* Correction type badge */}
                            {c.correctionType && (
                              <span className="text-xs bg-gray-200 text-gray-600 px-2 py-0.5 rounded">
                                {c.correctionType.replace('_', ' ')}
                              </span>
                            )}
                            {/* Context badges */}
                            {c.context?.mealType && (
                              <span className="text-xs bg-blue-100 text-blue-600 px-2 py-0.5 rounded">
                                {c.context.mealType}
                              </span>
                            )}
                            {c.context?.hourOfDay !== undefined && (
                              <span className="text-xs bg-purple-100 text-purple-600 px-2 py-0.5 rounded">
                                {c.context.hourOfDay}:00
                              </span>
                            )}
                          </div>
                          {/* Meal text preview */}
                          {c.context?.mealText && (
                            <p className="text-xs text-gray-400 mt-1 truncate" title={c.context.mealText}>
                              from: "{c.context.mealText}"
                            </p>
                          )}
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
