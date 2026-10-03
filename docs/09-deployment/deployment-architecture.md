# Deployment Architecture

> **Alignment:** This is a detail document. The canonical requirements, enums (modes, intents, statuses, result kinds), API surface, and SSE protocol are in [`REQUIREMENTS.md`](../../REQUIREMENTS.md). If anything here conflicts with it, `REQUIREMENTS.md` wins and this document must be corrected. Decisions: [`docs/01-decisions/decision-records.md`](../01-decisions/decision-records.md). Deployment requirements: REQUIREMENTS §12; configuration variables: §9.2.

## 1. Purpose

This document defines how Discover is packaged, deployed, configured, monitored, and operated in development, staging, and production.

The deployment architecture is intentionally lightweight. Discover should not require local AI inference, GPU infrastructure, Kubernetes, multiple backend services, or a large worker fleet for the initial MVP.

## 2. Deployment Goals

The deployment must:

- support the complete agentic discovery workflow
- keep Qloo credentials server-side
- use hosted AI services rather than local model inference
- keep the backend compatible with small container instances
- use PostgreSQL for durable application state
- allow frontend and backend to deploy independently
- provide health and readiness checks
- support environment-specific configuration
- provide useful logs without excessive resource usage
- remain easy to reproduce locally with Docker
- allow future scaling without rewriting the application architecture

## 3. Initial Production Topology

Recommended topology:

    User Browser
         │
         ▼
    Frontend Hosting
    Vercel / equivalent
         │ HTTPS
         ▼
    FastAPI Backend
    Lightweight container
         │
         ├──────────────► Hosted LLM
         │
         ├──────────────► Qloo API
         │
         └──────────────► PostgreSQL

The frontend and backend are separate deployments.

The backend is the only component that communicates directly with Qloo and the database.

## 4. Deployment Components

Initial production components:

| Component | Responsibility | Deployment |
|---|---|---|
| Frontend | Discovery UI | Static/managed frontend hosting |
| Backend | API and agent orchestration | Small container |
| PostgreSQL | Persistent state | Managed PostgreSQL |
| LLM provider | Hosted inference | External API |
| Qloo | Cultural intelligence | External API |
| Speech-to-text | Voice transcription | External API/service |

The speech-to-text provider may be selected independently from the LLM provider.

## 5. Backend Process Model

The backend should initially run as a single FastAPI application process.

Conceptually:

    uvicorn app.main:app

A production container may use an equivalent process command supplied by the hosting platform.

Do not start with multiple workers on a 512 MB-class instance unless measurement demonstrates that memory permits it.

The application should remain stateless at the process level.

Durable state belongs in PostgreSQL.

## 6. Why One Backend Service

The initial application does not need separate services for:

- agent orchestration
- Qloo integration
- search
- authentication
- discovery
- persistence

These should remain modules inside one backend service.

This reduces:

- memory overhead
- deployment complexity
- network latency
- operational cost
- debugging complexity

The internal module boundaries defined in the backend architecture still apply.

## 7. Resource Constraints

The deployment must assume constrained resources.

Primary principles:

- no local LLM
- no local embedding model
- no GPU requirement
- no vector database
- no large in-memory caches
- no background worker by default
- no unnecessary runtime dependencies
- bounded agent loops
- bounded request payloads
- bounded result counts

The backend should be designed to function within a small memory footprint.

## 8. Docker Image

Use a minimal Python image:

    python:3.12-slim

The image should:

- install only required dependencies
- avoid development tools in production
- avoid unnecessary OS packages
- run as a non-root user when practical
- expose the application port
- use a deterministic dependency installation strategy

Conceptual Docker structure:

    backend/
    ├── Dockerfile
    ├── requirements.txt
    ├── .dockerignore
    └── app/

## 9. Docker Build Principles

The Docker build should:

1. start from Python 3.12 slim
2. set a predictable working directory
3. copy dependency metadata first
4. install dependencies
5. copy application source
6. create/use a non-root runtime user
7. expose the application port
8. start FastAPI through Uvicorn

Dependency installation should be cache-friendly.

Development dependencies should not be included in the production image unless required.

## 10. Environment Configuration

Configuration must come from environment variables.

Example categories:

    APP_ENV
    APP_NAME
    LOG_LEVEL

    DATABASE_URL

    QLOO_API_KEY
    QLOO_BASE_URL

    LLM_API_KEY
    LLM_BASE_URL
    LLM_MODEL

    CORS_ORIGINS

    AUTH configuration

    RATE_LIMIT configuration

Secrets must never be committed to Git.

## 11. Environment Files

The repository should contain:

    .env.example

