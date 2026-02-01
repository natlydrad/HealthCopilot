import { useState } from "react";
import { correctIngredient, updateIngredient } from "./api";

export default function CorrectionModal({ ingredient, onClose, onSuccess }) {
  const [name, setName] = useState(ingredient.name || "");
  const [quantity, setQuantity] = useState(ingredient.quantity || 1);
  const [unit, setUnit] = useState(ingredient.unit || "");
  const [category, setCategory] = useState(ingredient.category || "food");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // Common units for dropdown
  const units = [
    "oz", "g", "grams", "cup", "cups", "tbsp", "tablespoon", 
    "tsp", "teaspoon", "piece", "pieces", "slice", "slices",
    "serving", "egg", "eggs", "pill", "pills", "capsule", "capsules"
  ];

  const categories = ["food", "drink", "supplement", "other"];

  const handleSave = async () => {
    setError("");
    setSaving(true);

    try {
      // Prepare original parse (what GPT/system parsed)
      const originalParse = {
        name: ingredient.name || "",
        quantity: ingredient.quantity || 1,
        unit: ingredient.unit || "",
        category: ingredient.category || "food",
        source: ingredient.source || "gpt",
        parsingStrategy: ingredient.parsingStrategy || "gpt",
        confidence: ingredient.confidence || null,
        rawGPT: ingredient.rawGPT || null,
        nutrition: ingredient.nutrition || [],
        macros: ingredient.macros || {},
      };

      // Prepare user correction
      const userCorrection = {
        name: name.trim(),
        quantity: parseFloat(quantity) || 1,
        unit: unit.trim(),
        category: category,
      };

      // Validate
      if (!userCorrection.name) {
        throw new Error("Ingredient name is required");
      }
      if (userCorrection.quantity <= 0) {
        throw new Error("Quantity must be greater than 0");
      }

      // Check if anything actually changed
      const hasChanges = 
        originalParse.name !== userCorrection.name ||
        originalParse.quantity !== userCorrection.quantity ||
        originalParse.unit !== userCorrection.unit ||
        originalParse.category !== userCorrection.category;

      if (!hasChanges) {
        onClose();
        return;
      }

      // Create correction record
      await correctIngredient(ingredient.id, originalParse, userCorrection);

      // Update ingredient with corrected values
      await updateIngredient(ingredient.id, {
        name: userCorrection.name,
        quantity: userCorrection.quantity,
        unit: userCorrection.unit,
        category: userCorrection.category,
      });

      // Success!
      if (onSuccess) {
        onSuccess();
      }
      onClose();
    } catch (err) {
      console.error("Correction error:", err);
      setError(err.message || "Failed to save correction");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4 shadow-xl">
        <h2 className="text-xl font-bold mb-4 text-slate-800">Correct Ingredient</h2>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded text-red-700 text-sm">
            {error}
          </div>
        )}

        <div className="space-y-4">
          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Ingredient Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="e.g., chicken"
            />
          </div>

          {/* Quantity and Unit */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Quantity
              </label>
              <input
                type="number"
                step="0.1"
                min="0"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Unit
              </label>
              <input
                type="text"
                list="units"
                value={unit}
                onChange={(e) => setUnit(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="e.g., oz"
              />
              <datalist id="units">
                {units.map((u) => (
                  <option key={u} value={u} />
                ))}
              </datalist>
            </div>
          </div>

          {/* Category */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Category
            </label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {categories.map((cat) => (
                <option key={cat} value={cat}>
                  {cat.charAt(0).toUpperCase() + cat.slice(1)}
                </option>
              ))}
            </select>
          </div>

          {/* Original values (for reference) */}
          <div className="pt-2 border-t border-slate-200">
            <p className="text-xs text-slate-500 mb-1">Original parse:</p>
            <p className="text-xs text-slate-400">
              {ingredient.name} {ingredient.quantity} {ingredient.unit || "serving"}
            </p>
          </div>
        </div>

        {/* Actions */}
        <div className="mt-6 flex gap-3 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-slate-600 hover:text-slate-800 border border-slate-300 rounded-md"
            disabled={saving}
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? "Saving..." : "Save Correction"}
          </button>
        </div>
      </div>
    </div>
  );
}
