import { useState } from "react";
import Editor from "@monaco-editor/react";
import api, { errMsg } from "../api";
import Findings from "../components/Findings.jsx";
import ReviewMeta from "../components/ReviewMeta.jsx";
import ExportLinks from "../components/ExportLinks.jsx";

const EXT = { py: "python", js: "javascript", jsx: "javascript", ts: "typescript", tsx: "typescript", java: "java", cpp: "cpp", cc: "cpp", h: "cpp" };
const LANGS = ["python", "javascript", "typescript", "java", "cpp"];
const MAX = 100000;
const ANALYZERS = { python: "Static analyzers: Ruff + Bandit", javascript: "Static analyzer: ESLint (+ security plugin)", typescript: "Static analyzer: ESLint (+ security plugin)", java: "Static analyzer: Checkstyle", cpp: "Static analyzer: cppcheck" };

export default function Workspace() {
  const [code, setCode] = useState("import os\n\ndef run(cmd):\n    return eval(cmd)\n");
  const [lang, setLang] = useState("python");
  const [state, setState] = useState("idle");
  const [res, setRes] = useState(null);
  const [reviewed, setReviewed] = useState("");
  const [err, setErr] = useState("");

  const upload = async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    const l = EXT[f.name.split(".").pop().toLowerCase()];
    if (!l) return setErr("Unsupported file type");
    if (f.size > MAX) return setErr(`File exceeds ${MAX} characters`);
    setErr("");
    setLang(l);
    setCode(await f.text());
  };

  const run = async () => {
    if (!code.trim()) return setErr("Enter some code first");
    if (code.length > MAX) return setErr(`Code exceeds ${MAX} characters`);
    setState("loading");
    setErr("");
    try {
      const { data } = await api.post("/reviews", { code, language: lang });
      setRes(data);
      setReviewed(code);
      setState("done");
    } catch (e) {
      setErr(errMsg(e));
      setState("error");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <select className="input" value={lang} onChange={(e) => setLang(e.target.value)} aria-label="Language">
          {LANGS.map((l) => <option key={l}>{l}</option>)}
        </select>
        <input type="file" accept=".py,.js,.jsx,.ts,.tsx,.java,.cpp,.cc,.h" onChange={upload} className="text-sm" aria-label="Upload file" />
        <button className="btn" onClick={run} disabled={state === "loading"}>{state === "loading" ? "Analyzing…" : "Analyze"}</button>
        <span className="text-xs text-slate-300">
          {ANALYZERS[lang]} · {code.length}/{MAX}
        </span>
      </div>
      {err && <p role="alert" className="rounded bg-red-900/50 p-2 text-sm text-red-200">{err}</p>}
      <div className="overflow-hidden rounded-lg border border-slate-800">
        <Editor height="360px" theme="vs-dark" language={lang} value={code} onChange={(v) => setCode(v ?? "")} options={{ minimap: { enabled: false } }} />
      </div>
      <p className="sr-only" aria-live="polite">{state === "loading" ? "Analyzing" : state === "done" ? "Analysis complete" : ""}</p>
      {state === "idle" && <p className="text-sm text-slate-400">Results will appear here after you click Analyze.</p>}
      {state === "done" && res && (
        <>
          <ReviewMeta review={res} />
          <ExportLinks id={res.id} findings={res.findings} />
          <Findings findings={res.findings} code={reviewed} />
        </>
      )}
    </div>
  );
}
