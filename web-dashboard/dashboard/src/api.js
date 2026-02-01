let authToken = null;
const PB_BASE = "https://pocketbase-1j2x.onrender.com";

export function setAuthToken(token) {
  authToken = token;
}

export async function fetchMeals() {
  if (!authToken) throw new Error("Not logged in");

  const url = `${PB_BASE}/api/collections/meals/records?perPage=200&sort=-created`;
  console.log("Fetching meals from:", url);

  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${authToken}`,
    },
  });

  const data = await res.json();
  console.log("Raw meals response:", data); // <-- log everything

  if (!data || !data.items) {
    console.warn("No 'items' field in meal data:", data);
    return [];
  }

  // Optional: sort client-side by created just to be sure
  const sorted = [...data.items].sort(
    (a, b) => new Date(b.created) - new Date(a.created)
  );
  console.log("Sorted meal IDs:", sorted.map((m) => m.id));
  return sorted;
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