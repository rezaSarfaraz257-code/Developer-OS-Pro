# Developer OS — Production Deployment

## 1. Configure the environment

```bash
cp .env.example .env
```

Set real production values for every placeholder, especially:

- `DJANGO_SECRET_KEY`
- `POSTGRES_PASSWORD`
- `ALLOWED_HOSTS`
- `CORS_ALLOWED_ORIGINS`
- `CSRF_TRUSTED_ORIGINS`
- `FRONTEND_URL`

Use an HTTPS domain.

## 2. GitHub integration

Create the GitHub OAuth application and set its callback to:

```text
https://YOUR_DOMAIN/api/github/callback/
```

Then configure:

```text
GITHUB_CLIENT_ID
GITHUB_CLIENT_SECRET
GITHUB_OAUTH_SCOPE
GITHUB_TOKEN_ENCRYPTION_KEY
GITHUB_OAUTH_REDIRECT
```

The application uses OAuth state and PKCE. For organization-scale automation or fine-grained repository permissions, a GitHub App is the recommended future integration boundary.

## 3. Optional AI

Developer OS can use an OpenAI-compatible `/chat/completions` endpoint:

```text
AI_API_URL=
AI_API_KEY=
AI_MODEL=
```

If these values are absent, the workspace assistant falls back to deterministic workspace intelligence instead of fabricating AI output.

## 4. Start production

```bash
docker compose up -d --build
```

The stack is:

```text
Nginx/React → Django/Gunicorn → PostgreSQL
```

## 5. Create the administrator

```bash
docker compose exec backend python manage.py createsuperuser
```

## 6. Verify health

```text
https://YOUR_DOMAIN/api/health/
```

The response should report:

```json
{"status":"ok","database":"ok"}
```

## 7. Local development

Backend:

```powershell
cd Backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_catalog
python manage.py runserver
```

Frontend:

```powershell
cd Frontend
npm ci
npm run dev
```

If Vite is not proxied locally, set:

```text
VITE_API_URL=http://127.0.0.1:8000/api
```

## Hosting notes

Use a managed PostgreSQL service for serious production workloads, terminate TLS at a trusted edge, keep secrets outside the repository, and configure backups and monitoring before onboarding real users.

## Backups and release operations

Before onboarding real users, configure scheduled PostgreSQL backups and test a restore. A manual backup can be created with:

```bash
POSTGRES_DB=developeros POSTGRES_USER=developeros POSTGRES_PASSWORD='...' ./scripts/backup_postgres.sh
```

The generated `.dump` file should be stored outside the application container and retained according to your recovery policy.

For load balancers and container orchestration, use `/api/health/` for liveness and `/api/health/ready/` for readiness. Do not send production traffic until the readiness endpoint returns `status: ready`.
