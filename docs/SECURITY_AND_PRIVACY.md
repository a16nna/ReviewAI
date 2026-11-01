# Security and privacy

## Implemented controls
| Area | Control |
|---|---|
| Input | Pydantic validation; 100,000-char limit; language allow-list; uploads limited client-side and re-validated server-side |
| Code execution | Submitted code is never executed; analyzers run via argument lists (`shell=False`) in a temp dir with fixed file names (no user-controlled paths), 30 s wall-clock timeout (all platforms), CPU and file-size rlimits where `resource.prlimit` exists (Linux only), 2 MB output cap, UTF-8 decoding with replacement |
| Secrets | Analyzers receive a minimal environment (no API keys; on Windows only the required system variables are added); `backend/.env` is loaded without overriding real environment variables; secrets only via env vars; `.env` git-ignored; `.env.example` has placeholders |
| Prompt injection | Code is wrapped in `<code>` tags with the closing tag escaped; system prompt declares it untrusted data and asks to flag injection attempts; output is schema-validated; line numbers are verified against the real code; AI output is rendered as plain text; nothing the model says can trigger an action (publishing needs a human confirmation) |
| Sessions | OAuth `state` cookie checked with constant-time compare (byte-wise, so hostile non-ASCII input is rejected instead of crashing); session id is random, HttpOnly, SameSite=Lax, `Secure` when `COOKIE_SECURE=true`; 8 h TTL; token Fernet-encrypted in memory; never sent to the browser or logged |
| CSRF | State-changing GitHub endpoints require `X-CSRF-Token` equal to the per-session secret (double-submit, set as a readable cookie at login and re-issued by `/github/status` if lost; the frontend echoes it explicitly); plus an `Origin` allow-list check on all writes. The allow-list is exact-match on purpose (no "same host" shortcut, which would be vulnerable to DNS rebinding of a local service) |
| CORS | Explicit origin list (`CORS_ORIGINS`), no wildcard, only needed methods/headers |
| GitHub | Least-privilege scope default `public_repo`; owner/repo validated; all changed files are paginated before validating; head-SHA and diff-position validation before publish (phantom lines past the end of a diff are not accepted); `@mentions` neutralised; only `event=COMMENT` (no approve/merge/push) |
| Webhook | HMAC-SHA256 over the raw body (constant-time), `Content-Length` and body caps (1 MB), delivery-id dedupe table with failed-run retry, background processing, never comments |
| Rendering | React text rendering only; no `dangerouslySetInnerHTML`; tests assert hostile titles are inert |
| Logging | No code, tokens or provider error bodies are logged; provider errors are mapped to fixed messages |
| Database | Alembic migrations; automatic timestamped backup before migrating an existing SQLite file; tolerant legacy-row handling; foreign keys enforced |
| Dependencies | `pip-audit` (clean at time of writing), `npm audit` in CI |

## Privacy and retention
- Source code is held in memory and a temp directory only for the duration of a request, then discarded; the database stores no source code (tested). Stored: findings text (including AI "corrected code" suggestions and analyzer messages, which may quote small code fragments), language, counts, analyzer status, PR repo/number/head SHA.
- With a real key, submitted code (and, for PR reviews, file excerpts) is sent to Google (Gemini); with GitHub connected, repository data is fetched from GitHub.
- Retention: reviews persist until deleted in the UI/API, or automatically after `RETENTION_DAYS` days (checked when a review is created). Webhook delivery ids are purged with the same cutoff.

## Remaining risks (not solved)
- **Untested platforms**: Windows and macOS behaviour (including the weaker resource limits there) has not been verified; only Linux was tested.
- **Real-service behaviour**: the GitHub and Gemini integrations were verified only against mocks and a local stand-in; real-world error shapes, SSO/fine-grained-token behaviour and rate limits are untested.
- **Backups** (`<db>.bak-*`) contain the same data as the database and are never deleted automatically; they are covered by `.gitignore` but not by `RETENTION_DAYS`.
- Behind a reverse proxy the rate limiter keys on the proxy IP (shared bucket) and does not read `X-Forwarded-For`.
- **No authentication/authorization for the app itself**: it's a single-user tool. Anyone who can reach the API can read/delete stored reviews and spend your Gemini quota. Put it behind authentication before any shared deployment.
- Rate limiting and sessions are per-process memory; multiple workers would each have their own.
- The OAuth `public_repo`/`repo` scopes are coarse; a GitHub App with fine-grained permissions would be better.
- Prompt injection cannot be fully eliminated; mitigations reduce impact, and a human gates every external action.
- Resource limits other than timeouts depend on Linux `prlimit`; Windows relies on the timeout only.
- Analyzer tools parse attacker-controlled text; they run unprivileged but are not sandboxed beyond rlimits (use containers/seccomp in production).
- No penetration test or independent review has been performed.
- `npm audit` (at the time of writing): production-tree advisories in `react-router` (open-redirect/SSR-hydration issues; SSR isn't used and links are internal) and `dompurify` (only via `monaco-editor`, which is loaded from a CDN at runtime and is not in the built bundle); dev-tree advisories in the Vitest/Vite toolchain. Fixes require major upgrades that were not attempted. Monaco is loaded from jsDelivr at runtime — self-host it if that is unacceptable.
