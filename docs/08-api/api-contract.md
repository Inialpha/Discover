# API Contract

## 1. Purpose

This document defines the public HTTP contract between the Discover frontend and backend.

The API is intentionally product-oriented. Clients interact with discovery sessions, messages, results, history, and saved discoveries. They do not interact directly with Qloo, the LLM provider, the database, or internal agent tools.

## 2. API Principles

1. Use JSON for normal request and response bodies.
2. Version the public API under /api/v1.
3. Keep provider-specific structures out of public contracts.
4. Use stable product-level identifiers.
5. Return explicit status fields for agentic outcomes.
6. Treat the backend as the source of truth for discovery state.
7. Make errors machine-readable and user-presentable.
8. Keep authentication independent from discovery logic.
9. Never expose Qloo credentials or raw provider requests.
10. Allow the API to evolve without coupling the frontend to database models.

## 3. Base URL

Production:

    https://<discover-api-host>/api/v1

Development:

    http://localhost:<port>/api/v1

The frontend receives the API base URL through environment configuration.

## 4. Authentication

The API should support authenticated requests when account functionality is enabled.

The authentication mechanism is intentionally separate from this document because the final identity provider may be selected during implementation.

Every authenticated request must allow the backend to determine:

    user_id

The client must not send an arbitrary user_id as proof of ownership.

Anonymous discovery may be supported for the MVP.

Anonymous sessions must use server-generated session identifiers and must not expose another user's session data.

## 5. Common Headers

Requests:

    Content-Type: application/json

Authenticated requests may additionally include the authentication mechanism selected by the application.

The frontend may send a client request ID for debugging/idempotency:

    X-Request-ID: <client-generated-id>

The backend should generate a correlation ID when one is not supplied.

## 6. Common Response Metadata

Responses may include:

    request_id
    timestamp

Example:

    {
      "request_id": "uuid",
      "timestamp": "2026-10-01T12:00:00Z"
    }

The frontend should not depend on timestamp formatting beyond standard ISO-8601 parsing.

## 7. Discovery Modes

The public API recognizes:

    personal
    gift
    community
    business

The backend may infer a mode from the initial message when mode is omitted.

## 8. POST /api/v1/discovery

Creates a new discovery session.

### Request

    {
      "mode": "personal",
      "message": "Find me a movie based on my taste in music.",
      "input_type": "text",
      "preferences": {}
    }

Fields:

| Field | Type | Required | Notes |
|---|---|---:|---|
| mode | string | No | personal, gift, community, business |
| message | string | Yes | Initial discovery request |
| input_type | string | No | text or voice_transcript |
| preferences | object | No | Explicit request-level preferences |

The message must be non-empty and bounded by a server-defined maximum length.

### Response

    {
      "session": {
        "id": "uuid",
        "mode": "personal",
        "status": "active",
        "title": null
      },
      "state": {
        "version": 1,
        "summary": {},
        "missing_information": []
      },
      "response": {
        "type": "question",
        "message": "What kind of mood are you looking for?"
      },
      "results": []
    }

The response type may be:

    question
    results
    message
    error

The API should return a question when the agent requires materially useful information before discovery.

## 9. POST /api/v1/discovery/{session_id}/message

Adds a message to an existing discovery session.

### Request

    {
      "message": "Something intelligent but not too dark.",
      "input_type": "text",
      "state_version": 2
    }

Fields:

| Field | Type | Required | Notes |
|---|---|---:|---|
| message | string | Yes | User message |
| input_type | string | No | text or voice_transcript |
| state_version | integer | No | Last known state version |

The state version allows the backend to detect stale concurrent clients.

### Response

The response uses the same discovery response contract as session creation.

Example question:

    {
      "session": {},
      "state": {
        "version": 3,
        "summary": {
          "mood": "intelligent but not too dark"
        },
        "missing_information": [
          {
            "key": "target_type",
            "importance": "high"
          }
        ]
      },
      "response": {
        "type": "question",
        "message": "Do you want a movie, series, or either?"
      },
      "results": []
    }

