import { Link } from "react-router-dom";

const features = [
  ["AI review", "Gemini analyzes logic errors, security, performance and maintainability, with severity and confidence."],
  ["Static analysis", "Ruff and Bandit results (Python) are kept separate from AI suggestions."],
  ["GitHub PRs", "Review pull-request diffs and publish comments only after you confirm."],
  ["History & reports", "Findings are stored (not your code) with Markdown and JSON export."],
];

export default function Landing() {
  return (
    <div>
      <section className="py-12 text-center">
        <h1 className="text-4xl font-bold text-white">AI-powered code review you can verify</h1>
        <p className="mx-auto mt-4 max-w-2xl text-slate-400">
          ReviewAI combines an LLM with deterministic analyzers. Code is analyzed, never executed.
        </p>
        <Link to="/review" className="btn mt-6 inline-block">Open review workspace</Link>
      </section>
      <section className="grid gap-4 md:grid-cols-2">
        {features.map(([t, d]) => (
          <div key={t} className="card"><h2 className="font-semibold text-white">{t}</h2><p className="mt-1 text-sm text-slate-400">{d}</p></div>
        ))}
      </section>
      <section className="mt-10">
        <h2 className="text-xl font-semibold text-white">How it works</h2>
        <ol className="mt-3 list-decimal space-y-1 pl-6 text-slate-300">
          <li>Paste or upload code and pick a language.</li>
          <li>The backend runs static analyzers in a temp directory and asks the AI provider for findings.</li>
          <li>Review severity, evidence and suggested fixes, then export or revisit them in the dashboard.</li>
        </ol>
      </section>
    </div>
  );
}
