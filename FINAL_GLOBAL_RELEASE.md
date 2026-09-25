# Developer OS — Global Release Hardening

This package is the final hardening pass over the Web IDE release.

## User-facing capabilities

- Persistent project workspaces
- File create/edit/save/delete/rename/move, including virtual directories
- Framework presets and package installation through isolated runner containers
- npm and pip package workflows
- Python and Node runtimes in the runner image
- Git available inside workspaces for normal developer workflows
- Project-aware AI conversations and workspace context
- Collaboration, comments, notifications, organizations and role foundation
- Universal platform search
- API keys and subscription entitlement foundation
- Docker Compose production topology with PostgreSQL, Django/Gunicorn, Nginx and runner

## Final hardening included in this package

- Workspace source limits: 2,000 files / 50 MB total source / 1 MB per file
- Strict path validation and traversal prevention
- Virtual directory rename and recursive delete semantics
- Runner timeout process-group cleanup to prevent orphaned processes
- Non-root runner, dropped Linux capabilities, no-new-privileges, CPU/RAM/PID limits
- Production release gate and static Python/import validation

## Important production requirement

The runner intentionally executes developer commands in a separate service rather than inside Django. For internet-scale arbitrary-code execution, the runner should be deployed on dedicated worker nodes with a stronger isolation layer such as Firecracker/gVisor/Kata Containers, per-execution network policy, and resource quotas. The application is designed so that this isolation boundary can be replaced without changing the IDE API.

## Verification performed for this package

- Python compilation: PASS
- Repository release gate: PASS
- ZIP integrity: checked after packaging

A full browser build and Django integration test suite must still be executed by CI on the deployment environment because this packaging environment does not contain the project's complete npm/Python dependency sets.