Example results:

    {
      "session": {
        "id": "uuid",
        "mode": "personal",
        "status": "completed"
      },
      "state": {
        "version": 4,
        "summary": {
          "target": "movie",
          "mood": "intelligent but not too dark"
        },
        "missing_information": []
      },
      "response": {
        "type": "results",
        "message": "Here are some discoveries that fit what you described."
      },
      "results": [
        {
          "id": "uuid",
          "name": "Example",
          "type": "movie",
          "image_url": "https://example.com/image.jpg",
          "description": "Example description.",
          "explanation": {
            "summary": "Connects your preference for intelligent stories with a lighter tone."
          }
        }
      ]
    }

## 10. GET /api/v1/discovery/{session_id}

Returns the current durable representation of a discovery session.

Response:

    {
      "session": {
        "id": "uuid",
        "mode": "personal",
        "status": "active",
        "title": "Movie discovery"
      },
      "state": {
        "version": 4,
        "summary": {},
        "missing_information": []
      },
      "messages": [],
      "results": []
    }

The backend may paginate older messages in a future version.

The initial implementation can return a bounded recent message history.

## 11. DELETE /api/v1/discovery/{session_id}

Deletes or archives a discovery session according to the application's retention policy.

Expected successful response:

    {
      "success": true
    }

The API should not physically delete data if the selected product retention model requires soft deletion.

## 12. GET /api/v1/history

Returns discovery sessions available to the authenticated user.

Query parameters:

    page
    limit
    status
    mode

Example:

    GET /api/v1/history?page=1&limit=20&status=completed

Response:

    {
      "items": [
        {
          "id": "uuid",
          "title": "Weekend movie",
          "mode": "personal",
          "status": "completed",
          "summary": "Movie recommendations based on your taste in thrillers.",
          "updated_at": "2026-10-01T12:00:00Z"
        }
      ],
      "page": 1,
      "limit": 20,
      "has_more": false
    }

## 13. GET /api/v1/history/{id}

Returns a previously completed or retained discovery session.

The response should use the same session representation as GET discovery.

Ownership must be checked on the backend.

## 14. POST /api/v1/saved

Saves a discovery result.

### Request

    {
      "result_id": "uuid",
      "title": "Gift idea",
      "note": "Possible birthday gift"
    }

A result snapshot may be generated by the backend rather than trusted from the client.

The client should not be able to modify the provider entity ID or ownership relationship through arbitrary request fields.

### Response

    {
      "saved": {
        "id": "uuid",
        "result_id": "uuid",
        "title": "Gift idea",
        "note": "Possible birthday gift",
        "created_at": "2026-10-01T12:00:00Z"
      }
    }

## 15. GET /api/v1/saved

Returns the authenticated user's saved discoveries.

Query parameters may eventually include:

    page
    limit

Response:

    {
      "items": [
        {
          "id": "uuid",
          "title": "Gift idea",
          "note": "Possible birthday gift",
          "result": {
            "name": "Example",
            "type": "product",
            "image_url": "https://example.com/image.jpg",
            "explanation": {
              "summary": "Fits the recipient's interest in ..."
            }
          },
          "created_at": "2026-10-01T12:00:00Z"
        }
      ],
      "page": 1,
      "limit": 20,
      "has_more": false
    }

## 16. DELETE /api/v1/saved/{id}

Removes a saved discovery.

Response:

    {
      "success": true
    }

Deleting a saved discovery must not delete the underlying discovery session or provider result.

## 17. Discovery Response Contract

The discovery endpoints share a common response envelope:

    {
      "session": {},
      "state": {},
      "response": {},
      "results": [],
      "request_id": "uuid"
    }

The response is designed to support the agentic interaction without exposing internal agent implementation.

### Response object

    {
      "type": "question",
      "message": "What kind of experience are you looking for?",
      "actions": []
    }

Supported response types:

    question
    results
    message
    error

Optional actions can provide structured frontend shortcuts:

    {
      "type": "quick_reply",
      "label": "Adventurous",
      "value": "I want something adventurous."
    }

The backend may omit actions when natural-language input is preferable.

## 18. State Summary Contract

The frontend should receive a safe summary rather than the entire internal DiscoveryState.

Example:

    {
      "version": 5,
      "summary": {
        "looking_for": "weekend experience",
        "interests": ["live music", "food"],
        "location": "Calabar",
        "budget": "moderate"
      },
      "missing_information": [
        {
          "key": "date",
          "label": "Date",
          "importance": "medium"
        }
      ]
    }

