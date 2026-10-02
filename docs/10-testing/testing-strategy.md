# Testing Strategy

> **Alignment:** This is a detail document. The canonical requirements, enums (modes, intents, statuses, result kinds), API surface, and SSE protocol are in [`REQUIREMENTS.md`](../../REQUIREMENTS.md). If anything here conflicts with it, `REQUIREMENTS.md` wins and this document must be corrected. Decisions: [`docs/01-decisions/decision-records.md`](../01-decisions/decision-records.md). Profiles and test layers: REQUIREMENTS §11 (ADR-009).

## 1. Purpose

This document defines the testing strategy for Discover before and during implementation.

Discover is an agentic system, so testing must cover both deterministic software behavior and the boundaries where an LLM makes decisions.

The goal is not to prove that an LLM always produces one exact answer. The goal is to verify that:

- application contracts remain correct
- tools execute safely
- Qloo integration is reliable
- agent decisions stay within defined boundaries
- user state is preserved correctly
- recommendations are grounded in the intended inputs
- failures are handled predictably
- the complete discovery experience works end-to-end

## 2. Testing Principles

Testing should follow these principles:

1. Prefer deterministic tests wherever deterministic behavior is possible.
2. Test external providers through adapters rather than coupling the whole application to them.
3. Use mocks/fakes for most unit tests.
4. Reserve live-provider tests for explicit integration or smoke tests.
5. Test agent behavior through structured decisions and invariants rather than exact prose.
6. Test security boundaries explicitly.
7. Keep the test suite lightweight enough to run in CI.
8. Test the five discovery modes.
9. Test failure paths, not only successful paths.
10. Every important bug should result in a regression test.

## 3. Testing Pyramid

The initial test distribution should favor fast tests:

    End-to-End Tests
          ▲
          │
    Integration Tests
          ▲
          │
    Unit Tests
          ▲

Most tests should be unit tests.

Integration tests verify boundaries between internal components and external-provider adapters.

End-to-end tests verify the complete user journey.

## 4. Test Layers

Discover should have these testing layers:

| Layer | Purpose |
|---|---|
| Unit | Verify isolated functions/modules |
| Integration | Verify internal component boundaries and provider adapters |
| API | Verify HTTP contracts |
| Database | Verify persistence behavior |
| Agent | Verify orchestration and decision constraints |
| Frontend | Verify UI behavior and API integration |
| End-to-End | Verify complete discovery journeys |
| Smoke | Verify deployed application health and critical flows |

## 5. Test Directory

Recommended structure:

    tests/
    ├── unit/
    │   ├── agent/
    │   ├── discovery/
    │   ├── qloo/
    │   ├── llm/
    │   ├── search/
    │   ├── auth/
    │   └── common/
    ├── integration/
    │   ├── qloo/
    │   ├── llm/
    │   ├── database/
    │   └── discovery/
    ├── api/
    ├── e2e/
    ├── fixtures/
    └── conftest.py

Frontend tests should live with the frontend according to its selected framework conventions.

## 6. Unit Testing

Unit tests should cover deterministic business logic without network calls.

Important unit-test targets:

- DiscoveryState updates
- missing-information evaluation
- question selection
- confidence thresholds
- readiness evaluation
- target-type selection
- signal/filter construction
- Qloo request normalization
- Qloo response normalization
- explanation normalization
- result evaluation
- refinement limits
- retry decisions
- error mapping
- pagination
- validation
- authorization decisions
- configuration validation

## 7. DiscoveryState Tests

The state model is central to Discover.

Tests should verify:

- valid state creation
- partial state creation
- preference updates
- constraint updates
- location updates
- audience updates
- resolved entity insertion
- duplicate entity handling
- asked-question tracking
- refinement state updates
- execution counters
- serialization/deserialization
- state-version handling

Invalid state should fail predictably.

## 8. Missing Information Tests

The system should not ask questions merely because information is absent.

Tests should verify that the agent distinguishes between:

- information that is required
- information that would improve results
- information that is unnecessary

Example:

A user asking for a movie recommendation may not need to provide a budget.

A business-market request may require a target market before Qloo discovery can be meaningful.

The exact policy should be represented in deterministic readiness logic where possible.

