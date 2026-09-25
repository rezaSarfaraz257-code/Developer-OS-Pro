# DeveloperOS — production deployment checklist

This release is designed as a deployable Django + PostgreSQL + Nginx + React/Vite stack.

## Included in this release

- JWT authentication with refresh rotation and server-side blacklist on logout.
- Owner-scoped projects, tasks, notes, snippets and activity history.
- Project-level collaborator membership with API-enforced access.
- Live workspace analytics calculated from persisted data.
- AI assistant endpoint with two modes: an optional OpenAI-compatible provider, or deterministic local workspace intelligence when no provider is configured.
- GitHub OAuth/account/repository integration foundation.
- PostgreSQL in Docker Compose with health checks and migration-on-start.
- Nginx reverse proxy, static asset caching and security headers.
- Responsive command-center UI with mobile navigation.
- CI for frontend lint/build and backend deploy checks/tests.

## Required production environment

Copy `.env.example` to `.env` and set at minimum:

- `POSTGRES_PASSWORD`
- `DJANGO_SECRET_KEY`
- `ALLOWED_HOSTS`
- `CORS_ALLOWED_ORIGINS`
- `CSRF_TRUSTED_ORIGINS`
- `FRONTEND_URL`

For GitHub features set the GitHub OAuth variables and a secure `GITHUB_TOKEN_ENCRYPTION_KEY`.

For external AI, set `AI_API_URL`, `AI_API_KEY`, and `AI_MODEL`. These values are optional; the assistant remains usable with local workspace intelligence without them.

## Deploy

1. Create `.env` with real secrets and production domains.
2. Run `docker compose up -d --build`.
3. Confirm `GET /api/health/` returns `status: ok`.
4. Create an account and verify login, project creation, task creation, note creation and logout.
5. If GitHub is enabled, set the OAuth callback to `/api/github/callback/` on the production API domain.
6. If using an external AI provider, test the AI Assistant page and verify the provider mode is returned.

## Important hosting note

TLS should terminate at the public reverse proxy/load balancer. The included Django settings trust `X-Forwarded-Proto` and enable HTTPS security controls when `DEBUG=False`.

Never commit `.env`, production credentials, JWT secrets, GitHub client secrets, or AI API keys.

## Final hardening pass

The release includes additional production safeguards:

- `/api/health/ready/` readiness probe checks database connectivity and mandatory production configuration.
- Authentication and AI assistant endpoints have dedicated throttling policies.
- AI prompts are capped at 6,000 characters to bound request cost and abuse.
- Backend container runs Gunicorn as a non-root application user.
- Docker backend health checks use the application readiness endpoint.
- `scripts/backup_postgres.sh` creates compressed PostgreSQL custom-format backups.
- CodeQL and dependency-review workflows are included for the repository security gate.
- Frontend error recovery and runtime health indicators use the live readiness endpoint.
