import { Outlet, Link, useLocation } from "react-router-dom";

export default function PlaygroundLayout() {
  const location = useLocation();
  const base = "/play";

  return (
    <div className="min-h-screen bg-[#f5f0e8]">
      {/* Top bar: back to real dashboard + nav */}
      <header className="sticky top-0 z-10 border-b border-amber-200/60 bg-white/80 backdrop-blur-sm">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <Link
            to="/"
            className="rounded-xl bg-slate-100 px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-200"
          >
            ← Back to dashboard
          </Link>
          <nav className="flex items-center gap-2">
            <Link
              to={base}
              className={`rounded-xl px-3 py-2 text-sm font-medium transition ${
                location.pathname === base
                  ? "bg-amber-100 text-amber-800"
                  : "text-slate-600 hover:bg-amber-50"
              }`}
            >
              Week
            </Link>
            <Link
              to={`${base}/insights`}
              className={`rounded-xl px-3 py-2 text-sm font-medium transition ${
                location.pathname === `${base}/insights`
                  ? "bg-amber-100 text-amber-800"
                  : "text-slate-600 hover:bg-amber-50"
              }`}
            >
              Insights
            </Link>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
