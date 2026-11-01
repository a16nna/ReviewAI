import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import api, { errMsg } from "../api";

const SEV = ["Critical", "High", "Medium", "Low", "Informational"];
const toRows = (o) => Object.entries(o).map(([name, value]) => ({ name, value }));

export default function Dashboard() {
  const [stats, setStats] = useState(null);
    const [err, setErr] = useState("");

  const load = () => {
    api.get("/stats").then((x) => setStats(x.data)).catch((e) => setErr(errMsg(e)));
  };
  useEffect(load, []);

  if (err) return <p role="alert">{err}</p>;
  if (!stats) return <p>Loading…</p>;
  if (stats.total_reviews === 0)
    return <div className="card text-center"><p>No reviews yet.</p><Link to="/review" className="btn mt-3 inline-block">Run your first review</Link></div>;

  const sev = SEV.map((name) => ({ name, value: stats.by_severity[name] || 0 }));
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-white">Dashboard</h1>
      <div className="grid gap-4 md:grid-cols-3">
        <div className="card"><p className="text-sm text-slate-300">Total reviews</p><p className="text-3xl font-bold text-white">{stats.total_reviews}</p></div>
        <div className="card"><p className="text-sm text-slate-300">Real findings</p><p className="text-3xl font-bold text-white">{sev.reduce((a, b) => a + b.value, 0)}</p></div>
        <div className="card"><p className="text-sm text-slate-300">Latest review</p><p className="text-lg text-white">{stats.recent[0] ? new Date(stats.recent[0].created_at + "Z").toLocaleString() : "-"}</p></div>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Chart title="Findings by severity"><BarChart data={sev}><CartesianGrid stroke="#1e293b" /><XAxis dataKey="name" stroke="#94a3b8" /><YAxis allowDecimals={false} stroke="#94a3b8" /><Tooltip /><Bar dataKey="value" fill="#6366f1" /></BarChart></Chart>
        <Chart title="Findings by category"><BarChart data={toRows(stats.by_category)}><CartesianGrid stroke="#1e293b" /><XAxis dataKey="name" stroke="#94a3b8" /><YAxis allowDecimals={false} stroke="#94a3b8" /><Tooltip /><Bar dataKey="value" fill="#22d3ee" /></BarChart></Chart>
        <Chart title="Reviews per day"><LineChart data={stats.by_day}><CartesianGrid stroke="#1e293b" /><XAxis dataKey="date" stroke="#94a3b8" /><YAxis allowDecimals={false} stroke="#94a3b8" /><Tooltip /><Line dataKey="count" stroke="#a78bfa" /></LineChart></Chart>
      </div>
      <section>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-white">Recent reviews</h2>
          <Link className="text-sm text-indigo-300 underline" to="/history">View all history</Link>
        </div>
        <ul className="space-y-1 text-sm">
          {stats.recent.map((r) => (
            <li key={r.id}><Link className="text-indigo-300 underline" to={`/reviews/${r.id}`}>{new Date(r.created_at + "Z").toLocaleString()}</Link> · {r.language} · {r.findings} finding(s){r.is_mock ? " (mock)" : ""}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function Chart({ title, children }) {
  return <div className="card"><h2 className="mb-2 text-sm font-semibold text-white">{title}</h2><ResponsiveContainer width="100%" height={220}>{children}</ResponsiveContainer></div>;
}