It must contain variable names and safe placeholder values only.

Local development may use:

    .env

The real .env file must be ignored by Git.

Production secrets must be configured through the hosting provider's secret/environment configuration.

## 12. Configuration Validation

The backend should validate required configuration during startup.

For example:

- database URL required in production
- Qloo API key required for Qloo functionality
- LLM credentials required for agent execution
- allowed CORS origins must be explicitly configured

Missing critical configuration should produce a clear startup error rather than a delayed runtime failure.

Secrets themselves must never be written to logs.

## 13. Frontend Deployment

The frontend should be deployed independently.

Required configuration:

    API_BASE_URL

The browser must never receive:

    QLOO_API_KEY
    DATABASE_URL
    LLM_API_KEY
    other backend secrets

Frontend environment variables must be treated as public unless the hosting platform explicitly guarantees server-side secrecy for a given variable.

## 14. CORS

The backend should explicitly allow the deployed frontend origin.

Development may allow:

    http://localhost:<frontend-port>

Production should use the exact production frontend origin.

Avoid allowing all origins in production.

If multiple legitimate frontend origins are required, configure them explicitly.

## 15. Database Deployment

Use managed PostgreSQL rather than running PostgreSQL inside the application container.

Reasons:

- durable storage
- backups
- simpler operations
- independent database lifecycle
- easier scaling
- no database process consuming backend memory

The application container should not own the database lifecycle.

## 16. Database Connections

The backend should use a small connection pool appropriate for the hosting instance.

Do not create a large connection pool by default.

The pool size should be configurable.

The application must close or release connections correctly.

Database connection exhaustion should be treated as an operational error rather than solved by blindly increasing pool size.

## 17. Database Migrations

Schema changes must use migrations.

The migration system should:

- version schema changes
- run deterministically
- support local development
- support production deployment
- avoid destructive operations without explicit migration logic

Migrations should be committed to the repository.

The deployment process should not silently recreate the production database.

## 18. Startup and Readiness

The backend exposes:

    GET /health
    GET /ready

Health:

- verifies the application process is alive
- should remain cheap
- should not depend on Qloo or the LLM

Readiness:

- verifies required local infrastructure, especially PostgreSQL
- may fail when the application cannot serve requests safely

Qloo and LLM outages should normally be represented as service-level failures rather than making the entire process unhealthy.

## 19. Deployment Lifecycle

Recommended deployment sequence:

    Git push
       ↓
    Build container
       ↓
    Run automated tests
       ↓
    Build production image
       ↓
    Deploy backend
       ↓
    Run/verify migrations
       ↓
    Health check
       ↓
    Readiness check
       ↓
    Accept traffic

Frontend deployment can occur independently after its API base URL is configured.

## 20. CI/CD

The repository should eventually run CI on pull requests and pushes.

Minimum CI stages:

1. dependency installation
2. formatting/lint checks
3. unit tests
4. API tests
5. build verification
6. frontend tests/build when frontend exists

Production deployment should only occur after the relevant checks succeed.

## 21. Local Development

Developers should be able to run the backend locally without recreating the production infrastructure manually.

Minimum local setup:

    Backend
    PostgreSQL
    Frontend

External Qloo and LLM APIs may be used through development credentials.

A local Docker Compose configuration can be introduced if useful, but it should not become a production requirement.

## 22. External Provider Connectivity

The backend communicates with:

    LLM
    Qloo
    optional current-information search
    optional speech-to-text

Each external provider must have:

- explicit timeout
- bounded retries
- error normalization
- structured logging
- no secret leakage

External requests must never be allowed to hang indefinitely.

## 23. Qloo Deployment Boundary

Qloo is reachable only from the backend.

Flow:

    Browser
       ↓
    Discover Backend
       ↓
    Qloo API

The Qloo API key is stored only in backend deployment secrets.

The frontend cannot construct arbitrary Qloo requests.

## 24. LLM Deployment Boundary

The LLM is also reachable only from the backend.

Flow:

    Browser
       ↓
    Discover Backend
       ↓
    LLM Provider

The backend controls:

- system instructions
- available tools
- model selection
- token limits
- retry policy
- structured output validation

The frontend sends user intent, not provider-specific prompts.

## 25. Agent Resource Limits

The deployment must enforce bounded agent execution.

Initial limits should be configurable, for example:

    MAX_AGENT_STEPS=8
    MAX_QLOO_CALLS_PER_DISCOVERY=...
    MAX_REFINEMENTS=3

Exact values should be tuned during testing.

The purpose is to prevent:

- infinite tool loops
- accidental provider cost spikes
- long-running requests
- excessive memory usage

