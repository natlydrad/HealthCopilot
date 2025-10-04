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
      const dayMeals = allMeals.filter(
        (m) => new Date(m.timestamp).toISOString().split("T")[0] === date
      );
      setMeals(dayMeals);

      let totalCals = 0;
      for (const meal of dayMeals) {
        const ingredients = await fetchIngredients(meal.id);
        for (const ing of ingredients) {
          if (ing.nutrition && ing.nutrition.calories) {
            totalCals += parseFloat(ing.nutrition.calories);
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
        <div key={meal.id} className="bg-white p-4 rounded-xl shadow mb-4">
          <h2 className="font-semibold">{meal.text || "(no text)"}</h2>
          <p className="text-gray-500 text-sm">{meal.timestamp}</p>
        </div>
      ))}
    </div>
  );
}
