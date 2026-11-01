import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { errMsg } from "../api";
import { SEVERITIES } from "../components/Findings.jsx";

const PAGE = 25;

export default function History() {
  const [rows, setRows] = useState([]);
  const [f, setF] = useState({ q: "", language: "", severity: "", source_kind: "" });
  const [more, setMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  const load = useCallback(async (offset = 0) => {
    setLoading(true);
    setErr("");
    try {
      const params = { limit: PAGE, offset, ...Object.fromEntries(Object.entries(f).filter(([, v]) => v)) };
      const { data } = await api.get("/reviews", { params });
      setRows((r) => (offset ? [...r, ...data] : data));
      setMore(data.length === PAGE);
    } catch (e) {
      setErr(errMsg(e));
    }
    setLoading(false);
  }, [f]);

  useEffect(() => { load(0); }, [load]);

  const del = async (id) => {
    if (!window.confirm("Delete this review permanently?")) return;
    try {
      await api.delete(`/reviews/${id}`);
      setRows((r) => r.filter((x) => x.id !== id));
      setMsg("Review deleted.");
    } catch (e) {
      setErr(errMsg(e));
    }
  };
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold text-white">Review history</h1>
      <div className="flex flex-wrap gap-2">
        <input className="input" placeholder="Search findings, repo…" aria-label="Search reviews" value={f.q} onChange={set("q")} />
        <select className="input" aria-label="Language filter" value={f.language} onChange={set("language")}>
          <option value="">All languages</option>
          {["python", "javascript", "typescript", "java", "cpp", "multi"].map((l) => <option key={l}>{l}</option>)}
        </select>
        <select className="input" aria-label="Severity filter" value={f.severity} onChange={set("severity")}>
          <option value="">Any severity</option>
          {SEVERITIES.map((s) => <option key={s}>{s}</option>)}
        </select>
        <select className="input" aria-label="Origin filter" value={f.source_kind} onChange={set("source_kind")}>
          <option value="">All origins</option>
          <option value="manual">Workspace</option>
          <option value="github_pr">GitHub PR</option>
          <option value="github_webhook">GitHub webhook</option>
        </select>
      </div>
      {err && <p role="alert" className="rounded bg-red-900/60 p-2 text-sm text-red-100">{err}</p>}
      {msg && <p role="status" className="text-green-300">{msg}</p>}
      {loading && !rows.length ? <p>Loading…</p> : rows.length === 0 ? (
        <p className="card text-slate-300">No reviews match. <Link className="text-indigo-300 underline" to="/review">Run a review</Link></p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-slate-300"><tr><th scope="col">Date</th><th scope="col">Origin</th><th scope="col">Language</th><th scope="col">Findings</th><th scope="col">Provider</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-t border-slate-800">
                  <td className="py-2"><Link className="text-indigo-300 underline" to={`/reviews/${r.id}`}>{new Date(r.created_at + "Z").toLocaleString()}</Link></td>
                  <td>{r.repo ? `${r.repo}#${r.pr_number}` : "Workspace"}</td>
                  <td>{r.language}</td>
                  <td>{r.findings.length}</td>
                  <td>{r.provider}{r.is_mock ? " (mock)" : ""}</td>
                  <td><button className="text-red-300 underline" aria-label={`Delete review ${r.id}`} onClick={() => del(r.id)}>Delete</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {more && <button className="btn-ghost" disabled={loading} onClick={() => load(rows.length)}>Load more</button>}
    </div>
  );
}
