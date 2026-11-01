# Deployment notes

This project is built and verified for local use. These notes describe a reasonable production setup; none of it has been tested here.

1. **Containers**: `docker compose up --build` (see `docker-compose.yml`; copy `.env.example` to `.env` first). The frontend container serves the build with nginx and proxies `/api/` to the backend, keeping cookies same-origin. Backend image installs JRE, cppcheck, Node, ESLint and Checkstyle. Data lives in the `reviewai-data` volume.
2. **HTTPS**: terminate TLS in front (reverse proxy / load balancer) and set `COOKIE_SECURE=true`, `FRONTEND_URL`, `CORS_ORIGINS`, `GITHUB_REDIRECT_URI` to the public https URLs.
3. **Secrets**: provide `GEMINI_API_KEY`, `GITHUB_CLIENT_SECRET`, `SESSION_KEY`, `GITHUB_WEBHOOK_SECRET`, `GITHUB_WEBHOOK_TOKEN` via your platform's secret store, not files in the repo.
4. **Access control**: add authentication in front of the whole app (the app has none).
5. **Rate limiting behind a proxy**: the in-memory limiter keys on the connecting IP, i.e. the proxy; enforce per-client limits at the proxy as well.
6. **Scaling**: run a single backend process (sessions/rate limits are in memory) or move them to Redis first. SQLite is fine for one instance; use PostgreSQL via `DATABASE_URL` for more (migrations are plain Alembic/SQLAlchemy, but only SQLite has been tested).
7. **Webhooks**: expose `/api/github/webhook` publicly; GitHub retries are deduplicated by delivery id.
8. **Backups/retention**: back up the DB volume, set `RETENTION_DAYS`, and prune the `<db>.bak-*` copies migrations write.
