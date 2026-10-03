# Backend Architecture

> **Alignment:** This is a detail document. The canonical requirements, enums (modes, intents, statuses, result kinds), API surface, and SSE protocol are in [`REQUIREMENTS.md`](../../REQUIREMENTS.md). If anything here conflicts with it, `REQUIREMENTS.md` wins and this document must be corrected. Decisions: [`docs/01-decisions/decision-records.md`](../01-decisions/decision-records.md). Endpoint list: REQUIREMENTS §7.3. Run executor, registries, and configuration: §9.

## 1. Purpose

This document defines the backend architecture for Discover and turns the product, Qloo integration, and agent-state designs into a practical FastAPI application.

The backend must remain lightweight, modular, testable, secure, and suitable for a small deployment. It deliberately avoids LangChain, LangGraph, local AI models, local embeddings, and unnecessary infrastructure.

## 2. Responsibilities

The backend is responsible for receiving discovery requests, maintaining sessions, orchestrating the bounded agent, validating state, executing controlled tools, integrating Qloo and the hosted LLM, normalizing results, optionally retrieving current information, persisting relevant data, enforcing authorization, protecting provider credentials, and exposing stable API contracts.

The backend does not render the UI and the frontend never calls Qloo or the LLM provider directly.

## 3. High-Level Architecture

~~~text
Frontend
  |
 HTTPS
  v
FastAPI API
  |
  v
Application Services
  |
  v
Agent Orchestrator
  |
  +--> Tool Registry --> Qloo Adapter --> Qloo
  |
  +--> LLM Adapter --> Hosted LLM
  |
  +--> Current Search Adapter
  |
  +--> Repositories --> PostgreSQL
~~~

The important boundary is:

> The LLM decides; deterministic application services execute.

## 4. Technology Direction

Initial stack:

- Python 3.12
- FastAPI
- Uvicorn
- Pydantic
- httpx
- OpenAI-compatible hosted LLM client
- psycopg
- PostgreSQL
- python-dotenv for local development
- Docker

Initial dependency direction:

~~~text
fastapi
uvicorn[standard]
openai
httpx
pydantic
python-dotenv
psycopg[binary]
~~~

Additional packages require a concrete product or engineering reason.

## 5. Proposed Backend Structure

~~~text
backend/
├── Dockerfile
├── requirements.txt
├── .env.example
├── app/
│   ├── main.py
│   ├── config.py
│   ├── api/
│   │   ├── dependencies.py
│   │   ├── routes/
│   │   │   ├── auth.py
│   │   │   ├── discovery.py
│   │   │   ├── sessions.py
│   │   │   ├── history.py
│   │   │   └── saved.py
│   │   └── schemas/
│   ├── agent/
│   │   ├── orchestrator.py
│   │   ├── decisions.py
│   │   ├── prompts.py
│   │   └── state.py
│   ├── discovery/
│   │   ├── service.py
│   │   ├── evaluator.py
│   │   └── query_builder.py
│   ├── tools/
│   │   ├── registry.py
│   │   ├── executor.py
│   │   └── definitions.py
│   ├── qloo/
│   │   ├── client.py
│   │   ├── entities.py
│   │   ├── tags.py
│   │   ├── insights.py
│   │   └── models.py
│   ├── llm/
│   │   ├── client.py
│   │   └── models.py
│   ├── search/
│   │   └── current.py
│   ├── auth/
│   │   └── service.py
│   ├── db/
│   │   ├── connection.py
│   │   ├── models.py
│   │   └── repositories/
│   └── common/
│       ├── errors.py
│       ├── logging.py
│       └── utils.py
└── tests/
    ├── unit/
    ├── integration/
    └── api/
~~~

This is a growth direction. Files should be created when their subsystem is implemented rather than all at once.

## 6. Layer Responsibilities

### API layer

Owns HTTP, request validation, authentication dependencies, response serialization, and status codes. It should not contain Qloo logic or agent orchestration.

### Application layer

Owns discovery workflows, sessions, history, and saved discoveries.

### Agent layer

Owns next-action decisions, questions, tool selection, and bounded execution.

### Integration layer

