import { useEffect, useState } from "react";
import api, { errMsg } from "../api";

const LABELS = { gemini: "Gemini", mock: "Mock (demo, not real AI)", unavailable: "Unavailable" };
const providerLabel = (cap) => (cap ? LABELS[cap.ai?.state] || cap.ai_provider : "…");

export default function Settings() {
  const [cap, setCap] = useState(null);
  const [health, setHealth] = useState(null);
  const [gh, setGh] = useState(null);
  const [err, setErr] = useState("");

  const load = () => {
    api.get("/capabilities").then((x) => setCap(x.data)).catch((e) => setErr(errMsg(e)));
    api.get("/health").then((x) => setHealth(x.data)).catch((e) => setErr(errMsg(e)));
    api.get("/github/status").then((x) => setGh(x.data)).catch((e) => setErr(errMsg(e)));
  };
  useEffect(load, []);

  const connect = async () => {
    try { window.location.href = (await api.get("/github/login")).data.url; } catch (e) { setErr(errMsg(e)); }
  };
  const disconnect = async () => {
    try { await api.post("/github/logout"); } catch (e) { setErr(errMsg(e)); }
    load();
  };

  return (
    <div className="space-y-4">
      {err && <p role="alert" className="rounded bg-red-900/50 p-2 text-sm text-red-200">{err}</p>}
      <h1 className="text-2xl font-semibold text-white">Settings</h1>
      <section className="card"><h2 className="font-semibold text-white">AI provider</h2>
        <p className="text-sm">{health ? `Mode: ${health.mode}` : "…"} · Provider: <b>{providerLabel(cap)}</b>{cap?.ai?.model && <> · Model: <span className="font-mono">{cap.ai.model}</span></>}</p>
        {cap?.ai?.state === "mock" && <p role="status" className="text-sm text-yellow-100">{cap.ai.message}</p>}
        {cap?.ai?.state === "unavailable" && <p role="alert" className="text-sm text-red-200">AI review is unavailable: {cap.ai.message}</p>}
        {cap?.ai?.state === "gemini" && <p className="text-sm text-slate-300">The API key is read only by the backend and is never sent to the browser.</p>}
      </section>
      <section className="card"><h2 className="font-semibold text-white">GitHub</h2>
        {gh?.connected ? <p className="text-sm">Connected as <b>{gh.login}</b> (scope: {gh.scope})</p> : <p className="text-sm">Not connected.</p>}
        {gh && <p className="text-sm text-slate-300">Webhook: {gh.webhook_configured ? "secret configured (endpoint /github/webhook)" : "not configured"}</p>}
        {gh && !gh.configured && <p className="text-sm text-yellow-100">OAuth is not configured. Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET (see README).</p>}
        <div className="mt-2">{gh?.connected ? <button className="btn-ghost" onClick={disconnect}>Disconnect</button> : <button className="btn" onClick={connect} disabled={!gh?.configured}>Connect GitHub</button>}</div>
      </section>
      <section className="card"><h2 className="font-semibold text-white">Analysis capabilities</h2>
        <ul className="text-sm text-slate-200">{cap && Object.entries(cap.languages).map(([l, a]) => <li key={l}><b>{l}</b>: AI review · {Object.entries(a).map(([k, v]) => `${k} ${v}`).join(", ")}</li>)}</ul>
      </section>
      <section className="card"><h2 className="font-semibold text-white">Privacy & retention</h2>
        <ul className="list-disc pl-5 text-sm text-slate-300">
          <li>Submitted code is analyzed in a temporary directory that is deleted afterwards and is never executed or stored.</li>
          <li>Retention: {cap?.retention_days ? `reviews older than ${cap.retention_days} days are deleted automatically` : "no automatic deletion (set RETENTION_DAYS to enable)"}.</li>
          <li>Findings and metadata are stored in the local database until you delete them.</li>
          <li>GitHub tokens are kept only in backend memory (lost on restart) and are never sent to the browser.</li>
          <li>With a real AI key, submitted code is sent to Google (Gemini) for analysis.</li>
        </ul>
      </section>
    </div>
  );
}
