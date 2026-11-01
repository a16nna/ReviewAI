import { REPORT_BASE } from "../api";
import { CopyButton } from "./Findings.jsx";

export default function ExportLinks({ id, findings }) {
  const base = `${REPORT_BASE}/reviews/${id}/report`;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <a className="btn-ghost" href={`${base}?format=md`} download={`review-${id}.md`}>Export Markdown</a>
      <a className="btn-ghost" href={`${base}?format=json`} download={`review-${id}.json`}>Export JSON</a>
      <CopyButton text={JSON.stringify(findings, null, 2)} label="Copy findings" />
    </div>
  );
}