## 9. Question Selection Tests

Question selection should be tested using structured inputs.

Test cases should include:

- no missing information
- one critical missing field
- several missing fields
- low-value missing fields
- already-asked questions
- contradictory information
- ambiguous user intent

The system should avoid repeatedly asking the same question.

## 10. Agent Decision Tests

The LLM may produce one of the supported decisions:

    ask_user
    call_tool
    complete

Tests should verify that malformed or unsupported decisions are rejected.

The application must validate structured LLM output before executing it.

The agent must not be able to invoke arbitrary functions outside the registered tool set.

## 11. Agent Loop Tests

The orchestrator must be tested for:

- successful completion
- user follow-up
- tool execution
- multiple tool calls
- tool failure
- LLM failure
- invalid LLM output
- repeated decisions
- maximum-step termination
- maximum-refinement termination
- cancellation/timeouts
- empty provider results

Example invariant:

    agent_steps <= MAX_AGENT_STEPS

The invariant must hold even when the LLM repeatedly requests tools.

## 12. Loop Prevention Tests

Explicit regression tests should cover loops such as:

    LLM → Qloo → LLM → Qloo → ...

without meaningful state change.

The system should terminate when:

- maximum steps are reached
- maximum refinements are reached
- repeated tool execution provides no useful progress
- the request becomes invalid
- an execution budget is exhausted

## 13. Tool Registry Tests

The tool registry must verify:

- known tools can be resolved
- unknown tools are rejected
- tool schemas are available
- required arguments are validated
- tool results have the expected internal shape

The registry is a security boundary.

## 14. Tool Executor Tests

Test:

- successful execution
- invalid arguments
- timeout
- provider error
- unexpected exception
- retry behavior
- result normalization
- correlation/request IDs

A failed tool must produce a controlled application error rather than crash the entire process.

## 15. Entity Resolution Tests

The Qloo entity-resolution adapter should be tested independently.

Test cases:

- exact entity match
- strong match
- ambiguous match
- weak match
- no match
- multiple candidate matches
- malformed Qloo response
- Qloo timeout
- Qloo rate limit
- Qloo server error

Confidence thresholds defined by the discovery architecture must be enforced consistently.

## 16. Qloo Request Tests

Tests should verify that the internal request model is converted into the correct Qloo request.

Cover:

- target type
- entity interests
- tag interests
- signal weights
- location
- price filters
- rating filters
- other supported constraints
- result count
- sorting
- explainability
- cross-domain interests

The application should never send unsupported parameters simply because an LLM generated them.

## 17. Qloo Response Tests

Use representative fixture responses.

Test:

- normal result
- empty result
- partial result
- missing optional fields
- unexpected fields
- malformed result
- explainability metadata
- location metadata
- provider errors

The adapter should convert provider-specific data into Discover's provider-independent result model.

## 18. Qloo Integration Tests

A small number of integration tests may call the real Qloo API.

These tests should be:

- explicitly marked
- excluded from ordinary unit CI when credentials are unavailable
- run in a controlled environment
- bounded in request count

They should verify that the adapter still matches the live Qloo API.

The normal CI suite must not depend on Qloo availability.

## 19. LLM Adapter Tests

The LLM adapter should be tested separately from the agent.

Test:

- request construction
- model configuration
- structured output parsing
- invalid JSON/structured output
- missing fields
- unsupported decisions
- timeout
- provider error
- rate limit
- retry behavior

Do not make exact natural-language response matching a core test strategy.

## 20. LLM Fixture Strategy

Agent tests should use deterministic LLM fixtures.

A fixture can represent decisions such as:

    ask_user:
      question: "What kind of films does your friend usually enjoy?"

    call_tool:
      tool: "resolve_entity"
      arguments: ...

    complete:
      answer: ...

This makes the orchestration testable without requiring a live model.

## 21. Prompt Tests

Prompt changes can alter agent behavior.

The project should therefore maintain representative scenarios covering:

- personal discovery
- gift discovery
- community discovery
- business discovery
- ambiguous requests
- requests requiring follow-up
- requests requiring entity resolution
- requests requiring current information

Prompt tests should focus on behavioral invariants rather than exact wording.