The internal state may contain fields that never leave the backend.

## 19. Missing Information Contract

Missing information should be represented semantically.

Example:

    {
      "key": "budget",
      "label": "Budget",
      "importance": "medium",
      "reason": "Could materially change the available recommendations."
    }

The frontend should not decide which missing information matters. It only renders the agent's selected question or optional context.

## 20. Result Contract

The normalized public result should be provider-independent.

Example:

    {
      "id": "uuid",
      "name": "Example",
      "type": "movie",
      "description": "Short description.",
      "image_url": "https://example.com/image.jpg",
      "url": "https://example.com/item",
      "location": null,
      "metadata": {},
      "explanation": {
        "summary": "Why this fits your request.",
        "signals": [
          "psychological thrillers",
          "morally complex characters"
        ]
      }
    }

The frontend should not receive raw Qloo response structures.

## 21. Explanation Contract

Explanation is optional because provider responses may not always contain enough data for a strong explanation.

Example:

    {
      "summary": "This connects your interest in atmospheric thrillers with your preference for complex characters.",
      "signals": [
        {
          "label": "Atmospheric thrillers",
          "source": "user_preference"
        },
        {
          "label": "Complex characters",
          "source": "user_preference"
        }
      ]
    }

The frontend must not present unsupported causal claims. Explanations should reflect available evidence from the discovery pipeline.

## 22. Pagination

List endpoints should use:

    page
    limit

The backend should enforce a maximum limit.

The initial API can use simple page-based pagination. Cursor pagination can be introduced later if history or saved data becomes large.

Discovery results themselves are not initially paginated because the agent controls a bounded result count.

## 23. Idempotency

Discovery messages can trigger expensive external operations.

The backend should support an idempotency mechanism for requests that create or advance state.

Potential header:

    Idempotency-Key: <unique-client-key>

The server may store the result of an idempotent operation for a bounded period.

This prevents accidental duplicate submissions caused by mobile retries or double taps.

## 24. Concurrency

A client should include its latest known state version when advancing a session when practical.

If the state is stale, return:

    HTTP 409 Conflict

Example:

    {
      "error": {
        "code": "STATE_CONFLICT",
        "message": "This discovery session changed before your request was processed.",
        "request_id": "uuid"
      }
    }

The frontend should reload the current session rather than overwrite it.

## 25. Error Contract

All expected API errors should use a common structure:

    {
      "error": {
        "code": "ERROR_CODE",
        "message": "User-safe explanation.",
        "details": {},
        "request_id": "uuid"
      }
    }

The message must be safe for display to the user.

Internal exception messages, provider payloads, credentials, stack traces, and hidden prompts must not be returned.

## 26. HTTP Status Mapping

Initial mapping:

| Status | Meaning |
|---|---|
| 200 | Successful read/update |
| 201 | Resource created |
| 202 | Accepted asynchronous operation, if introduced |
| 204 | Successful deletion with no body |
| 400 | Invalid request |
| 401 | Authentication required/invalid |
| 403 | Authenticated but not authorized |
| 404 | Resource not found |
| 409 | State or idempotency conflict |
| 422 | Validation failure |
| 429 | Rate limit |
| 500 | Unexpected server failure |
| 502 | Upstream provider failure |
| 503 | Service temporarily unavailable |

The frontend should map these statuses to user-relevant states rather than exposing raw status codes.

## 27. Validation

The backend must validate:

- message length
- mode
- input_type
- UUID formats
- pagination limits
- state_version
- saved-discovery ownership
- supported fields

Unknown or dangerous fields should not be blindly passed to Qloo.

## 28. Security Boundary

The API is the trust boundary.

The frontend is untrusted input.

The backend is responsible for:

- authorization
- ownership checks
- input validation
- Qloo credentials
- LLM credentials
- database access
- rate limiting
- prompt-injection-resistant tool handling
- provider response validation

The frontend must never be treated as a trusted source of ownership or authorization.

## 29. Voice API Boundary

Voice should remain a separate input transformation boundary.

Initial flow:

    Browser microphone
        ↓
    speech-to-text service
        ↓
    transcript
        ↓
    POST /discovery or /message

The discovery API should receive text rather than raw audio unless a future backend transcription endpoint is deliberately introduced.

