export function groupMealsByDay(meals) {
  const grouped = {};
  for (const meal of meals) {
    const date = new Date(meal.timestamp).toISOString().split("T")[0];
    if (!grouped[date]) grouped[date] = [];
    grouped[date].push(meal);
  }
  return grouped;
}