Owns Qloo, LLM, and current-search providers.

### Persistence layer

Owns database connections, repositories, transactions, and persistence models.

## 7. Configuration

All secrets and deployment-specific values come from environment variables.

Example:

~~~text
APP_ENV=development
APP_HOST=0.0.0.0
APP_PORT=8000
DATABASE_URL=...
QLOO_API_KEY=...
LLM_API_KEY=...
LLM_BASE_URL=...
LLM_MODEL=...
CURRENT_SEARCH_API_KEY=...
JWT_SECRET=...
JWT_ALGORITHM=...
CORS_ORIGINS=...
~~~

No provider key belongs in source code, frontend code, logs, or API responses.

A typed Settings object should be the single configuration source for the application.

## 8. Application Startup

Startup should initialize:

1. configuration
2. logging
3. reusable HTTP clients
4. database pool
5. provider adapters
6. tool registry
7. application services
8. API routes

Shared HTTP clients should be reused instead of repeatedly creating connections for individual calls.

## 9. API Design

The public API is centered on discovery sessions.

~~~text
Summary (authoritative table: REQUIREMENTS §7.3; schemas: docs/08-api/api-contract.md)

POST   /api/v1/auth/guest
GET    /api/v1/me
POST   /api/v1/discovery/sessions
GET    /api/v1/discovery/sessions                      (history = filtered list)
GET    /api/v1/discovery/sessions/{id}
POST   /api/v1/discovery/sessions/{id}/messages        (SSE or JSON; starts a run)
GET    /api/v1/discovery/runs/{run_id}
GET    /api/v1/discovery/runs/{run_id}/events          (replay / resume)
POST   /api/v1/discovery/runs/{run_id}/cancel
GET    /api/v1/discovery/sessions/{id}/results
PUT    /api/v1/results/{result_id}/feedback
POST   /api/v1/saved            GET /api/v1/saved       GET|PATCH|DELETE /api/v1/saved/{id}
POST   /api/v1/reports          GET /api/v1/reports/{id}/export
POST   /api/v1/shares           GET /api/v1/public/shares/{token}
GET    /api/v1/meta             GET /health             GET /ready
~~~

Authentication endpoints depend on the selected authentication provider.

## 10. Create Discovery Session

POST /api/v1/discovery/sessions  (optionally with `initial_message`; messages then go to `/messages`)

Example message request:

~~~json
{
  "message": "I need a birthday gift for my girlfriend. She loves Taylor Swift and Korean dramas.",
  "mode": "someone_else"
}
~~~

The mode may be omitted so the agent can infer it.

Example response when information is missing:

~~~json
{
  "session_id": "uuid",
  "status": "needs_input",
  "question": "What is your approximate budget, and would you prefer a physical gift, an experience, or either?"
}
~~~

The API must not expose internal tool calls.

## 11. Continue Discovery

POST /api/v1/discovery/{session_id}/message

Example request:

~~~json
{
  "message": "About 100,000 naira, either one."
}
~~~

A response can be needs_input, complete, or failed.

Complete responses contain normalized discovery results and a user-facing response. Failed responses contain a stable error code and safe message.

## 12. Discovery Response Contract

Conceptually the public response is:

~~~python
class DiscoveryResponse(BaseModel):
    session_id: str
    status: Literal["needs_input", "complete", "failed"]
    question: str | None = None
    response: str | None = None
    results: list[DiscoveryResult] = []
    metadata: dict[str, Any] = {}
    error: ApiError | None = None
~~~

The frontend contract must remain independent of the raw Qloo response format.

## 13. Session Lifecycle

~~~text
created
  ↓
collecting
  ↓
ready
  ↓
discovering
  ↓
evaluating
  ↓
refining ────┐
  │          │
  └──────────┘
  ↓
complete
~~~

Failure and timeout can occur from any active state. A session may return to collecting when the agent asks a user question.

## 14. Stateless HTTP, Stateful Sessions

The API process should not depend on an in-memory object surviving between requests.

The pattern is:

~~~text
Request 1 → load session → run agent → save state → response
Request 2 → load session → run agent → save state → response
~~~

This supports restarts and multiple application instances.

## 15. Discovery Service

