export async function login(email, password) {
  const res = await fetch("http://127.0.0.1:8090/api/collections/users/auth-with-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ identity: email, password })
  });

  if (!res.ok) {
    throw new Error("Login failed");
  }

  const data = await res.json();
  // data.token = JWT, data.record = user info
  return data;
}