## 22. Prompt Injection Tests

User input must be treated as untrusted.

Tests should include requests that attempt to:

- reveal system instructions
- expose API keys
- invoke unregistered tools
- bypass safety or validation constraints
- modify internal state directly
- manipulate tool arguments
- request raw provider credentials

The agent should remain within its defined tool and data boundaries.

## 23. Discovery Service Tests

The discovery service should be tested for:

- personal discovery
- gift discovery
- community discovery
- business discovery
- incomplete requests
- ready requests
- Qloo no-result cases
- refinement
- result normalization
- persistence

The service should not contain provider-specific HTTP logic.

## 24. Recommendation Evaluation Tests

The evaluator should verify that results satisfy the discovery request's hard constraints.

Examples:

- requested location
- price range
- target category
- explicit exclusions
- requested result count

Soft preference matching should be evaluated separately from hard constraints.

The evaluator must not silently convert a hard user constraint into a soft preference.

## 25. Explainability Tests

Explainability is a product requirement.

Tests should verify that a recommendation can be associated with useful supporting signals when Qloo provides them.

The system should distinguish between:

- provider-backed explanation
- application-generated explanation
- unavailable explanation

The UI must not imply that a generated explanation came directly from Qloo when it did not.

## 26. Current Information Boundary Tests

Current information and cultural intelligence are different responsibilities.

Tests should verify that:

- current operational facts use the current-information search boundary
- Qloo is used for cultural intelligence
- provider results are not mixed without attribution
- unavailable current information does not silently become a fabricated fact

## 27. Database Tests

Database integration tests should use an isolated test database.

Test:

- user creation
- session creation
- message persistence
- state persistence
- discovery query persistence
- normalized result persistence
- saved discovery persistence
- history retrieval
- deletion
- pagination
- uniqueness constraints
- foreign keys
- transaction rollback

## 28. Transaction Tests

Test failure during multi-step operations.

For example:

    create discovery
        ↓
    persist state
        ↓
    persist message
        ↓
    persist results

If a transaction is intended to be atomic, a failure should not leave a partially committed state.

Where operations are intentionally separate, that behavior must be documented and tested.

## 29. Concurrency Tests

The API supports stateful sessions.

Tests should cover two messages submitted against the same session concurrently.

The application must prevent silent lost updates.

The state-version mechanism described in the API architecture should be exercised.

## 30. API Contract Tests

Every public endpoint should have tests for:

- successful response
- validation errors
- authentication requirements
- authorization failures
- not-found behavior
- conflict behavior
- provider failure
- internal failure
- response schema

Endpoints include:

    The full endpoint list is REQUIREMENTS §7.3. Every endpoint needs contract,
    access-control (ACC-008), and error-path tests. SSE endpoints additionally need
    event-order, heartbeat, and resume (Last-Event-ID) tests.

## 31. API Security Tests

Test:

- missing authentication
- invalid authentication
- unauthorized session access
- unauthorized history access
- unauthorized saved-item access
- malformed JSON
- oversized payloads
- invalid IDs
- invalid pagination
- CORS behavior
- secret leakage through error responses

## 32. Authentication Tests

Authentication implementation may evolve, but tests must verify the application-level boundary.

At minimum:

- unauthenticated access to public endpoints
- authenticated access to protected endpoints
- ownership enforcement
- expired/invalid credentials
- session isolation

Authentication tests should not depend on a real external identity provider unless running a dedicated integration suite.

## 33. Frontend Testing

The frontend should test:

- mode selection
- discovery creation
- message submission
- follow-up question rendering
- user answer submission
- loading/agent activity states
- recommendation cards
- explanations
- refinement
- saved discovery
- history
- errors
- empty results
- voice input
- responsive layouts
- keyboard accessibility

## 34. Frontend API Mocking

Frontend tests should normally mock the backend API.

Scenarios should include:

    discovery complete
    needs user input
    provider failure
    validation error
    authentication failure
    empty results
    network failure

This keeps frontend tests deterministic.

## 35. End-to-End Tests

End-to-end tests should verify complete user journeys.

Initial required journeys:

### Personal

    Open Discover
      ↓
    Select Discover for Me
      ↓
    Describe taste
      ↓
    Agent asks useful follow-up if necessary
      ↓
    Agent resolves entities/tags
      ↓
    Qloo discovery
      ↓
    Results displayed
      ↓
    User refines results

### Gift

    Select gift discovery
      ↓
    Describe recipient
      ↓
    Agent asks about recipient's interests
      ↓
    Entity/tag resolution
      ↓
    Qloo discovery
      ↓
    Gift-oriented results
      ↓
    Explanation

### Community

    Select community discovery
      ↓
    Describe audience
      ↓
    Clarify relevant context
      ↓
    Qloo discovery
      ↓
    Culturally relevant results

### Business

    Select business discovery
      ↓
    Describe business/product
      ↓
    Define target market
      ↓
    Agent resolves market context
      ↓
    Qloo discovery
      ↓
    Market-oriented results

## 36. End-to-End Test Environment

E2E tests should use a controlled environment.

External services should generally be mocked or replaced by stable test doubles.

A separate live smoke test can verify:

    Frontend
       ↓
    Backend
       ↓
    Qloo
       ↓
    LLM
       ↓
    Database

This prevents provider instability from making the complete E2E suite unreliable.

## 37. Deployment Smoke Tests

After deployment, automatically or manually verify:

- /health
- /ready
- frontend loads
- API connection works
- authentication works where enabled
- a basic discovery can start
- a Qloo-backed discovery can complete
- results render
- refinement works
- save/history behavior works

## 38. Performance Tests

The initial MVP does not require large-scale load testing.

It should nevertheless test:

- normal discovery latency
- provider timeout behavior
- database query latency
- concurrent sessions
- memory behavior
- request-size limits

The goal is to identify obvious resource problems before public use.

## 39. Memory Testing

Because the backend targets small instances, memory behavior is important.

Test scenarios should include:

- repeated discovery requests
- long conversations
- multiple simultaneous sessions
- repeated Qloo calls
- failed requests
- large-but-valid user messages

Look for:

- unbounded state growth
- retained HTTP responses
- oversized logs
- cache growth
- unreleased database connections

## 40. Cost-Control Tests

Agentic applications can accidentally multiply external API usage.

Tests should verify:

- maximum agent steps
- maximum Qloo calls
- maximum refinements
- bounded retries
- no duplicate tool execution without reason
- no repeated entity resolution when the result is already known

A discovery request should have a predictable maximum execution budget.

## 41. Regression Testing

Every production bug should produce a regression test.

Regression tests should include:

- the triggering input
- expected state transition
- expected provider interaction where relevant
- expected user-visible behavior
- failure boundary

Do not fix recurring agent failures only through prompt changes if a deterministic application constraint can prevent them.

## 42. Test Data and Fixtures

Fixtures should represent realistic but synthetic data.

Do not place real user personal information in repository fixtures.

Fixture categories:

- entities
- tags
- locations
- Qloo responses
- LLM decisions
- provider errors
- users
- sessions
- discovery results

Fixtures should be small enough to keep tests fast.

## 43. Test Naming

Test names should describe behavior.

Prefer:

    test_agent_stops_after_max_steps

over:

    test_agent_8

Prefer:

    test_qloo_adapter_maps_price_filter

over:

    test_qloo_request

## 44. Test Markers

Recommended markers:

    unit
    integration
    api
    e2e
    live_qloo
    live_llm
    smoke

Ordinary CI should run fast deterministic tests.

Live provider tests should require explicit configuration.

## 45. CI Test Strategy

Pull requests should run:

    lint
    type checks where configured
    unit tests
    API tests
    database integration tests where practical
    frontend tests
    frontend build
    backend Docker build

Live Qloo/LLM tests should not be required for every pull request unless their credentials and cost are explicitly controlled.

## 46. Test Secrets

CI secrets must be stored in the CI platform's secret manager.

Never commit:

- Qloo API keys
- LLM API keys
- database passwords
- authentication secrets

Tests should fail clearly when a live-provider test is requested without its required credential.

## 47. Contract Drift Detection

External APIs can change.

The integration suite should periodically verify:

- Qloo request compatibility
- Qloo response normalization
- LLM structured-output compatibility