## 26. Request Limits

The API should enforce reasonable limits on:

- message size
- request body size
- result count
- history page size
- saved item page size
- number of refinement operations

Limits should be configurable rather than scattered throughout application code.

## 27. Timeouts

Every external network request must have a timeout.

The backend should use separate timeout categories where appropriate:

- connection timeout
- read timeout
- total operation budget

The overall discovery request must also have a bounded execution budget.

A provider timeout should not leave an HTTP request open indefinitely.

## 28. Retry Strategy

Retries should be selective.

Retryable examples:

- transient network failures
- some 5xx upstream failures
- transient rate limiting when a safe retry delay is available

Usually non-retryable:

- invalid API key
- invalid request
- malformed tool input
- unsupported Qloo filter
- validation errors

Retries must be bounded.

A retry must not cause the agent to exceed its execution budget.

## 29. Rate Limiting

Application-level rate limiting should protect the backend and external providers.

Initial rate limiting may be applied to:

- discovery creation
- discovery messages
- voice transcription
- expensive discovery operations

The implementation should be compatible with the selected hosting architecture.

If the first deployment has only one backend instance, an in-process limiter may be sufficient for early testing. A shared external limiter can be introduced when horizontal scaling requires it.

## 30. Caching

Caching should remain conservative.

Good initial candidates:

- Qloo entity resolution
- stable tag lookups
- stable location resolution
- safe repeated metadata requests

Avoid large process-local caches on small instances.

Cache entries must have bounded lifetime and memory usage.

Do not cache personalized responses across users unless the cache key and privacy implications are explicitly understood.

## 31. Logging

Production logging should be structured and concise.

Each request should ideally include:

    request_id
    route
    method
    status
    duration_ms

Discovery operations may additionally record:

    session_id
    agent_step
    tool_name
    provider
    provider_latency_ms

Do not log:

- API keys
- access tokens
- passwords
- raw authorization headers
- unnecessary personal data
- complete prompts when they may contain sensitive user information
- complete provider payloads by default

## 32. Observability

The initial deployment does not require a large observability platform.

At minimum:

- application logs
- request IDs
- health endpoint
- readiness endpoint
- provider latency
- error counts
- deployment logs

As usage grows, add metrics and tracing selectively.

## 33. Error Monitoring

Unexpected backend exceptions should be captured by the hosting platform or an optional error-monitoring provider.

User-facing errors should remain generic.

Developer logs should contain enough context to identify:

- endpoint
- request ID
- session ID where appropriate
- failing component
- exception class
- safe error details

## 34. Data Privacy

Deployment must follow the application's data minimization requirements.

Do not persist provider credentials, raw API responses, or unnecessary sensitive user data.

The backend should store only the information required for:

- continuing discovery
- history
- saved discoveries
- preferences
- account functionality
- debugging within the defined retention policy

## 35. Backups

Managed PostgreSQL backups should be enabled where the chosen provider supports them.

Backups should be treated separately from application container storage.

The application must not depend on local container disk for durable user data.

## 36. Static and Uploaded Files

The initial architecture should avoid local persistent file storage.

If user uploads such as profile images or documents are introduced later, use object storage rather than the backend container filesystem.

Temporary files must be deleted after use.

## 37. Security

Production deployment must:

- use HTTPS
- keep secrets server-side
- restrict CORS
- validate all external input
- enforce authentication/authorization where required
- use secure database credentials
- avoid running containers as root where practical
- keep dependencies updated
- avoid exposing internal administrative endpoints
- avoid returning stack traces to users

## 38. Dependency Management

Production dependencies should be explicit.

The backend should maintain:

    requirements.txt

Dependency versions should be pinned or constrained deliberately enough to make builds reproducible.

Unused packages should be removed.

The initial dependency set should remain close to:

    fastapi
    uvicorn[standard]
    openai
    httpx
    pydantic
    python-dotenv
    psycopg[binary]

Additional packages should have a clear architectural reason.

## 39. Frontend Build

The frontend build should:

- install dependencies
- run type checking if applicable
- run tests
- produce an optimized production build
- use the configured backend API URL

No backend secrets should be embedded in the generated JavaScript bundle.

## 40. Deployment Platforms

The architecture should remain platform-neutral.

A practical initial arrangement is:

    Frontend → Vercel or equivalent
    Backend  → Render or equivalent container host
    Database → Managed PostgreSQL
    AI       → Hosted LLM API
    Cultural intelligence → Qloo API

The application should not rely on undocumented platform-specific behavior.

## 41. Scaling Strategy

