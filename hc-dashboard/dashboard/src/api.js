let authToken = null;
const PB_BASE = "http://127.0.0.1:8090";

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
  // PocketBase filter for a relation field must use this format:
  // filter=(mealId='jmlpwbqrpq4etn8')
  const filter = encodeURIComponent(`(mealId='${mealId}')`);

  const url = `${PB_BASE}/api/collections/ingredients/records?filter=${filter}`;

  console.log("🛰 Fetching:", url);
  const res = await fetch(url);

  if (!res.ok) {
    console.error("❌ fetchIngredients failed", res.status, res.statusText);
    throw new Error("Failed to fetch ingredients");
  }

  const data = await res.json();
  console.log("📦 fetchIngredients got", data.items.length, "ingredients");
  return data.items;
}