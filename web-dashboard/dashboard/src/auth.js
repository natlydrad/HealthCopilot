const PB_BASE = "https://pocketbase-1j2x.onrender.com";

export async function login(email, password) {
  const res = await fetch(`${PB_BASE}/api/collections/users/auth-with-password`, {
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

export async function signup(email, password) {
  const res = await fetch(`${PB_BASE}/api/collections/users/records`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ 
      email, 
      password,
      passwordConfirm: password 
    })
  });

  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.message || "Signup failed");
  }

  // After signup, log them in automatically
  return login(email, password);
}
