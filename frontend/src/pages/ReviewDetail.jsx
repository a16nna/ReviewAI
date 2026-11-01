import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import api, { errMsg } from "../api";
import Findings from "../components/Findings.jsx";
import ReviewMeta from "../components/ReviewMeta.jsx";
import ExportLinks from "../components/ExportLinks.jsx";

export default function ReviewDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [r, setR] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.get(`/reviews/${id}`).then((x) => setR(x.data)).catch((e) => setErr(errMsg(e)));
  }, [id]);

  const del = async () => {
    if (!window.confirm("Delete this review permanently?")) return;
    try {
      await api.delete(`/reviews/${id}`);
      nav("/history");
    } catch (e) {
      setErr(errMsg(e));
    }
  };

  if (err && !r) return <p role="alert">{err} <Link className="text-indigo-300 underline" to="/history">Back to history</Link></p>;
  if (!r) return <p>Loading…</p>;
  return (
    <div className="space-y-4">
      {err && <p role="alert" className="text-red-300">{err}</p>}
      <p className="text-sm text-slate-300">Review {r.id} · {new Date(r.created_at + "Z").toLocaleString()}</p>
      <ReviewMeta review={r} />
      <div className="flex gap-2"><ExportLinks id={r.id} findings={r.findings} /><button className="btn-ghost text-red-300" onClick={del}>Delete</button></div>
      <p className="text-xs text-slate-400">Source code is not stored, so the original/suggested comparison is only available right after analysis.</p>
      <Findings findings={r.findings} />
    </div>
  );
}
