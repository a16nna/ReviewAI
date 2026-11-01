import { NavLink, Route, Routes } from "react-router-dom";
import Landing from "./pages/Landing.jsx";
import Workspace from "./pages/Workspace.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import History from "./pages/History.jsx";
import ReviewDetail from "./pages/ReviewDetail.jsx";
import GitHubPage from "./pages/GitHubPage.jsx";
import Settings from "./pages/Settings.jsx";

const links = [["/review", "Workspace"], ["/dashboard", "Dashboard"], ["/history", "History"], ["/github", "GitHub"], ["/settings", "Settings"]];

export default function App() {
  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:bg-white focus:p-2 focus:text-black">Skip to content</a>
      <header className="border-b border-slate-800">
        <nav aria-label="Main" className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-4 py-3 text-sm">
          <NavLink to="/" className="mr-4 text-lg font-semibold text-white">ReviewAI</NavLink>
          {links.map(([to, label]) => (
            <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "text-indigo-400" : "text-slate-400 hover:text-white")}>
              {label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main id="main" className="mx-auto max-w-6xl px-4 py-6">
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/review" element={<Workspace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/history" element={<History />} />
          <Route path="/reviews/:id" element={<ReviewDetail />} />
          <Route path="/github" element={<GitHubPage />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<p>Page not found.</p>} />
        </Routes>
      </main>
    </div>
  );
}
