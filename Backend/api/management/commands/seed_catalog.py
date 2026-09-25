from django.core.management.base import BaseCommand
from api.models import Tool, Resource, Workflow

# Curated, current developer-tool catalog. Descriptions are product-neutral and
# intentionally avoid fabricated community ratings or rankings.
TOOLS = [
    {"name":"React","tag":"Frontend","category":"Frontend","description":"Component-based UI for modern web applications.","accent":"cyan","rating":0,"features":["Components","Concurrent rendering","Server/client UI patterns"]},
    {"name":"TypeScript","tag":"Language","category":"Frontend","description":"Typed JavaScript for safer large-scale application development.","accent":"blue","rating":0,"features":["Static types","Editor tooling","Safer refactoring"]},
    {"name":"Next.js","tag":"Full-stack","category":"Frontend","description":"React framework for full-stack web applications and production delivery.","accent":"violet","rating":0,"features":["App Router","Server rendering","Route handlers"]},
    {"name":"Vite","tag":"Build","category":"Frontend","description":"Fast modern frontend tooling with a lean development and build pipeline.","accent":"purple","rating":0,"features":["Fast HMR","Production bundling","Plugin ecosystem"]},
    {"name":"Tailwind CSS","tag":"UI","category":"Design","description":"Utility-first CSS for consistent, responsive product interfaces.","accent":"cyan","rating":0,"features":["Design tokens","Responsive utilities","Component styling"]},
    {"name":"Playwright","tag":"Testing","category":"Testing","description":"End-to-end browser automation for reliable web application testing.","accent":"green","rating":0,"features":["Cross-browser tests","Tracing","Parallel execution"]},
    {"name":"Vitest","tag":"Testing","category":"Testing","description":"Fast unit and component testing designed for modern Vite projects.","accent":"green","rating":0,"features":["Fast tests","Mocking","Coverage"]},
    {"name":"Django","tag":"Backend","category":"Backend","description":"Secure Python web framework for APIs, applications and administration.","accent":"green","rating":0,"features":["ORM","Admin","Security primitives"]},
    {"name":"Django REST Framework","tag":"API","category":"Backend","description":"Production API toolkit for Django with serializers, permissions and authentication.","accent":"green","rating":0,"features":["Serializers","Permissions","Browsable APIs"]},
    {"name":"FastAPI","tag":"API","category":"Backend","description":"High-performance Python API framework built around type hints and OpenAPI.","accent":"cyan","rating":0,"features":["OpenAPI","Async support","Validation"]},
    {"name":"PostgreSQL","tag":"Database","category":"Data","description":"Production-grade relational database for transactional and analytical workloads.","accent":"blue","rating":0,"features":["Transactions","Indexes","JSONB"]},
    {"name":"Redis","tag":"Infrastructure","category":"Data","description":"In-memory data platform for caching, queues, rate limiting and realtime workloads.","accent":"red","rating":0,"features":["Caching","Streams","Queues"]},
    {"name":"Docker","tag":"Containers","category":"DevOps","description":"Portable application containers for reproducible development and deployment.","accent":"blue","rating":0,"features":["Images","Compose","Isolation"]},
    {"name":"Kubernetes","tag":"Orchestration","category":"DevOps","description":"Container orchestration for resilient, scalable production workloads.","accent":"blue","rating":0,"features":["Deployments","Services","Autoscaling"]},
    {"name":"Terraform","tag":"Infrastructure","category":"DevOps","description":"Infrastructure as code for repeatable cloud and platform provisioning.","accent":"violet","rating":0,"features":["Declarative config","State","Provider ecosystem"]},
    {"name":"GitHub","tag":"Code hosting","category":"Collaboration","description":"Repository hosting, code review, issues and engineering collaboration.","accent":"purple","rating":0,"features":["Repositories","Pull requests","Actions"]},
    {"name":"GitLab","tag":"DevSecOps","category":"Collaboration","description":"Source control and DevSecOps workflows across planning, CI and delivery.","accent":"orange","rating":0,"features":["CI/CD","Merge requests","Security workflows"]},
    {"name":"GitHub Actions","tag":"CI/CD","category":"DevOps","description":"Repository-native automation for build, test, release and deployment workflows.","accent":"purple","rating":0,"features":["Workflows","Runners","Environments"]},
    {"name":"Vercel","tag":"Deployment","category":"DevOps","description":"Cloud platform for frontend and full-stack web deployment.","accent":"white","rating":0,"features":["Preview deployments","Edge delivery","Observability"]},
    {"name":"Cloudflare","tag":"Edge","category":"DevOps","description":"Global edge platform for DNS, security, delivery and application services.","accent":"amber","rating":0,"features":["CDN","WAF","Workers"]},
    {"name":"Sentry","tag":"Observability","category":"DevOps","description":"Application monitoring for errors, performance and production debugging.","accent":"purple","rating":0,"features":["Error tracking","Performance","Release health"]},
    {"name":"OpenTelemetry","tag":"Observability","category":"DevOps","description":"Vendor-neutral telemetry standard for traces, metrics and logs.","accent":"cyan","rating":0,"features":["Tracing","Metrics","Logs"]},
    {"name":"Ruff","tag":"Python","category":"Backend","description":"Fast Python linter and formatter for consistent, high-speed code quality checks.","accent":"orange","rating":0,"features":["Linting","Formatting","Fast CI"]},
    {"name":"uv","tag":"Python","category":"Backend","description":"Fast Python package and environment management for modern projects.","accent":"green","rating":0,"features":["Dependency management","Virtual environments","Lockfiles"]},
    {"name":"Pytest","tag":"Testing","category":"Testing","description":"Extensible Python testing framework for unit and integration test suites.","accent":"blue","rating":0,"features":["Fixtures","Parametrization","Plugins"]},
    {"name":"Bun","tag":"Runtime","category":"Backend","description":"Modern JavaScript and TypeScript runtime, package manager and toolkit.","accent":"amber","rating":0,"features":["Runtime","Package manager","Bundling"]},
    {"name":"Supabase","tag":"Backend","category":"Data","description":"Postgres-centered backend platform with authentication, storage and APIs.","accent":"green","rating":0,"features":["Postgres","Auth","Storage"]},
    {"name":"Neon","tag":"Postgres","category":"Data","description":"Serverless PostgreSQL with branching and elastic infrastructure.","accent":"cyan","rating":0,"features":["Database branching","Autoscaling","Serverless Postgres"]},
    {"name":"LangGraph","tag":"AI","category":"AI","description":"Stateful orchestration for controllable, multi-step AI agent workflows.","accent":"violet","rating":0,"features":["State graphs","Tool calling","Human-in-the-loop"]},
    {"name":"Model Context Protocol","tag":"AI","category":"AI","description":"Open protocol for connecting AI applications with tools and contextual data.","accent":"purple","rating":0,"features":["Tools","Resources","Context exchange"]},
    {"name":"OpenAI API","tag":"AI","category":"AI","description":"API platform for building model-powered product and developer workflows.","accent":"green","rating":0,"features":["Structured output","Tool use","Multimodal models"]},
]