The initial MVP therefore does not require a public audio-upload API.

## 30. Health Endpoints

### GET /health

Purpose: process health.

Example:

    {
      "status": "ok"
    }

This should remain lightweight and should not depend on external providers.

### GET /ready

Purpose: deployment readiness.

The readiness check may verify required infrastructure such as database connectivity.

External Qloo availability should not necessarily make the entire application fail readiness.

## 31. API Documentation

FastAPI should generate OpenAPI documentation from the actual request and response schemas.

The implementation should keep:

- route definitions
- Pydantic request schemas
- Pydantic response schemas
- validation rules

close enough that the generated OpenAPI remains authoritative.

This document is the architectural contract; generated OpenAPI becomes the implementation-level reference.

## 32. API Versioning

Initial version:

    /api/v1

Breaking changes require a new API version.

Backward-compatible additions may be made within v1.

The frontend should not depend on undocumented fields.

## 33. Timeout Behavior

The API should impose bounded timeouts.

The discovery endpoint may involve:

- LLM calls
- entity resolution
- Qloo discovery
- optional current-information search

The backend must not leave HTTP requests hanging indefinitely.

If the operation exceeds the supported request budget, return a safe timeout response and preserve the session state so the user can retry.

## 34. Agentic Execution Contract

The API should represent agent outcomes, not agent implementation.

Conceptually:

    user message
        ↓
    agent decision
        ↓
    zero or more internal tool calls
        ↓
    final agent outcome
        ↓
    API response

Possible outcomes:

    needs_user_input
    discovery_complete
    informational_message
    failed

These may be mapped into the simpler public response types:

    question
    results
    message
    error

## 35. Current Information

If a discovery requires current operational information, such as current opening hours or an event occurring at a particular time, the backend may use a current-information search tool.

The frontend does not need a separate current-search API.

Current-information evidence should be converted into the same product-level result format where appropriate.

## 36. Caching

The API should not expose cache behavior to the frontend.

Backend caching may be used for:

- entity resolution
- tags
- location resolution
- safe repeat queries

Cached data must not bypass authorization checks.

## 37. Rate Limits

The backend should eventually enforce application-level limits separately from upstream Qloo limits.

Potential dimensions:

- requests per minute per user
- discovery sessions per day
- expensive discovery executions
- voice transcription usage

The exact limits are deployment/product decisions and should be configurable.

## 38. API Implementation Structure

The backend route structure should remain:

    backend/app/api/
    ├── dependencies.py
    ├── routes/
    │   ├── discovery.py
    │   ├── sessions.py
    │   ├── history.py
    │   └── saved.py
    └── schemas/
        ├── discovery.py
        ├── history.py
        ├── saved.py
        └── common.py

Authentication schemas and routes may be added separately.

## 39. Testing Contract

Every public endpoint should have tests for:

- valid request
- invalid request
- authentication/authorization
- ownership
- expected response schema
- upstream failure
- timeout
- state conflict where relevant
- duplicate/idempotent request where relevant

Contract tests should ensure the frontend's expected response shape remains stable.

## 40. Implementation Order

API implementation should proceed in this order:

1. common response/error models
2. discovery request/response schemas
3. discovery create endpoint
4. discovery message endpoint
5. session retrieval
6. history
7. saved discoveries
8. deletion endpoints
9. health/readiness
10. authentication dependencies
11. rate limiting
12. idempotency
13. OpenAPI review
14. endpoint integration tests

## 41. Definition of Done

The API contract is ready for implementation when:

- all initial public endpoints are defined
- request and response shapes are explicit
- discovery outcomes are represented
- state versioning is defined
- errors have a common contract
- ownership rules are clear
- Qloo remains behind the backend
- voice remains an input boundary
- health/readiness semantics are defined
- pagination and idempotency behavior are defined
- generated OpenAPI can become the implementation reference
- endpoint tests can be written directly from this contract

## 42. Architectural Summary

The Discover API is the stable boundary between a simple frontend and a complex agentic backend.

The browser sends natural-language intent. The backend owns reasoning, state, Qloo integration, persistence, authorization, and execution. The browser receives only product-level information needed to continue the discovery experience.

The core rule is:

> **The public API describes what Discover does, not how Discover does it.**
