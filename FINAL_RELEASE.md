# Developer OS — Production 1.0 Release Gate

This is the release contract for the first public production version. It is the production release contract for the product.

## Release scope

The production line includes:

- identity and authentication
- public developer catalog
- projects and workspace
- tasks and progress
- notes and snippets
- tags and favorites
- collaboration
- activity and analytics
- AI workspace assistant
- GitHub integration
- production Docker deployment
- security controls
- responsive command-center UI

## Mandatory pre-release checks

### Backend

```bash
cd Backend
python manage.py check --deploy
python manage.py migrate --check
python manage.py test
python manage.py seed_catalog
```

### Frontend

```bash
cd Frontend
npm ci
npm run lint
npm run build
```

### Production stack

```bash
docker compose config
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 backend
```

### Smoke test

Verify:

1. `/api/health/`
2. public tools/resources/workflows
3. account registration
4. login
5. token refresh
6. logout and refresh-token revocation
7. profile update and avatar upload
8. project creation/edit/delete
9. task creation/update/delete
10. notes
11. snippets
12. favorites
13. collaboration permissions
14. AI assistant
15. GitHub connect/repository listing/activity sync
16. responsive navigation
17. direct browser refresh on application routes

## Production environment

Required:

- `DJANGO_SECRET_KEY`
- `POSTGRES_PASSWORD`
- `ALLOWED_HOSTS`
- `CORS_ALLOWED_ORIGINS`
- `CSRF_TRUSTED_ORIGINS`
- `FRONTEND_URL`

Required for GitHub:

- `GITHUB_CLIENT_ID`
- `GITHUB_CLIENT_SECRET`
- `GITHUB_TOKEN_ENCRYPTION_KEY`
- `GITHUB_OAUTH_REDIRECT`

Optional AI:

- `AI_API_URL`
- `AI_API_KEY`
- `AI_MODEL`

Never commit `.env`.

## Operational standard

A production release is not considered complete until the actual deployment environment passes the commands above. Local source inspection alone is not proof of production readiness.

## Final hardening pass — 2026-09-24

The release package includes an additional production hardening pass:

- Cross-catalog global search API (`/api/search/`).
- Request correlation IDs and server timing headers on API responses.
- Authentication throttling for login and registration endpoints.
- GitHub repository activity filtering by exact `owner/repository` full name.
- GitHub account disconnect lifecycle with credential deletion.
- Runtime production-readiness page with live API/database checks instead of hard-coded PASS states.
- React error boundary with recovery/reload actions.
- Frontend unit tests using Node's built-in test runner.
- Removal of obsolete empty API service files and other dead surface area.
- Live catalog data is now used on the public home experience instead of stale hard-coded workflow/resource counts.

The package is considered release-complete for the defined product scope after static validation. Final deployment acceptance still requires the target environment to execute the repository CI pipeline, backend tests, frontend build, HTTPS/proxy validation, and real-user end-to-end smoke test.


## 2.0 Platform Completion Layer

The final product surface now includes the platform layers that turn a workspace into a developer operating system:

1. Intelligence — persisted AI threads + workspace context engine.
2. Collaboration — comments, organization membership, project collaboration and task dependencies.
3. Search — authenticated universal search across personal workspace entities and shared developer catalog.
4. Web IDE — persistent multi-file browser workspace with editor, file tree and terminal surface.
5. SaaS — subscription model, organization plans, API keys and billing webhook boundary.
6. Quality gates — migration coverage, Python syntax validation and frontend production build are expected release gates in CI.

For arbitrary code execution, Developer OS uses an isolated-runner boundary rather than executing untrusted source inside the API process.
