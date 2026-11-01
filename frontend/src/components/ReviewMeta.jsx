export default function ReviewMeta({ review }) {
  return (
    <div className="card text-sm">
      {review.is_mock && (
        <p className="mb-2 rounded bg-yellow-900/60 p-2 text-yellow-100">
          MOCK MODE: no AI key configured, so no real AI analysis was performed.
        </p>
      )}
      {review.ai_error && (
        <p role="alert" className="mb-2 rounded bg-red-900/60 p-2 text-red-100">
          AI review failed: {review.ai_error}. Static-analysis results are still shown.
        </p>
      )}
      <p>Language: <b>{review.language}</b> · Provider: <b>{review.provider}</b>{review.repo && <> · PR: <b>{review.repo}#{review.pr_number}</b></>}</p>
      <ul className="mt-1 flex flex-wrap gap-x-4 text-slate-300">
        {Object.entries(review.analyzers).map(([k, v]) => (
          <li key={k}>{k}: <span className={v === "ran" ? "text-green-300" : "text-yellow-200"}>{v}</span></li>
        ))}
      </ul>
      <p className="text-xs text-slate-400">Code is analyzed, never executed.</p>
    </div>
  );
}