Routes should call a DiscoveryService rather than directly invoking the agent.

Conceptually:

~~~python
class DiscoveryService:
    async def start_discovery(...): ...
    async def continue_discovery(...): ...
    async def get_session(...): ...
~~~

The service loads state, applies the user message, invokes the orchestrator, persists changes, and builds the API response.

## 16. Agent Orchestrator

The orchestrator has one primary responsibility: execute a bounded decision loop over DiscoveryState.

It must not directly access PostgreSQL, construct raw Qloo HTTP requests, read environment variables, or contain FastAPI route logic.

Those responsibilities belong to the relevant services and adapters.

## 17. LLM Adapter

The LLM provider is hidden behind a small adapter.

Conceptually:

~~~python
class LLMClient:
    async def decide(self, state, tools) -> AgentDecision:
        ...
~~~

The adapter owns provider authentication, model selection, structured output, timeouts, and provider error mapping.

The rest of the application should not depend directly on one provider SDK.

## 18. Structured Agent Decisions

The preferred model output is structured.

~~~json
{
  "action": "call_tool",
  "tool_name": "resolve_entity",
  "tool_arguments": {
    "query": "Taylor Swift",
    "expected_type": "music"
  }
}
~~~

The backend validates this against AgentDecision before execution. Invalid structured output is a controlled model error, not executable arbitrary content.

## 19. Qloo Adapter

The Qloo integration is isolated behind application-level methods.

~~~python
class QlooClient:
    async def search_entities(...): ...
    async def search_tags(...): ...
    async def search_locations(...): ...
    async def insights(...): ...
~~~

The adapter owns the Qloo API key, HTTP headers, URLs, Qloo parameter syntax, response parsing, and Qloo-specific errors.

The agent does not know raw Qloo HTTP syntax.

## 20. Qloo Request Path

~~~text
DiscoveryState
  ↓
Query Builder
  ↓
QlooDiscoveryRequest
  ↓
Qloo Insights Service
  ↓
Qloo Client
  ↓
Qloo API
~~~

This boundary isolates future Qloo API changes.

## 21. Query Builder

The query builder is deterministic application code.

~~~python
def build_qloo_request(state: DiscoveryState) -> QlooDiscoveryRequest:
    ...
~~~

It maps target type, resolved entities, tags, location, audience, filters, exclusions, result count, and explainability into the internal Qloo request model.

The LLM does not generate arbitrary Qloo parameter names.

## 22. Tool Executor

The tool executor is the safety boundary between model output and application code.

~~~text
Agent decision
  ↓
Validate action
  ↓
Validate tool name
  ↓
Validate arguments
  ↓
Check limits
  ↓
Execute with timeout
  ↓
Normalize result
  ↓
Update state
~~~

It must enforce tool allow-listing, argument validation, timeouts, retries, counters, and normalized errors.

## 23. Tool Context

Tools receive dependencies through application context rather than secrets in arguments.

Conceptually:

~~~python
class ToolContext:
    qloo: QlooClient
    search: CurrentSearchClient
    user_id: str | None
    session_id: str
~~~

## 24. Current Information

Current search is a separate adapter because Qloo cultural intelligence is not a substitute for every operational fact.

Example:

~~~text
Qloo cultural shortlist
  ↓
Current-information search
  ↓
Final answer
~~~

Use current search for facts such as current opening hours, current event dates, current prices, availability, and recent announcements.

## 25. Database Architecture

PostgreSQL is the initial persistence target.

Core entities are conceptually:

~~~text
User
  |
  +-- DiscoverySession
  |      +-- DiscoveryMessage
  |      +-- DiscoveryState
  |      +-- DiscoveryResult
  |
  +-- SavedDiscovery
  |
  +-- UserPreference
~~~

The detailed schema belongs in the database architecture document.

## 26. Repository Boundary

Database access is isolated from application services.

~~~text
DiscoveryService
  ↓
DiscoveryRepository
  ↓
PostgreSQL
~~~

Repositories perform persistence operations, not business decisions.

## 27. Transactions

Do not hold database transactions open while waiting on LLM or Qloo calls.

A safe pattern is:

