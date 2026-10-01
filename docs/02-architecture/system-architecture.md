# Discover — System Architecture

**Status:** Draft — Version 0.1  
**Source of truth:** REQUIREMENTS.md  
**Primary external intelligence:** Qloo Cultural Intelligence API

---

## 1. Architecture Goals

Discover's architecture should:

1. Make the agent genuinely tool-using and iterative.
2. Keep Qloo central to discovery rather than treating it as enrichment.
3. Separate conversational context from structured discovery state.
4. Remain lightweight enough for a small hosted backend.
5. Keep external API details behind adapters/services.
6. Support text and voice through the same discovery pipeline.
7. Make agent execution bounded, observable, and testable.
8. Allow the product to grow from consumer discovery into community and business discovery without rewriting the core agent.

---

## 2. High-Level Architecture

```text
                         ┌───────────────────────┐
                         │       Frontend        │
                         │ React + TypeScript     │
                         │                       │
                         │ Text / Voice / UI     │
                         └───────────┬───────────┘
                                     │ HTTPS
                                     ▼
                         ┌───────────────────────┐
                         │      FastAPI API      │
                         │                       │
                         │ Auth / Sessions       │
                         │ Discovery endpoints  │
                         │ Conversation API     │
                         └───────────┬───────────┘
                                     │
                                     ▼
                         ┌───────────────────────┐
                         │ Discovery Orchestrator│
                         │                       │
                         │ State → LLM → Tools  │
                         │ bounded execution     │
                         └──────┬─────────┬──────┘
                                │         │
                    ┌───────────┘         └────────────┐
                    ▼                                  ▼
          ┌──────────────────┐               ┌──────────────────┐
          │   Tool Layer     │               │   LLM Adapter    │
          │                  │               │                  │
          │ Entity Resolver  │               │ Hosted LLM API   │
          │ Qloo Insights    │               │ Structured output│
          │ Search (optional)│               └──────────────────┘
          └────────┬─────────┘
                   │
                   ▼
          ┌──────────────────┐
          │    Qloo Adapter  │
          │                  │
          │ Lookup           │
          │ Insights         │
          │ Normalization    │
          └────────┬─────────┘
                   │
                   ▼
              ┌─────────┐
              │ Qloo API│
              └─────────┘

          ┌──────────────────────┐
          │     PostgreSQL       │
          │ Users / Sessions     │
          │ Messages / State     │
          │ Results / Saved data │
          └──────────────────────┘
```

The diagram describes logical boundaries. The first implementation should avoid turning every box into a separate deployable service.

---

## 3. Architectural Layers

### 3.1 Presentation Layer

Responsible for:

- Authentication UI
- Discovery workspace
- Text input
- Voice input
- Conversation display
- Agent activity state
- Results
- Result details
- Saving/refining discoveries
- Settings

The frontend should not contain Qloo API credentials or raw Qloo request construction.

### 3.2 API Layer

FastAPI exposes stable application endpoints.

Responsibilities:

- Validate incoming requests.
- Authenticate users.
- Load required state.
- Start/resume discovery sessions.
- Invoke the discovery orchestrator.
- Persist relevant results.
- Return stable response schemas.

The API layer should not contain the agent's decision-making logic.

### 3.3 Agent Layer

The agent layer is the application's decision-making runtime.

Responsibilities:

- Interpret the user's goal.
- Maintain structured discovery state.
- Decide whether information is missing.
- Ask follow-up questions.
- Select tools.
- Execute tools.
- Inspect tool results.
- Refine discovery.
- Produce a final response.

This is a custom orchestration loop, not LangChain or LangGraph.

### 3.4 Tool Layer

Tools expose capabilities to the agent through stable schemas.

Examples:

- Resolve entity
- Resolve tag/category
- Query Qloo
- Search current information
- Evaluate discovery results

Tools should return structured data rather than arbitrary prose whenever practical.

### 3.5 Integration Layer

External-service adapters isolate vendor-specific implementation.

Initial integrations:

- Qloo
- Hosted LLM
- Speech-to-text provider
- Optional current-information search provider

The rest of the application should not depend directly on vendor-specific HTTP details.

### 3.6 Persistence Layer

PostgreSQL stores durable application state.

The database should not become a replacement for the in-memory agent state used during one execution. Persistence exists to resume sessions, support history, personalization, and saved discoveries.

---

## 4. Discovery Request Lifecycle

A typical discovery request follows this lifecycle:

```text
1. User submits text or voice
             ↓
2. Voice is transcribed if necessary
             ↓
3. API validates request
             ↓
4. Discovery session is loaded/created
             ↓
5. Agent state is loaded
             ↓
6. LLM interprets current state + new input
             ↓
7. Agent decides:
      ├── ask user
      ├── call tool
      └── complete
             ↓
8. Tools execute
             ↓
9. Tool results update state
             ↓
10. Agent evaluates whether discovery is sufficient
             ↓
11. Optional refinement / additional Qloo call
             ↓
12. Final answer generated
             ↓
13. Results/state persisted
             ↓
14. API returns response
```

The same lifecycle should work whether the request is for the user, someone else, a community, or a business.

---

## 5. Agent Architecture

### 5.1 Core Runtime

The agent should use a bounded loop conceptually equivalent to:

```text
while steps < MAX_STEPS:

    response = LLM(state)

    if response asks for user input:
        return NEEDS_INPUT

    if response contains tool calls:
        execute tools
        update state
        continue

    return COMPLETE
```

The exact implementation may use Pydantic models and normal Python functions rather than a large framework.

### 5.2 Agent Responsibilities

The agent should decide:

- What the user is trying to accomplish.
- Which discovery mode applies.
- What information is already known.
- What information is missing.
- Whether missing information matters enough to ask.
- Which tool should be called.
- Whether Qloo results are sufficient.
- Whether another discovery iteration is useful.
- When the task is complete.

### 5.3 What the Agent Should Not Do

The agent should not:

- Construct arbitrary raw Qloo HTTP requests.
- Access Qloo API credentials directly.
- Bypass tool validation.
- Run without a step limit.
- Treat every user message as a new unrelated task.
- Invent evidence for recommendation explanations.
- Store arbitrary sensitive information merely because it appeared in conversation.

---

## 6. Structured Discovery State

A conceptual state model:

```text
DiscoveryState
├── session
│   ├── id
│   ├── user_id
│   └── status
│
├── request
│   ├── mode
│   ├── goal
│   └── original_input
│
├── subject
│   ├── type
│   └── description
│
├── preferences
│   ├── interests
│   ├── dislikes
│   └── style/context signals
│
├── constraints
│   ├── budget
│   ├── location
│   ├── timing
│   └── other constraints
│
├── qloo
│   ├── resolved_entities
│   ├── resolved_tags
│   ├── requests
│   └── results
│
├── interaction
│   ├── missing_information
│   ├── questions_asked
│   └── user_answers
│
├── refinement
│   ├── iterations
│   └── decisions
│
└── execution
    ├── step_count
    ├── errors
    └── status
```

This is a logical model. The persistence schema will be defined separately.

---

## 7. State Ownership

| State | Primary owner | Persistence |
|---|---|---|
| Raw messages | Conversation service | PostgreSQL |
| Current discovery state | Agent/orchestrator | In memory + PostgreSQL snapshot |
| Qloo results | Discovery service | PostgreSQL when useful |
| Tool execution metadata | Agent runtime | Logs + optional persisted metadata |
| Saved discoveries | Result service | PostgreSQL |
| User preferences | Profile service | PostgreSQL |

A request should not require replaying an unlimited conversation history into the LLM.

---

## 8. Tool Execution Model

Tools should have a common conceptual contract:

```text
Tool input
    ↓
Validation
    ↓
Execution
    ↓
Structured result
    ↓
State update
    ↓
LLM
```

Each tool should define:

- Name
- Description
- Input schema
- Output schema
- Timeout
- Retry policy
- Error mapping

The agent receives tool definitions, but vendor-specific implementation remains outside the agent.

---

## 9. Qloo Integration Architecture

Qloo is separated into a dedicated adapter/service boundary.

```text
Agent
  ↓
Qloo Tool
  ↓
Qloo Service
  ↓
Qloo Adapter
  ↓
Qloo API
```

### Lookup responsibilities

The lookup layer should resolve natural-language entities and other supported identifiers needed for discovery.

### Insights responsibilities

The insights layer should construct supported recommendation/taste/location/audience requests based on the structured discovery state.

### Response normalization

Qloo responses should be normalized into an internal representation before being passed back to the agent.

The internal representation should contain only fields the application actually needs, for example:

- entity identity
- entity type
- display name
- image/reference data where available
- category
- Qloo relevance information where available
- location information where available
- source metadata
- raw response reference for debugging where appropriate

The exact fields must be finalized after the official Qloo API schemas are documented.

---

## 10. LLM Architecture

The LLM is an external reasoning component.

