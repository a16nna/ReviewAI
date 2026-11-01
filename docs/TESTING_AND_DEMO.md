# Testing

## Commands
```
cd backend  && python -m pytest -q ; ruff check app tests alembic ; bandit -q -r app ; pip-audit -r requirements.txt
cd frontend && npm run lint ; npm test ; npm run build ; npm audit
cd backend  && python tests/integration/verify_stack.py        # needs `npm install` in frontend
cd frontend && npx playwright install chromium && npm run e2e   # not run by the author
```

## Verification record (final audit, Linux x86_64, Ubuntu 24.04, Python 3.12.3, Node 22)
| Check | Result |
|---|---|
| Backend tests, all analyzers installed | **78 passed** |
| Backend tests, clean venv without Ruff/Bandit, Node/Java/cppcheck hidden from PATH | **72 passed, 6 skipped** (real-analyzer tests skip with a reason) |
| Backend tests, only Ruff/Bandit missing | **76 passed, 2 skipped** |
| Backend tests in random order (pytest-randomly), twice | 78 passed both times |
| `ruff check app tests alembic` / `bandit -r app` (1026 lines) / `pip-audit` | clean / 0 issues / no known vulnerabilities |
| Real analyzers on sample input (Ruff+Bandit, ESLint, ESLint/TS, Checkstyle, cppcheck) | all reported `ran` and produced findings |
| Frontend: `npm run lint` / `npm test` / `npm run build` | clean / **35 passed** / built |
| `playwright test --list` | spec discovered (1 test); **not executed** |
| Full-stack script (fake GitHub + backend configured only via `.env` + Vite dev server, all calls through the proxy) | **38/38 checks** |
| Migration of a genuine legacy DB created by the original pre-migration code (3 reviews) | API output identical before/after; `PRAGMA integrity_check` ok, FK check empty; backup byte-identical; cascade delete works |
| `setup.ps1` under **PowerShell 7.4.6 on Linux** from a clean tools folder | installed ESLint, downloaded Checkstyle, reported all 5 analyzers available (exit 0); with node/java/cppcheck hidden it listed all three problems (exit 1) |
| `setup.sh` same two scenarios | exit 0 / exit 1 with the same problem list |

## What the tests cover
- **Determinism**: by default the Python analyzers are replaced by tiny fakes (`tests/conftest.py`), so no test outcome depends on which tools are installed. `@pytest.mark.real_analyzers` tests use the real tools and skip when absent. Missing Ruff/Bandit is asserted to be reported as `unavailable` (never `ran`, no findings) both at the analysis layer and through the API.
- **Windows-related** (simulated, not run on Windows): importing and running analysis with the `resource` module absent; wall-clock timeout without rlimits; Windows environment variables kept while secrets are excluded; executable discovery via `CPPCHECK_PATH`; non-UTF-8 analyzer output; `.env` loader.
- **GitHub diff handling**: hunk headers without counts, "No newline" markers, blank context lines, multiple hunks, CRLF, trailing newline (no phantom line), form-feed/U+2028 inside lines, removed lines that look like headers, pagination beyond 100 files, position validation including files on page 2, head-changed conflict, `@mention` neutralisation, CSRF, non-ASCII secrets (no 500s), CSRF-cookie recovery.
- **Webhook**: unconfigured, bad/tampered signature, oversized payload, ping, ignored events, malformed payload, duplicate delivery, failed-then-retried delivery, never comments.
- **Migrations**: fresh DB; legacy DB; odd rows (null fields, bad JSON, non-lists); automatic backup (and none for fresh/up-to-date DBs); idempotency; cascade delete; retention; "source code is not stored".
- **AI**: parsing, dropped invalid findings, provider failure classes without leaking details, truncation, prompt-injection containment, line grounding.
- **Frontend**: findings filtering/inert untrusted text/code comparison, forms and uploads, loading/error/mock states, navigation, dashboard/history/detail/settings, export links, delete flows, publish only after explicit confirmation, CSRF header interceptor.

## Not tested (be sceptical of anything claiming otherwise)
Native Windows or macOS execution; real Gemini calls; real GitHub traffic; a real browser (including Monaco, which loads from a CDN, and cookie/redirect behaviour in a browser); Docker builds; PostgreSQL.

# Demonstration guide
See the "Demonstration workflow" section in the README.


## Gemini verification checklist
Automated tests use a fake client (`backend/tests/test_gemini.py`) and need no key. Run:
`cd backend && pip install -r requirements.txt && python -m pytest -q && ruff check app tests alembic && bandit -q -r app`
`cd frontend && npm ci && npm test && npm run lint && npm run build`
Mock mode: start without `GEMINI_API_KEY`; Settings shows Mock and results carry the `[MOCK]` label.
Live check (needs your own key; counts as verified only if it succeeds): set `GEMINI_API_KEY`, run the backend, submit `x = eval(input())` as Python in the Workspace, and confirm an AI finding with a quoted evidence line, `provider: gemini`, and Ruff/Bandit findings listed separately. Record the result here with the date and model.