~~~text
load state
  ↓
apply user message
  ↓
run bounded agent
  ↓
persist resulting state
  ↓
commit
~~~

Provider failures must preserve the user's conversation and avoid corrupting the session.

## 28. Authentication and Authorization

The backend should use an established authentication mechanism rather than implementing password security from scratch.

Business logic should depend on an internal authenticated-user abstraction rather than a specific auth provider.

Every user-owned resource must verify ownership before read, update, save, or delete operations.

A session ID alone is never authorization.

## 29. CORS and Input Validation

CORS should explicitly list the deployed frontend origin in production.

Pydantic validation should reject malformed IDs, unsupported modes, invalid numeric ranges, oversized messages, and unsupported target types before provider calls.

Configurable limits should apply to message length, preferences, entities, results, tool calls, and refinements.

## 30. Timeouts and Error Mapping

Every external dependency needs an explicit timeout.

Suggested stable error categories:

~~~text
VALIDATION_ERROR
AUTHENTICATION_ERROR
RATE_LIMITED
TIMEOUT
NOT_FOUND
PROVIDER_ERROR
EMPTY_RESULT
INTERNAL_ERROR
~~~

Raw stack traces and provider internals must never be returned to users.

## 31. Retry Policy

Initial defaults:

- at most 2 transient retries
- exponential backoff
- no retry for invalid requests
- no retry for authentication failures
- stop retrying when execution limits are reached

Configuration should live centrally rather than inside individual tools.

## 32. Logging and Observability

Useful logs include:

- request ID
- session ID
- agent step
- tool name
- provider latency
- provider status
- result count
- final status
- error category

Do not log API keys, authorization tokens, or full sensitive user content by default.

Track request duration, LLM latency, Qloo latency, tool counts, agent steps, refinement counts, and error categories.

## 33. Correlation IDs

Request ID and session ID serve different purposes.

~~~text
request ID = one HTTP operation
session ID = one discovery conversation
~~~

Together they allow an execution to be traced without relying on raw user content.

## 34. Caching

Good initial cache candidates are entity resolution, tag search, and location resolution.

Recommendation caching must be more conservative because results depend on query, location, and provider behavior.

User-specific state must not be served from a shared cache.

## 35. Concurrency

The first implementation should favor predictable sequential execution.

~~~text
resolve entity A
  ↓
resolve entity B
  ↓
build query
  ↓
call Qloo
  ↓
evaluate
~~~

Parallel independent lookups can be introduced later if provider limits and correctness are understood.

## 36. Voice Boundary

Voice is an input channel rather than a separate discovery system.

~~~text
Voice
  ↓
Speech-to-text provider
  ↓
Text message
  ↓
Discovery API
  ↓
Normal agent flow
~~~

The core agent therefore remains independent of the speech provider.

## 37. Streaming and Background Jobs

Streaming is not required for the first backend milestone.

Background queues are also not required for the core interactive discovery flow. They may later support analytics, cleanup, notifications, or long-running reports.

## 38. Docker

Initial base image:

~~~dockerfile
FROM python:3.12-slim
~~~

The image should install only required dependencies, receive secrets from environment variables, avoid local model downloads, and run Uvicorn on the host-provided port.

Example runtime direction:

~~~text
uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
~~~

## 39. Small Deployment Strategy

For a small Render-style instance:

1. use Python slim
2. keep dependencies minimal
3. avoid ML libraries
4. reuse HTTP connections
5. limit provider result sizes
6. avoid background worker processes
7. avoid local model files
8. use external PostgreSQL
9. keep logs bounded
10. offload AI computation to hosted services

## 40. Health Endpoints

~~~text
GET /health
GET /ready
~~~

Health checks must not expose credentials.

## 41. API Versioning and OpenAPI

Public routes use /api/v1/ so contracts can evolve without immediately breaking the frontend.

FastAPI's OpenAPI schema should document public request models, response models, authentication requirements, and error responses.

Internal tools remain internal and do not become public HTTP endpoints merely because they are agent tools.

## 42. Testing Architecture

### Unit tests

Test state validation, readiness, query construction, normalization, error mapping, refinement detection, and execution limits.

