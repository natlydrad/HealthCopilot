import { useState } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Dashboard from "./Dashboard";
import DayDetail from "./DayDetail";
import Insights from "./Insights";
import { login, signup } from "./auth";
import { setAuthToken } from "./api";

export default function App() {
  const [user, setUser] = useState(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSignup, setIsSignup] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    try {
      const data = isSignup 
        ? await signup(email, password)
        : await login(email, password);
      setAuthToken(data.token);
      setUser(data.record);
    } catch (err) {
      setError(err.message || (isSignup ? "Signup failed" : "Login failed"));
    }
  }

  if (!user) {
    return (
      <form onSubmit={handleSubmit} className="p-8 max-w-sm mx-auto space-y-4">
        <h1 className="text-xl font-bold">{isSignup ? "Create Account" : "Login"}</h1>
        {error && <p className="text-red-500 text-sm">{error}</p>}
        <input
          className="border p-2 w-full rounded"
          placeholder="Email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <input
          type="password"
          className="border p-2 w-full rounded"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button
          className="bg-blue-500 text-white px-4 py-2 rounded w-full"
          type="submit"
        >
          {isSignup ? "Sign up" : "Log in"}
        </button>
        <p className="text-center text-sm text-gray-600">
          {isSignup ? "Already have an account?" : "Don't have an account?"}{" "}
          <button
            type="button"
            className="text-blue-500 underline"
            onClick={() => setIsSignup(!isSignup)}
          >
            {isSignup ? "Log in" : "Sign up"}
          </button>
        </p>
      </form>
    );
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/day/:date" element={<DayDetail />} />
        <Route path="/insights" element={<Insights />} />
      </Routes>
    </BrowserRouter>
  );
}