RESOURCES = [
    {"title":"React documentation","resource_type":"Official docs","category":"Frontend","description":"Official React documentation and current learning materials.","link":"https://react.dev/"},
    {"title":"TypeScript handbook","resource_type":"Official docs","category":"Frontend","description":"The official TypeScript language handbook and reference.","link":"https://www.typescriptlang.org/docs/"},
    {"title":"Vite guide","resource_type":"Official docs","category":"Frontend","description":"Modern frontend development and production build documentation.","link":"https://vite.dev/guide/"},
    {"title":"Django documentation","resource_type":"Official docs","category":"Backend","description":"Official Django documentation for web development and deployment.","link":"https://docs.djangoproject.com/"},
    {"title":"Django REST Framework","resource_type":"Official docs","category":"Backend","description":"API development patterns, serializers, permissions and authentication.","link":"https://www.django-rest-framework.org/"},
    {"title":"FastAPI documentation","resource_type":"Official docs","category":"Backend","description":"Modern Python API development with OpenAPI and type validation.","link":"https://fastapi.tiangolo.com/"},
    {"title":"PostgreSQL documentation","resource_type":"Official docs","category":"Data","description":"Authoritative PostgreSQL reference and administration documentation.","link":"https://www.postgresql.org/docs/"},
    {"title":"GitHub REST API","resource_type":"Official docs","category":"Integrations","description":"Current GitHub API reference, authentication and versioning guidance.","link":"https://docs.github.com/en/rest"},
    {"title":"GitHub Apps","resource_type":"Official docs","category":"Integrations","description":"Fine-grained repository integrations using GitHub Apps and short-lived tokens.","link":"https://docs.github.com/en/apps"},
    {"title":"OWASP API Security","resource_type":"Security","category":"Security","description":"API security guidance covering authorization, authentication and unsafe API consumption.","link":"https://owasp.org/API-Security/"},
    {"title":"OpenTelemetry documentation","resource_type":"Official docs","category":"Observability","description":"Vendor-neutral instrumentation and telemetry guidance.","link":"https://opentelemetry.io/docs/"},
    {"title":"Playwright documentation","resource_type":"Official docs","category":"Testing","description":"Cross-browser end-to-end testing and debugging documentation.","link":"https://playwright.dev/docs/"},
    {"title":"GitHub Actions documentation","resource_type":"Official docs","category":"DevOps","description":"Repository automation, CI/CD workflows and deployment environments.","link":"https://docs.github.com/en/actions"},
    {"title":"Vercel documentation","resource_type":"Official docs","category":"DevOps","description":"Deployment, functions, observability and platform workflows.","link":"https://vercel.com/docs"},
    {"title":"Cloudflare developer docs","resource_type":"Official docs","category":"DevOps","description":"Edge delivery, security and application platform documentation.","link":"https://developers.cloudflare.com/"},
]

