import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { fetchMeals, fetchIngredients } from "./api";

export default function DayDetail() {
  const { date } = useParams();
  const navigate = useNavigate();
  const [meals, setMeals] = useState([]);
  const [totals, setTotals] = useState({ calories: 0 });

  useEffect(() => {
    async function load() {
      const allMeals = await fetchMeals();
      console.log("Fetched meals:", allMeals.map(m => ({ id: m.id, text: m.text })));
      const dayMeals = allMeals.filter(
        (m) => new Date(m.timestamp).toISOString().split("T")[0] === date
      );
      setMeals(dayMeals);

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
      <button
        onClick={() => navigate(-1)}
        className="text-blue-500 underline mb-4"
      >
        ← Back
      </button>
      <h1 className="text-2xl font-bold mb-4">{date}</h1>

      <div className="bg-white p-4 rounded-xl shadow mb-6">
        <p className="font-semibold">Approx. Calories: {Math.round(totals.calories)}</p>
      </div>

      {meals.map((meal) => (
  <MealCard key={meal.id} meal={meal} />))}


      
    </div>
  );
}

function MealCard({ meal }) {
  const [ingredients, setIngredients] = useState([]);

  useEffect(() => {
    async function loadIngredients() {
      console.log("🔍 Fetching ingredients for meal:", meal.id, meal.text);
      const ings = await fetchIngredients(meal.id);
      console.log("✅ Ingredients response:", ings);
      setIngredients(ings);
    }
    loadIngredients();
  }, [meal.id]);

  return (
    <div className="bg-white p-4 rounded-xl shadow mb-4">
      <h2 className="font-semibold mb-1">{meal.text || "(no text)"}</h2>
      <p className="text-gray-500 text-sm mb-2">{meal.timestamp}</p>

      {ingredients.length === 0 ? (
        <p className="text-gray-400 italic">No ingredients found</p>
      ) : (
        <ul className="text-sm text-gray-700 list-disc ml-5">
            {ingredients.map((ing) => {
                const nutrients = Array.isArray(ing.nutrition) ? ing.nutrition : [];
                const energy = nutrients.find((n) => n.nutrientName === "Energy");
                const protein = nutrients.find((n) => n.nutrientName === "Protein");
                const carbs = nutrients.find((n) => n.nutrientName.includes("Carbohydrate"));
                const fat = nutrients.find((n) => n.nutrientName.includes("Total lipid"));

    return (
      <li key={ing.id}>
        <span className="font-medium">{ing.name}</span>
        {energy || protein || carbs || fat ? (
          <>
            {" — "}
            {energy ? `${energy.value} kcal` : ""}
            {protein ? ` | ${protein.value}g protein` : ""}
            {carbs ? ` | ${carbs.value}g carbs` : ""}
            {fat ? ` | ${fat.value}g fat` : ""}
          </>
        ) : (
          " — no nutrition data"
        )}
      </li>
    );
  })}
</ul>

      )}
    </div>
  );
}
