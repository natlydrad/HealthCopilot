import { useEffect, useState } from "react";
import { fetchMeals } from "./api";
import { groupMealsByDay } from "./utils/groupMealsByDay";
import { useNavigate } from "react-router-dom";

export default function Dashboard() {
  const [meals, setMeals] = useState([]);
  const navigate = useNavigate();

  useEffect(() => {
    fetchMeals().then(setMeals);
  }, []);

  const grouped = groupMealsByDay(meals);

  return (
    <div className="p-8 bg-gray-100 min-h-screen">
      <h1 className="text-3xl font-bold mb-6">🍽 HealthCopilot Dashboard</h1>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Object.entries(grouped).map(([date, dayMeals]) => (
          <div
            key={date}
            className="bg-white p-6 rounded-xl shadow hover:shadow-md transition cursor-pointer"
            onClick={() => navigate(`/day/${date}`)}
          >
            <h2 className="text-xl font-semibold mb-1">{date}</h2>
            <p className="text-gray-600">{dayMeals.length} meals</p>
          </div>
        ))}
      </div>
    </div>
  );
}