The application should use a provider adapter rather than scattering vendor SDK calls throughout the codebase.

Conceptually:

```text
Agent
  ↓
LLM Adapter
  ↓
Hosted Model
```

The adapter should support:

- System instructions
- Structured agent decisions
- Tool definitions
- Tool-call responses
- Normal text responses
- Timeout/error handling

The selected model can change without changing the rest of the agent architecture.

---

## 11. Voice Architecture

Voice is an input transport rather than a separate agent.

```text
Microphone
   ↓
Frontend audio capture
   ↓
Speech-to-text service
   ↓
Text
   ↓
Normal Discovery API
```

This keeps voice-specific logic out of the discovery engine.

The initial implementation should not require the backend to run speech recognition locally.

---

## 12. Current-Information Search

Some discoveries require information that changes frequently, such as:

- current opening status
- current event availability
- current product availability
- current prices
- current business details

Qloo should remain the cultural intelligence layer. A separate search capability may be used when current factual verification is required.

The agent should not automatically search the web for every request.

---

## 13. Result Evaluation

Qloo results should not automatically become final recommendations.

The evaluation stage should check:

1. Does the result match the requested category?
2. Does it satisfy explicit constraints?
3. Does it align with the relevant cultural signals?
4. Is location relevant?
5. Is there enough evidence to explain the recommendation?
6. Is another Qloo query likely to materially improve the result?

This can produce one of three outcomes:

```text
SUFFICIENT
    ↓
Generate final response

INSUFFICIENT
    ↓
Refine query / call tool again

MISSING_USER_INFORMATION
    ↓
Ask user
```

---

## 14. Explanation Architecture

Recommendation explanations must distinguish between:

### Evidence

Information directly returned by an external source such as Qloo.

### User context

Preferences or constraints explicitly provided by the user.

### Agent interpretation

A reasoned connection made by the LLM from the available evidence.

The UI may combine these into a natural explanation, but the internal model should preserve the distinction so the system does not present an inferred claim as if Qloo explicitly stated it.

---

## 15. Backend Module Direction

The first implementation can use a structure similar to:

```text
backend/
├── app/
│   ├── main.py
│   ├── config.py
│   │
│   ├── api/
│   │   ├── routes/
│   │   └── schemas/
│   │
│   ├── agent/
│   │   ├── orchestrator.py
│   │   ├── state.py
│   │   ├── prompts.py
│   │   └── decisions.py
│   │
│   ├── tools/
│   │   ├── registry.py
│   │   ├── entity_resolution.py
│   │   ├── qloo_insights.py
│   │   └── current_search.py
│   │
│   ├── integrations/
│   │   ├── qloo/
│   │   ├── llm/
│   │   └── speech/
│   │
│   ├── services/
│   │   ├── discovery.py
│   │   ├── conversations.py
│   │   └── results.py
│   │
│   ├── db/
│   │   ├── models.py
│   │   ├── session.py
│   │   └── migrations/
│   │
│   └── core/
│       ├── errors.py
│       └── logging.py
│
└── tests/
```

This is a starting structure, not a requirement to create every file immediately.

---

## 16. Frontend Architecture Direction

The frontend should be organized around product features rather than API endpoints.

Possible structure:

```text
frontend/
├── src/
│   ├── app/
│   ├── components/
│   ├── features/
│   │   ├── discovery/
│   │   ├── conversations/
│   │   ├── results/
│   │   ├── saved/
│   │   └── settings/
│   ├── pages/
│   ├── services/
│   ├── hooks/
│   ├── types/
│   └── styles/
└── tests/
```

The detailed UI/page specification will define the final structure.

---

## 17. Data Flow for a Gift Discovery

Example:

```text
User:
"I need a birthday gift for my girlfriend.
She loves Taylor Swift and Korean dramas."

        ↓

Agent extracts:

mode = gift
subject = girlfriend
goal = birthday gift
signals = Taylor Swift, Korean dramas

        ↓

Agent evaluates missing information

Missing:
budget
location
physical vs experience

        ↓

Agent asks:
"What is your approximate budget, and would
you prefer a physical gift or an experience?"

        ↓

User answers

        ↓

Agent resolves relevant entities

        ↓

Qloo lookup / insights

        ↓

Qloo results

        ↓

Result evaluation

        ↓

Optional refinement

        ↓

Final discoveries + explanations
```

---

## 18. Data Flow for Business Discovery