WORKFLOWS = [
    {"title":"Production feature delivery","level":"Advanced","duration":"1–2 weeks","summary":"Move a feature from scope to monitored production with explicit quality gates.","steps":["Scope","Design","Implement","Test","Review","Deploy","Observe"]},
    {"title":"API-first delivery","level":"Advanced","duration":"2–5 days","summary":"Define a stable contract before implementation and verify authorization at every object boundary.","steps":["Model","Contract","Validate","Implement","Test","Document"]},
    {"title":"Secure release","level":"Advanced","duration":"Continuous","summary":"Use automated quality, security and deployment gates before every production release.","steps":["Lint","Test","Security scan","Build","Deploy","Verify","Monitor"]},
    {"title":"AI-assisted engineering","level":"Intermediate","duration":"Per feature","summary":"Use AI with explicit repository context, review gates and human ownership.","steps":["Context","Plan","Generate","Review","Test","Refine","Ship"]},
    {"title":"Incident response","level":"Advanced","duration":"Minutes–hours","summary":"Turn telemetry into a controlled response loop and documented recovery.","steps":["Detect","Triage","Contain","Fix","Verify","Document"]},
    {"title":"Repository onboarding","level":"Beginner","duration":"1–2 hours","summary":"Create a repeatable path from an unfamiliar repository to an actionable engineering plan.","steps":["Inspect","Map","Run","Test","Document","Plan"]},
    {"title":"Database change","level":"Advanced","duration":"1–3 days","summary":"Ship schema changes safely with backwards compatibility and rollback planning.","steps":["Model","Migration","Backfill","Validate","Deploy","Observe"]},
    {"title":"Frontend quality loop","level":"Intermediate","duration":"Per release","summary":"Keep UI changes accessible, responsive, tested and measurable.","steps":["Design","Implement","Accessibility","Test","Performance","Release"]},
]

class Command(BaseCommand):
    help = "Seed the shared Developer OS catalog without overwriting existing records."

    def handle(self, *args, **options):
        for item in TOOLS:
            Tool.objects.update_or_create(name=item["name"], defaults=item)
        for item in RESOURCES:
            Resource.objects.update_or_create(title=item["title"], defaults=item)
        for item in WORKFLOWS:
            Workflow.objects.update_or_create(title=item["title"], defaults=item)
        self.stdout.write(self.style.SUCCESS("Developer OS catalog is ready."))
