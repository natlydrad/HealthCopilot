export async function fetchMeals() {
  const res = await fetch("http://127.0.0.1:8090/api/collections/meals/records");
  const data = await res.json();
  return data.items;
}