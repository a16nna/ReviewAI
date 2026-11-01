import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { errMsg } from "../api";
import Findings from "../components/Findings.jsx";

export default function GitHubPage() {
  const [st, setSt] = useState(null);
  const [repos, setRepos] = useState([]);
  const [repo, setRepo] = useState("");
  const [prs, setPrs] = useState([]);
  const [branches, setBranches] = useState([]);
  const [base, setBase] = useState("");
  const [result, setResult] = useState(null);
  const [pr, setPr] = useState(null);
  const [sel, setSel] = useState(new Set());
  const [ok, setOk] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const guard = async (fn) => { setErr(""); setBusy(true); try { await fn(); } catch (e) { setErr(errMsg(e)); } setBusy(false); };

  useEffect(() => {
    api.get("/github/status").then(({ data }) => {
      setSt(data);
      if (data.connected) api.get("/github/repos").then((r) => setRepos(r.data)).catch((e) => setErr(errMsg(e)));
    });
  }, []);

  const loadPrs = (full, baseBranch = "") => {
    setRepo(full); setResult(null); setPrs([]);
    if (!full) return;
    guard(async () => {
      if (!baseBranch) setBranches((await api.get(`/github/repos/${full}/branches`)).data);
      const params = baseBranch ? { base: baseBranch } : {};
      setPrs((await api.get(`/github/repos/${full}/pulls`, { params })).data);
    });
  };
  const review = (n) => { setPr(n); setSel(new Set()); setOk(false); setMsg(""); guard(async () => setResult((await api.post(`/github/repos/${repo}/pulls/${n}/review`)).data)); };
  const toggle = (id) => setSel((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const publish = () => guard(async () => {
    const comments = result.findings.filter((f) => sel.has(f.id)).map((f) => ({ path: f.file_path, line: f.line_start, body: `${f.severity}: ${f.title}. ${f.description}`.slice(0, 1900) }));
    await api.post(`/github/repos/${repo}/pulls/${pr}/publish`, { confirm: true, head_sha: result.head_sha, comments });
    setMsg(`Published ${comments.length} comment(s) to the pull request.`);
  });

  if (!st) return <p>Loading…</p>;
  if (!st.connected)
    return <div className="card"><p>GitHub is not connected.</p><p className="text-sm text-slate-300">Configure OAuth and connect from <Link className="text-indigo-400" to="/settings">Settings</Link>.</p></div>;

  return (
    <div className="space-y-4">
      {err && <p role="alert" className="rounded bg-red-900/50 p-2 text-sm text-red-200">{err}</p>}
      <div className="flex flex-wrap gap-2">
      <select className="input" value={repo} onChange={(e) => { setBase(""); loadPrs(e.target.value); }} aria-label="Repository">
        <option value="">Choose a repository…</option>
        {repos.map((r) => <option key={r.full_name} value={r.full_name}>{r.full_name}{r.private ? " (private)" : ""}</option>)}
      </select>
      {repo && branches.length > 0 && (
        <select className="input" value={base} onChange={(e) => { setBase(e.target.value); loadPrs(repo, e.target.value); }} aria-label="Base branch">
          <option value="">All base branches</option>
          {branches.map((b) => <option key={b.name} value={b.name}>{b.name}</option>)}
        </select>
      )}
      </div>
      {repo && prs.length === 0 && !busy && <p className="text-slate-300">No open pull requests.</p>}
      <ul className="space-y-2">{prs.map((p) => (
        <li key={p.number} className="card flex items-center justify-between gap-2 text-sm">
          <span>#{p.number} {p.title} <span className="text-slate-400">by {p.author}</span></span>
          <button className="btn" disabled={busy} onClick={() => review(p.number)}>Review</button>
        </li>))}</ul>
      {busy && <p>Working…</p>}
      {result && (
        <div className="space-y-3">
          {result.is_mock && <p className="rounded bg-yellow-900/50 p-2 text-sm text-yellow-200">MOCK MODE: no real AI analysis.</p>}
          {result.ai_error && <p role="alert" className="text-red-300">{result.ai_error}</p>}
          <p className="text-sm text-slate-300">Reviewed {result.files_reviewed} file(s); skipped {result.files_skipped.length}. Findings are limited to changed lines; surrounding code is used as context.</p>
          {result.files_skipped.length > 0 && (
            <ul className="text-xs text-slate-300">{result.files_skipped.map((s) => <li key={s.filename}>{s.filename}: {s.reason}</li>)}</ul>
          )}
          <Link className="text-sm text-indigo-300 underline" to={`/reviews/${result.review_id}`}>Open saved review</Link>
          <Findings findings={result.findings} selectable selected={sel} onToggle={toggle} />
          {sel.size > 0 && (
            <div className="card space-y-2">
              <p className="text-sm">{sel.size} comment(s) selected. They will be posted publicly to PR #{pr} on {repo}.</p>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} /> I confirm I want to publish these comments to GitHub.</label>
              <button className="btn" disabled={!ok || busy} onClick={publish}>Publish comments</button>
            </div>)}
          {msg && <p className="text-green-300">{msg}</p>}
        </div>
      )}
    </div>
  );
}
