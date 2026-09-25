# Developer OS Web IDE

Developer OS includes a persistent, project-scoped web IDE backed by an isolated runner service.

## Capabilities

- Nested text-file tree (up to 2,000 source files / 50 MB per workspace)
- Create, edit, save, delete, rename and move files
- Active-file persistence
- Framework presets for React/Vite, Vue/Vite, Svelte, Next.js, Express, NestJS, Django/DRF, FastAPI, Flask, Litestar, Streamlit, Django Ninja and more
- Generic npm/pip package installation, so the catalog does not limit users to the built-in presets
- Persistent npm/pip dependency directories in the runner volume
- Sandboxed terminal execution with a hard timeout
- Workspace snapshots synchronized back to the Django database
- Non-root runner container with dropped Linux capabilities, no Docker socket and process/memory/CPU limits

## Production setup

Set `IDE_RUNNER_TOKEN` in `.env`. The runner is internal to Docker Compose and is not published to the public internet.

The backend uses `IDE_RUNNER_URL=http://runner:8080`.

The runner intentionally does not receive the Docker socket. Arbitrary commands are therefore confined to the runner container rather than the host. For a multi-tenant public SaaS, deploy the runner as an independently isolated job service (microVM/gVisor/Firecracker or an equivalent hardened sandbox) before allowing untrusted public workloads.

## API

- `GET /api/ide/frameworks/`
- `GET/POST/DELETE /api/ide/workspaces/<id>/files/`
- `POST /api/ide/workspaces/<id>/sync/`
- `POST /api/ide/workspaces/<id>/install/`
- `POST /api/ide/workspaces/<id>/packages/`
- `POST /api/ide/workspaces/<id>/execute/`

The runner exposes only internal `/sync`, `/install`, `/exec`, `/snapshot` and `/health` endpoints.
