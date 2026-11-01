import axios from "axios";

// Same-origin (/api is proxied to FastAPI) so the HttpOnly session cookie is sent. The backend also sets a
// JS-readable `csrf_token` cookie at login; we echo it in an X-CSRF-Token header on every state-changing request
// (double-submit). Done explicitly rather than via axios' implicit XSRF handling so it is testable.
const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE || "/api", withCredentials: true });

const SAFE_METHODS = new Set(["get", "head", "options"]);

export function readCookie(name) {
  const hit = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
  return hit ? decodeURIComponent(hit.slice(name.length + 1)) : null;
}

api.interceptors.request.use((config) => {
  if (!SAFE_METHODS.has((config.method || "get").toLowerCase())) {
    const token = readCookie("csrf_token");
    if (token) config.headers.set("X-CSRF-Token", token);
  }
  return config;
});

export const errMsg = (e) => {
  const d = e?.response?.data?.detail;
  if (Array.isArray(d)) return d.map((x) => x.msg).join("; ");
  if (typeof d === "string") return d;
  return e?.message === "Network Error" ? "Cannot reach the backend. Is it running?" : "Request failed";
};

export const REPORT_BASE = import.meta.env.VITE_API_BASE || "/api";
export default api;
