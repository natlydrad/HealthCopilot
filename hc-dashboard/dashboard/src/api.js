let authToken = null;

export function setAuthToken(token) {
  authToken = token;
}

export async function fetchMeals() {
  if (!authToken) throw new Error("Not logged in");

  const res = await fetch("http://127.0.0.1:8090/api/collections/meals/records", {
    headers: {
      Authorization: `Bearer ${authToken}`
    }
  });

  const data = await res.json();
  return data.items || [];
}

export async function fetchIngredients(mealId) {
  const res = await fetch(
    `/api/collections/ingredients/records?filter=meal='${mealId}'`
  );
  if (!res.ok) throw new Error("Failed to fetch ingredients");
  const data = await res.json();
  return data.items;
}
