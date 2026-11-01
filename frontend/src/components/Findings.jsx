import { useMemo, useState } from "react";

export const SEVERITIES = ["Critical", "High", "Medium", "Low", "Informational"];
const COLORS = {
  Critical: "bg-red-700 text-white", High: "bg-orange-600 text-white", Medium: "bg-yellow-500 text-black",
  Low: "bg-sky-700 text-white", Informational: "bg-slate-600 text-white",
};

// All text is rendered by React as plain text (never raw HTML), so untrusted content is inert.
export default function Findings({ findings, code, selectable, selected, onToggle }) {
  const [sev, setSev] = useState("");
  const [src, setSrc] = useState("");
  const [q, setQ] = useState("");

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return findings
      .filter((f) => (!sev || f.severity === sev) && (!src || f.source === src))
      .filter((f) => !needle || `${f.title} ${f.description} ${f.file_path || ""}`.toLowerCase().includes(needle))
      .sort((a, b) => SEVERITIES.indexOf(a.severity) - SEVERITIES.indexOf(b.severity));
  }, [findings, sev, src, q]);

  if (!findings.length) return <p className="card text-slate-300">No findings were reported.</p>;
  return (
    <section aria-label="Findings">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <select className="input" aria-label="Filter by severity" value={sev} onChange={(e) => setSev(e.target.value)}>
          <option value="">All severities</option>
          {SEVERITIES.map((s) => <option key={s}>{s}</option>)}
        </select>
        <select className="input" aria-label="Filter by source" value={src} onChange={(e) => setSrc(e.target.value)}>
          <option value="">All sources</option>
          <option value="ai">AI suggestions</option>
          <option value="static_analysis">Static analysis</option>
        </select>
        <input className="input" aria-label="Search findings" placeholder="Search findings…" value={q} onChange={(e) => setQ(e.target.value)} />
        <span className="text-sm text-slate-300" aria-live="polite">{shown.length} of {findings.length} findings</span>
      </div>
      {shown.length === 0 && <p className="card text-slate-300">No findings match the filters.</p>}
      <ul className="space-y-3">
        {shown.map((f) => {
          const end = f.line_end || f.line_start;
          const original = code && f.line_start ? code.split("\n").slice(f.line_start - 1, end).join("\n") : null;
          return (
            <li key={f.id} className="card">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                {selectable && f.file_path && f.line_start && (
                  <input type="checkbox" aria-label={`Select finding: ${f.title}`} checked={selected.has(f.id)} onChange={() => onToggle(f.id)} />
                )}
                <span className={`rounded px-2 py-0.5 font-semibold ${COLORS[f.severity]}`}>{f.severity}</span>
                <span className="rounded border border-slate-600 px-2 py-0.5">
                  {f.source === "ai" ? "AI suggestion" : `Static analysis${f.analyzer ? `: ${f.analyzer}` : ""}`}
                </span>
                <span className="rounded border border-slate-600 px-2 py-0.5">{f.certainty === "confirmed" ? "Confirmed" : "Possible"}</span>
                <span className="text-slate-300">{f.category} · confidence: {f.confidence}</span>
                {f.file_path && <span className="font-mono text-slate-300">{f.file_path}</span>}
                {f.line_start && <span className="text-slate-300">line {f.line_start}{end && end !== f.line_start ? `–${end}` : ""}</span>}
              </div>
              <h3 className="mt-2 font-medium text-white">{f.title}</h3>
              <p className="mt-1 text-sm text-slate-200">{f.description}</p>
              {f.evidence && <p className="mt-1 text-sm text-slate-300"><b>Evidence:</b> <code className="rounded bg-slate-950 px-1 font-mono text-xs">{f.evidence}</code></p>}
              {f.impact && <p className="mt-1 text-sm text-slate-300"><b>Impact:</b> {f.impact}</p>}
              {f.remediation && <p className="mt-1 text-sm text-slate-300"><b>Fix:</b> {f.remediation}</p>}
              {f.corrected_code && (
                <div className="mt-3 grid gap-2 md:grid-cols-2">
                  <div><p className="text-xs text-slate-400">Original</p><pre className="overflow-x-auto rounded bg-slate-950 p-2 text-xs">{original ?? "(original not available — source code is not stored)"}</pre></div>
                  <div>
                    <p className="text-xs text-slate-400">Suggested</p>
                    <pre className="overflow-x-auto rounded bg-slate-950 p-2 text-xs">{f.corrected_code}</pre>
                    <CopyButton text={f.corrected_code} label="Copy suggestion" />
                  </div>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function CopyButton({ text, label = "Copy" }) {
  const [done, setDone] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setDone(true);
      setTimeout(() => setDone(false), 1500);
    } catch {
      setDone(false);
    }
  };
  return <button className="btn-ghost mt-1 text-xs" onClick={copy}>{done ? "Copied!" : label}</button>;
}