When an external contract changes, update the adapter and its fixtures together.

## 48. Testability Requirements for Implementation

Implementation should preserve testability.

Avoid:

- network calls directly inside domain logic
- global mutable state
- hidden singleton clients that cannot be replaced
- hard-coded provider configuration
- direct database calls from API route handlers
- LLM decisions that bypass validation

Prefer explicit dependency boundaries that can be replaced with fakes during tests.

## 49. Definition of Done

A feature is considered tested when:

- deterministic business logic has unit tests
- API behavior has contract tests
- persistence behavior has database tests where applicable
- provider adapters have mocked integration tests
- failure paths are covered
- security boundaries are tested
- relevant frontend behavior is tested
- at least one end-to-end journey covers the feature
- important bugs have regression tests
- tests run successfully in CI

## 50. Initial Implementation Testing Order

Testing should be implemented alongside the system in this order:

1. configuration and common utilities
2. state models
3. discovery readiness logic
4. Qloo request/response models
5. Qloo adapter
6. LLM structured decision models
7. tool registry/executor
8. agent orchestrator
9. discovery service
10. database repositories
11. API routes
12. authentication
13. frontend components
14. complete discovery journeys
15. deployment smoke tests

## 51. Testing Summary

Discover should be tested as an engineered system, not as a chatbot.

The deterministic parts should have strong automated coverage.

The agentic parts should be tested through:

- structured decisions
- bounded execution
- controlled fixtures
- behavioral invariants
- representative scenarios
- provider integration tests
- complete user journeys

The central testing principle is:

> **Test what the system must guarantee, not what the language model happens to say.**


---

# Profile mechanics (REQUIREMENTS §11, ADR-009)

## P1. Selecting a profile
`DISCOVER_PROFILE=mock|record|replay|live`, with optional `QLOO_MODE`, `LLM_MODE`, `SEARCH_MODE`, `STT_MODE` overrides. `mock` requires no external keys.

## P2. Repository layout
~~~text
backend/
  app/integrations/
    qloo/      client.py  live.py  mock.py  record.py  replay.py  normalize.py
    llm/       client.py  live.py  scripted.py  record.py  replay.py
    search/    client.py  live.py  mock.py  record.py  replay.py
fixtures/
  scenarios/   self.yaml  someone_else_gift.yaml  group.yaml  community.yaml
               business.yaml  compare.yaml  trend.yaml  ambiguous_entity.yaml
               thin_results.yaml  provider_failure.yaml  timeout.yaml
  recorded/    qloo/  llm/  search/        # created by `record`, sanitized
~~~

## P3. Scenario file shape (mock)
~~~yaml
id: someone_else_gift
match: { keywords: [gift, birthday], mode: someone_else }
script:
  - event: phase.changed   data: { phase: understanding }
  - event: tool.started    data: { tool: resolve_entities, provider: qloo }
  - event: tool.completed  data: { tool: resolve_entities, summary: "Matched 2 of 2" }
  - event: result.set      data: { results_ref: gift_results }
results:
  gift_results: [ ... normalized DiscoveryResult objects, marked synthetic ... ]
~~~
All mock output sets `synthetic: true` internally, which surfaces as the demo banner, export watermark, and `/meta.synthetic_data` (TST-003).

## P4. Recording and sanitizing
`record` writes request summaries and responses to `fixtures/recorded/`, stripping API keys, tokens, and any personal identifiers, and adds `captured_at` and API-version metadata (TST-021). Fixtures are reviewed before commit.

## P5. First session after keys arrive
Run the spike checklist (TST-020), commit fixtures, implement/adjust `normalize.py` until replay contract tests pass, then update `docs/07-qloo` and add an ADR for any deviation.

## P6. Quality evals
Maintain ≥ 15 golden prompts (`fixtures/evals/golden.yaml`) with behavioral assertions: asks only when material; labels evidence vs interpretation; honors budget and exclusions; never invents prices; states limitations when thin.

## P7. Streaming tests
- Event order and terminal-event uniqueness (API-011).
- Resume at every event index (API-012).
- Heartbeat cadence; client reconnect.
- Orphaned-run recovery on restart (BKD-005).
- Cancel during tool execution.
