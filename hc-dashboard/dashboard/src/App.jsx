import { useState } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Dashboard from "./Dashboard";
import DayDetail from "./DayDetail";
import Insights from "./Insights";  // ← NEW import
import { login } from "./auth";
import { setAuthToken } from "./api";

export default function App() {
  const [user, setUser] = useState(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  async function handleLogin(e) {
    e.preventDefault();
    try {
      const data = await login(email, password);
      setAuthToken(data.token);
      setUser(data.record);
    } catch (err) {
      alert("Login failed");
    }
  }

  if (!user) {
    return (
      <form onSubmit={handleLogin} className="p-8 max-w-sm mx-auto space-y-4">
        <h1 className="text-xl font-bold">Login</h1>
        <input
          className="border p-2 w-full"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <input
          type="password"
          className="border p-2 w-full"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button
          className="bg-blue-500 text-white px-4 py-2 rounded"
          type="submit"
        >
          Log in
        </button>
      </form>
    );
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/day/:date" element={<DayDetail />} />
        <Route path="/insights" element={<Insights />} />  {/* ← ADD THIS LINE */}
      </Routes>
    </BrowserRouter>
  );
}