```text
Business goal
    ↓
Target audience / market
    ↓
Existing product / brand / category
    ↓
Agent identifies missing business context
    ↓
Resolve Qloo entities / tags
    ↓
Qloo cultural intelligence
    ↓
Audience / category / location relationships
    ↓
Agent interpretation
    ↓
Business discovery report
```

Business output should be framed as cultural intelligence and opportunities to investigate, not guaranteed commercial outcomes.

---

## 19. Agent Execution Limits

Initial defaults should be configurable rather than hard-coded into business logic.

Candidate limits:

- Maximum agent steps: 8
- Maximum tool retries: 2
- Per-tool timeout: 10–20 seconds depending on service
- Overall request timeout: bounded by the API deployment platform
- Maximum refinement iterations: 2–3

These values are initial engineering targets and should be validated during implementation.

---

## 20. Error Boundaries

Errors should be handled at clear boundaries:

```text
Frontend
  ↓
API validation error

Agent
  ↓
Decision/tool error

Tool
  ↓
Integration error

Integration
  ↓
External API error
```

Internal details should be logged, while the user receives a concise recovery message.

Examples:

- Qloo unavailable → explain that discovery service is temporarily unavailable and offer retry.
- No Qloo matches → broaden or clarify the request.
- LLM failure → retry within bounded limits, then fail gracefully.
- Missing information → ask the user rather than guessing.

---

## 21. Security Boundaries

Secrets belong only on the backend.

```text
Frontend
  X Qloo API key
  X LLM API key
  X Database credentials

Backend
  ✓ Qloo API key
  ✓ LLM credentials
  ✓ Database credentials
```

The frontend communicates with the backend using authenticated application requests.

---

## 22. Deployment Architecture

Initial deployment target:

```text
Browser
   ↓
Hosted Frontend
   ↓ HTTPS
Hosted FastAPI Container
   ├── Hosted LLM API
   ├── Qloo API
   ├── Speech-to-text API
   └── PostgreSQL
```

The backend should be stateless at the process level where practical. Durable state belongs in PostgreSQL.

This supports container restarts and horizontal scaling later without redesigning the discovery model.

---

## 23. Resource Constraints

Because the first backend may run on a small hosted instance:

- No local model inference.
- No local vector database.
- No unnecessary data-processing libraries.
- No large in-memory datasets.
- Use async HTTP clients.
- Keep connection pools small.
- Bound conversation context.
- Avoid duplicate external requests.
- Prefer simple modules over heavyweight frameworks.

The architecture should optimize for correctness and useful agent behavior before premature scaling.

---

## 24. Architecture Decisions

### ADR-001 — Custom agent orchestration

**Decision:** Use a lightweight custom Python agent loop.

**Reason:** Discover needs a bounded, transparent orchestration layer and should avoid unnecessary framework overhead.

### ADR-002 — Qloo adapter boundary

**Decision:** Isolate Qloo API access behind dedicated services/adapters.

**Reason:** Prevent Qloo-specific HTTP details from leaking into agent logic and simplify testing.

### ADR-003 — Hosted AI

**Decision:** Use hosted LLM and speech services.

**Reason:** The target deployment environment has limited memory and CPU.

### ADR-004 — PostgreSQL

**Decision:** Use PostgreSQL for durable relational application state.

**Reason:** The application needs users, sessions, conversations, results, saved discoveries, and relationships between them.

### ADR-005 — Voice as an input channel

**Decision:** Treat speech-to-text as input preprocessing rather than a separate agent.

**Reason:** Text and voice should converge on the same discovery pipeline.

---

## 25. Open Architecture Decisions

The following must be finalized in later documentation:

- Exact Qloo endpoints and request schemas.
- Qloo entity-resolution strategy.
- Exact LLM/provider and model.
- Structured output format for agent decisions.
- Authentication provider.
- Speech-to-text provider.
- PostgreSQL schema.
- API endpoint definitions.
- Frontend design system.
- Result card schemas by content type.
- Search provider and search policy.
- Caching strategy.
- Rate limiting.
- Production observability.
- Deployment provider.
- Exact agent execution limits.

These decisions should be documented before their corresponding implementation begins.

---

## 26. Next Documentation Dependencies

The recommended documentation sequence is:

1. Product vision and problem definition.
2. Architecture decisions.
3. Qloo integration specification.
4. Agent state and tool schemas.
5. Database schema.
6. Backend API contract.
7. Frontend information architecture.
8. Discovery mode specifications.
9. Design system.
10. Deployment.
11. Testing.
12. Hackathon compliance checklist.

Architecture should be updated whenever one of these documents introduces a significant system-level decision.
