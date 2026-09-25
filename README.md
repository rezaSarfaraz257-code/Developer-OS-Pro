# Developer OS — Production 1.0

Developer OS is a developer operating environment: one workspace for projects, tasks, knowledge, tools, workflows, GitHub context, AI assistance, collaboration, activity and delivery intelligence.

This repository is the **production 1.0 release line**. It is not an MVP/demo repository.

## Product surface

- Public developer catalog: tools, resources and workflows
- Secure accounts: registration, JWT access/refresh rotation and logout revocation
- Developer profile and identity
- Project workspace with status, priority, deadlines, tags and stack metadata
- Tasks, notes, snippets and activity
- Favorites/bookmarks
- Collaboration and project membership
- Workspace analytics and delivery signals
- AI workspace assistant with optional OpenAI-compatible provider
- GitHub OAuth with PKCE, repository discovery and activity synchronization
- Production Docker stack: React/Vite + Nginx + Django/Gunicorn + PostgreSQL
- Security headers, HTTPS-aware settings, upload validation and encrypted GitHub credentials
- CI configuration and release validation documentation

## Architecture

```text
Browser
  │
  ▼
Nginx / React static application
  │
  ├── /api/* ───────────────► Django REST Framework
  │                              │
  │                              ├── Auth / JWT
  │                              ├── Workspace
  │                              ├── Projects / Tasks
  │                              ├── Knowledge / Resources
  │                              ├── GitHub integration
  │                              └── AI / collaboration
  │
  └── /media/* ─────────────► Django media storage

Django ─────────────────────► PostgreSQL
```

## Technology baseline

- React 19 + Vite 8
- Django 5.2 + Django REST Framework
- PostgreSQL 17
- SimpleJWT
- Docker / Nginx / Gunicorn
- GitHub REST API
- Optional OpenAI-compatible AI provider

## Production launch

1. Copy `.env.example` to `.env`.
2. Replace every placeholder secret and domain.
3. Configure HTTPS at the hosting edge.
4. Configure GitHub OAuth callback and credentials if GitHub integration is enabled.
5. Build and start:

```bash
docker compose up -d --build
```

6. Create the first administrator:

```bash
docker compose exec backend python manage.py createsuperuser
```

7. Verify:

```text
GET https://YOUR_DOMAIN/api/health/
```

Expected response includes `status=ok` and `database=ok`.

8. Execute the release gate described in `FINAL_RELEASE.md` before opening the service to users.

## Security model

- Production requires a real `DJANGO_SECRET_KEY`.
- PostgreSQL is the production database in Docker.
- JWT refresh tokens rotate and are blacklisted on logout.
- Project/task/note access is checked against ownership or collaboration membership.
- Uploaded avatars are validated, normalized and re-encoded.
- GitHub tokens are encrypted at rest.
- GitHub OAuth uses state plus PKCE.
- Shared catalogs are public-read and staff-write.
- API throttling is enabled.
- HTTPS, HSTS, secure cookies, clickjacking and content-type protections are enabled in production.

## GitHub integration

The current integration uses a GitHub OAuth App with configurable scopes and PKCE. For installations that need organization-scale automation or tightly scoped repository permissions, GitHub recommends GitHub Apps because they provide fine-grained permissions and short-lived tokens. The integration boundary is intentionally isolated so the authentication provider can evolve without changing the workspace model.

## Repository structure

```text
Developer-OS/
├── Backend/
│   ├── api/
│   ├── x/
│   ├── manage.py
│   └── requirements.txt
├── Frontend/
│   ├── src/
│   ├── public/
│   ├── package.json
│   ├── Dockerfile
│   └── nginx.conf
├── docs/
├── .github/
├── .env.example
├── docker-compose.yml
├── DEPLOYMENT.md
├── FINAL_RELEASE.md
└── PROJECT.md
```

## Development

Backend:

```bash
cd Backend
python -m venv .venv
# activate the environment
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_catalog
python manage.py runserver
```

Frontend:

```bash
cd Frontend
npm ci
npm run dev
```

## Product principle

Developer OS is designed as a durable product foundation. New releases should add capabilities or integrations; they should not require rewriting the core workspace, identity, authorization or deployment architecture.

## License

The repository does not currently declare an open-source license. Treat it as proprietary unless a license is added by the owner.

## Release hardening

The current release also provides a cross-catalog search endpoint, API request correlation IDs, authentication throttling, GitHub disconnect/repository filtering, runtime production-readiness checks, and a React error-recovery boundary. The public catalog is data-driven rather than dependent on fabricated ratings or static counts.


## Developer OS Pro — Platform Upgrade

This release extends the workspace into a full developer control plane:

- **Context-aware Intelligence**: persisted AI conversations/messages and project-aware context across projects, tasks, notes and snippets.
- **Universal Search**: authenticated cross-entity search for projects, tasks, notes, snippets plus the public developer catalog.
- **Collaboration Fabric**: project comments, organization/team membership, roles, invites foundation and task dependencies.
- **Web IDE**: persistent browser workspaces, file tree, multi-file editor, terminal panel and project launch surface.
- **SaaS foundation**: subscription/entitlement state, organizations and developer API keys with one-time secret issuance.
- **Production discipline**: migrations, API boundaries, security controls, health/readiness endpoints and CI/security workflows.

### Important execution boundary

The Web IDE intentionally does **not** execute arbitrary user code inside the Django web process. The Run action records the execution intent and exposes a safe integration boundary for an isolated runner/worker. A production deployment should connect this to a sandboxed job system (for example, isolated containers with strict CPU, memory, filesystem and network limits).

Payment providers are also intentionally provider-agnostic: subscription state and entitlements are persisted locally, while a verified provider webhook can synchronize external billing state.