Initial scale:

    1 frontend deployment
    1 backend instance
    1 managed PostgreSQL database

If demand grows:

    Frontend
        ↓
    Multiple stateless backend instances
        ↓
    Shared PostgreSQL
        ↓
    External providers

The backend architecture already keeps durable state outside the process, allowing horizontal scaling later.

## 42. Background Jobs

Do not introduce a worker queue in the initial MVP unless a concrete requirement appears.

Potential future background workloads:

- long-running enrichment
- scheduled recommendation refresh
- analytics aggregation
- large imports
- notification delivery

These can later use a dedicated worker and queue without changing the public discovery API.

## 43. Streaming

Streaming is optional.

Initial production can use standard HTTP request/response.

If streaming is introduced later, use it only for user-visible progress and response delivery.

Streaming must not be required for agent correctness.

## 44. Cold Starts

The application should minimize startup work.

Do not:

- load local AI models
- preload large datasets
- perform expensive provider requests during startup
- build large in-memory indexes

Startup should initialize configuration, database connectivity infrastructure, routes, and lightweight services.

## 45. Graceful Shutdown

The backend should release resources during shutdown:

- database connections
- HTTP clients
- background tasks if introduced

Requests already in progress should be allowed to terminate gracefully within the hosting platform's shutdown budget where possible.

## 46. Deployment Failure Recovery

If deployment fails:

1. retain the previous known-good deployment
2. inspect build/runtime logs
3. verify environment variables
4. verify database connectivity
5. verify migrations
6. verify health/readiness
7. roll back when necessary

Database migrations must be designed carefully so application rollback does not leave an incompatible schema.

## 47. Production Checklist

Before public demo deployment:

- [ ] HTTPS enabled
- [ ] Qloo key configured only on backend
- [ ] LLM key configured only on backend
- [ ] database configured
- [ ] migrations applied
- [ ] CORS restricted
- [ ] health endpoint works
- [ ] readiness endpoint works
- [ ] frontend API URL configured
- [ ] production build succeeds
- [ ] agent step limits configured
- [ ] provider timeouts configured
- [ ] retries bounded
- [ ] logs do not expose secrets
- [ ] error handling tested
- [ ] core discovery flow tested end-to-end
- [ ] anonymous/authenticated behavior tested as applicable

## 48. Hackathon Demo Deployment

The live demo should prioritize reliability over infrastructure complexity.

Recommended demo topology:

    Browser
       ↓
    Hosted Frontend
       ↓ HTTPS
    Single FastAPI Backend
       ↓
    PostgreSQL
       ↓
    Qloo + Hosted LLM

Before submitting the hackathon project:

- deploy a stable production version
- verify the public demo URL
- verify the public GitHub repository
- verify the open-source license
- verify Qloo functionality in the live environment
- test the primary discovery modes
- test failure recovery
- remove development-only secrets and logs
- record the exact deployment configuration needed to reproduce the demo

## 49. Definition of Done

Deployment architecture is ready for implementation when:

- production topology is defined
- backend process model is defined
- Docker strategy is defined
- environment configuration is defined
- PostgreSQL deployment is defined
- health/readiness behavior is defined
- provider timeout/retry rules are defined
- agent execution limits are defined
- CORS/security boundaries are defined
- logging/observability requirements are defined
- CI/CD expectations are defined
- scaling strategy is defined
- rollback considerations are documented
- hackathon demo requirements are explicit

## 50. Architectural Summary

Discover should be deployable as a small, understandable system:

    Frontend
        ↓
    One lightweight FastAPI service
        ↓
    PostgreSQL + external AI/Qloo services

The architecture deliberately moves computation that is expensive or difficult to host locally to managed APIs while keeping orchestration, state, security, and product logic under Discover's control.

The core deployment principle is:

> **Keep the runtime small, the boundaries explicit, and every expensive operation bounded.**


---

# Alignment addendum (REQUIREMENTS v1.0)

- **Environment variables:** the full list and defaults are REQUIREMENTS §9.2; `.env.example` at the repo root is the runnable reference.
- **SSE through the host:** disable response buffering (`X-Accel-Buffering: no`), keep heartbeats on, and verify idle-timeout behavior in staging before the demo (DEP-003). Cold-start UX and a keep-warm ping are required (NFR-005).
- **Local development:** `docker compose up` runs Postgres, backend, and frontend in the `mock` profile with no external keys (DEP-004).
- **Production guard:** startup refuses `DISCOVER_PROFILE=mock` unless `ALLOW_DEMO_MODE=true` (TST-004).
- **Frontend metadata route** for share previews (DEP-008, ADR-011).
