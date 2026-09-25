# Developer Workflows

Developer OS is designed around the complete engineering loop rather than isolated task records.

## Project intake

1. Create a project.
2. Add the repository and stack.
3. Define the initial milestone.
4. Add the first tasks.
5. Capture relevant notes and references.

## Daily execution

1. Open the workspace.
2. Review active and blocked tasks.
3. Select the next concrete action.
4. Update task status as work progresses.
5. Record decisions in notes or snippets.

## Knowledge capture

Use Resources for durable external references and Notes for project-specific context. Save reusable code in Snippets and frequently used catalog items in Favorites.

## Collaboration

Project owners can add registered developers as collaborators. The API enforces membership before exposing project-scoped data.

## AI workflow

AI requests are grounded in workspace signals such as projects, task status, deadlines and recent work. When an external model is configured, the provider receives only the generated workspace context and the user's request.

## Release workflow

1. Complete the implementation.
2. Run linting and tests.
3. Build the frontend.
4. Validate the production configuration.
5. Deploy.
6. Check `/api/health/`.
7. Verify authentication and core CRUD flows.
8. Monitor errors and external integrations.

## Operational principle

Developer OS should preserve context from planning through delivery: project intent, tasks, decisions, references, code snippets, collaboration and release signals should remain connected rather than being scattered across unrelated screens.
