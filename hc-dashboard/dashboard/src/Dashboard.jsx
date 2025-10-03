import { useEffect, useState } from "react";
import { fetchMeals } from "./api";

export default function Dashboard() {
  const [meals, setMeals] = useState([]);

  useEffect(() => {
    fetchMeals().then(setMeals);
  }, []);

  return (
    <div className="p-8 bg-gray-100 min-h-screen">
      <h1 className="text-3xl font-bold mb-6">HealthCopilot Dashboard</h1>

      <div className="p-6 bg-white rounded-xl shadow">
        <h2 className="font-semibold text-lg">🍽 Meals</h2>
        <ul className="list-disc ml-6 mt-2">
          {meals.map((m) => (
            <li key={m.id}>
              {m.text || "(no text)"} — {m.timestamp}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