### Integration tests

Mock Qloo, LLM, search, and database boundaries and verify provider adapters.

### API tests

Test complete FastAPI behavior including creating sessions, continuing sessions, authorization, history, and saved discoveries.

Live Qloo and LLM calls should not be required for normal CI tests.

## 43. Security Requirements

The backend must:

- keep Qloo and LLM keys server-side
- require authentication for user-owned resources
- validate every model-generated tool call
- validate external provider responses
- use HTTPS in production
- restrict CORS
- avoid secret logging
- enforce input limits
- treat external content as untrusted data
- protect against prompt-injection effects
- derive ownership from authentication rather than client input

## 44. Personal Discovery Flow

~~~text
Frontend
  ↓
POST /discovery
  ↓
DiscoveryService
  ↓
AgentOrchestrator
  ↓
Extract preferences
  ↓
Resolve entities
  ↓
Query Builder
  ↓
Qloo Adapter
  ↓
Qloo
  ↓
Normalize results
  ↓
Evaluate
  ↓
Response
~~~

## 45. Gift Discovery Flow

~~~text
User message
  ↓
Create gift session
  ↓
Extract subject, interests, goal, constraints
  ↓
Missing information detected
  ↓
Question returned
  ↓
User answers
  ↓
Session resumes
  ↓
Entity resolution
  ↓
Qloo discovery
  ↓
Evaluation/refinement
  ↓
Gift discoveries
~~~

## 46. Business Discovery Flow

~~~text
Business request
  ↓
Business DiscoveryState
  ↓
Resolve category and cultural signals
  ↓
Location/audience context
  ↓
Qloo cross-domain discovery
  ↓
Normalize relationships
  ↓
Agent interpretation
  ↓
Optional current-information research
  ↓
Business insight response
~~~

Business interpretations should be presented as insights or opportunities, not guarantees.

## 47. Implementation Order

### Step 1 — Backend skeleton

Create FastAPI, configuration, health endpoints, error handling, and Dockerfile.

### Step 2 — State models

Implement DiscoveryState and decision models from the agent architecture document.

### Step 3 — LLM adapter

Implement structured agent decisions.

### Step 4 — Tool infrastructure

Implement registry, executor, validation, limits, timeout, and retry handling.

### Step 5 — Qloo adapter

Implement entity search, tag search, location resolution, insights, response normalization, and explainability mapping.

### Step 6 — Query builder

Implement deterministic DiscoveryState to QlooDiscoveryRequest mapping.

### Step 7 — Agent loop

Connect LLM, state, tools, evaluator, and bounded execution.

### Step 8 — Discovery API

Expose create, continue, and get discovery session endpoints.

### Step 9 — PostgreSQL

Persist sessions and results.

### Step 10 — Authentication

Connect the selected authentication provider.

### Step 11 — History and saved discoveries

Add user-facing persistence features.

### Step 12 — Current information

Add current-search integration where required.

### Step 13 — Voice

Add speech-to-text as an input adapter.

## 48. Definition of Done

The first backend milestone is complete when:

- FastAPI starts successfully
- configuration is environment-driven
- health endpoints work
- discovery requests have typed contracts
- DiscoveryState persists between requests
- agent decisions are structured and validated
- arbitrary tool calls are rejected
- Qloo keys remain server-side
- Qloo calls pass through the adapter
- Qloo responses are normalized
- agent execution is bounded
- provider failures become safe API errors
- at least one discovery mode works end-to-end
- the system runs in a small container without local AI models

## 49. Architectural Summary

The backend is a thin, controlled orchestration layer:

~~~text
Frontend
  ↓
FastAPI
  ↓
DiscoveryService
  ↓
Bounded Agent
  ↓
Validated Tools
  ├── Qloo
  ├── Hosted LLM
  └── Current Search
  ↓
Normalized Results
  ↓
PostgreSQL
  ↓
Frontend
~~~

The most important rules are:

> Keep intelligence, orchestration, integrations, and persistence separate.

> Keep the public API stable even when Qloo, the LLM provider, or internal agent implementation changes.

> Prefer the smallest architecture that supports the actual product, then expand only when a requirement demands it.
