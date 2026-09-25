# Developer OS Architecture

## Runtime

Developer OS is a two-tier web application:

```text
React/Vite browser application
        │
        ▼
Django REST API
        │
        ▼
PostgreSQL
```

Nginx serves the compiled frontend and proxies `/api/` and `/media/` to Django.

## Frontend

The frontend is organized around:

- public discovery pages
- authenticated workspace
- project modules
- knowledge modules
- integration surfaces
- account/profile surfaces
- shared command-center styling

The API client centralizes authentication, refresh-token rotation, errors and request handling.

## Backend

The active Django application is `api/`.

Responsibilities:

- identity and authentication
- authorization boundaries
- project lifecycle
- task lifecycle
- notes and snippets
- catalog data
- collaboration
- activity
- GitHub integration
- workspace intelligence
- AI provider boundary

## Data

PostgreSQL is the production database. SQLite remains available for lightweight local development.

Core entities:

- User
- UserProfile
- Project
- Task
- Note
- Snippet
- Activity
- Tool
- Resource
- Workflow
- Favorite
- Tag
- GitHubAccount
- GitHubOAuthState

## Authorization

Every user-owned endpoint must scope object queries to the authenticated user or an explicit project collaboration relationship. Shared catalog mutation is restricted to staff.

## External services

GitHub is accessed only from the backend so credentials never reach the browser. GitHub requests use an explicit API version and authenticated requests.

The AI boundary accepts an OpenAI-compatible provider. Workspace context is assembled server-side and limited to the authenticated user's data.

## Deployment

Production containers:

- PostgreSQL
- Django/Gunicorn
- Nginx/React

Secrets are injected through environment variables. Static frontend assets are immutable and cached by Nginx.

## Design goals

1. secure by default
2. explicit authorization
3. predictable API contracts
4. resilient authentication
5. production observability hooks
6. modular product surfaces
7. clear separation between public catalog and private workspace
