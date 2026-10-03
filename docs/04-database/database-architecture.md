# Database Architecture

> **Alignment:** This is a detail document. The canonical requirements, enums (modes, intents, statuses, result kinds), API surface, and SSE protocol are in [`REQUIREMENTS.md`](../../REQUIREMENTS.md). If anything here conflicts with it, `REQUIREMENTS.md` wins and this document must be corrected. Decisions: [`docs/01-decisions/decision-records.md`](../01-decisions/decision-records.md). Entity list and rules: REQUIREMENTS §8. New tables vs. earlier drafts are listed in the *Alignment addendum* at the end of this file.

## 1. Purpose

This document defines the PostgreSQL persistence model for Discover.

The database must support:

- user accounts and authentication state
- discovery sessions
- conversation messages
- structured discovery state
- normalized discovery results
- saved discoveries
- discovery history
- lightweight user preferences
- audit and operational metadata needed to operate the application

The database is a persistence layer, not the agent's reasoning engine. The agent may maintain transient execution state during a request, but durable state must have a clear reason to exist in PostgreSQL.

## 2. Database Principles

Discover follows these database principles:

1. Persist product state, not every intermediate thought.
2. Minimize personal data.
3. Keep Qloo-specific HTTP structures out of product-facing tables where possible.
4. Use relational structure for entities that require querying and relationships.
5. Use JSONB for evolving structured discovery state and provider metadata.
6. Never make the database depend on a particular LLM provider.
7. Avoid storing sensitive information that is not required for discovery.
8. Use UTC timestamps for persisted time values.
9. Use application-generated UUIDs for public identifiers.
10. Design indexes around actual product queries rather than speculative optimization.

## 3. Technology

Initial database:

- PostgreSQL
- JSONB for flexible discovery-state structures
- UUID primary keys
- application-managed timestamps
- foreign keys for durable relationships
- transactions for multi-record state changes

The backend should use a small PostgreSQL driver layer rather than introducing a heavyweight ORM solely for convenience.

## 4. Core Entities

The initial schema contains these logical entities:

~~~text
User
 ├── UserPreference
 ├── DiscoverySession
 │    ├── DiscoveryMessage
 │    ├── DiscoveryState
 │    └── DiscoveryResult
 ├── SavedDiscovery
 └── DiscoveryHistory metadata

DiscoverySession
 └── DiscoveryResult

SavedDiscovery
 └── references a discovery result/session snapshot
~~~

The exact physical implementation may combine small metadata tables when doing so reduces unnecessary joins, but the logical boundaries remain explicit.

## 5. Users

### Table: users

Purpose: identify an application user and store only account-level information required by Discover.

Suggested columns:

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| email | TEXT | Unique when available |
| display_name | TEXT | Optional |
| auth_provider | TEXT | Provider identifier |
| auth_subject | TEXT | Provider-specific stable subject |
| created_at | TIMESTAMPTZ | Required |
| updated_at | TIMESTAMPTZ | Required |
| last_seen_at | TIMESTAMPTZ | Optional |

Constraints:

- unique (auth_provider, auth_subject)
- unique email where the application guarantees normalized email uniqueness
- do not store provider access tokens in this table unless a future feature explicitly requires them
- do not store passwords when authentication is delegated to an external identity provider

The application should normalize email values before uniqueness checks when email-based identity is supported.

## 6. User Preferences

### Table: user_preferences

Purpose: store explicit, durable preferences that improve future discovery.

Suggested columns:

| Column | Type | Notes |
|---|---|---|
| user_id | UUID | Primary key and FK |
| preferences | JSONB | Structured preference data |
| created_at | TIMESTAMPTZ | Required |
| updated_at | TIMESTAMPTZ | Required |

Examples of appropriate preference data:

~~~json
{
  "default_result_count": 10,
  "preferred_domains": ["movie", "music", "place"],
  "default_location": null,
  "response_style": "concise"
}
~~~

Preferences should represent explicit user choices or stable product settings. They should not silently become a profile containing inferred sensitive characteristics.

## 7. Discovery Sessions

### Table: discovery_sessions

Purpose: represent a user's discovery workspace and its lifecycle.

Suggested columns:

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| user_id | UUID | Nullable for anonymous MVP sessions if supported |
| mode | TEXT | self, someone_else, group, community, business (REQUIREMENTS §4.1) |
| title | TEXT | Optional generated/user-defined title |
| status | TEXT | active, completed, archived, deleted |
| created_at | TIMESTAMPTZ | Required |
| updated_at | TIMESTAMPTZ | Required |
| completed_at | TIMESTAMPTZ | Optional |

Constraints:

- foreign key to users when user_id is present
- mode must be one of the supported discovery modes
- status must use a controlled application vocabulary

The session is the durable anchor for the conversation and discovery lifecycle.

## 8. Discovery Messages

### Table: discovery_messages

Purpose: store user-facing conversation history when persistence is enabled.

Suggested columns:

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| session_id | UUID | FK |
| role | TEXT | user, assistant, system |
| content | TEXT | Message content |
| input_type | TEXT | text, voice_transcript, system |
| sequence_number | INTEGER | Ordered within session |
| created_at | TIMESTAMPTZ | Required |

Indexes:

- (session_id, sequence_number)
- (session_id, created_at)

System messages should be stored only when they have product/audit value. Internal prompts and hidden reasoning must never be persisted as conversation messages.

Voice audio itself should not be stored by default. If audio storage becomes a future feature, it requires a separate explicit retention and privacy design.

## 9. Structured Discovery State

### Table: discovery_states

Purpose: persist the latest durable representation of what the agent understands about a discovery request.

Suggested columns:

| Column | Type | Notes |
|---|---|---|
| session_id | UUID | Primary key and FK |
| state_version | INTEGER | Optimistic version |
| state | JSONB | Structured DiscoveryState |
| updated_at | TIMESTAMPTZ | Required |

The JSONB document corresponds to the application-level DiscoveryState defined in the discovery-mode architecture.

Conceptual structure:

~~~json
{
  "request": {},
  "subject": {},
  "preferences": {},
  "constraints": {},
  "location": {},
  "audience": {},
  "resolved_entities": [],
  "missing_information": [],
  "asked_questions": [],
  "refinement": {},
  "execution": {}
}
~~~

Not every transient execution field should be persisted. The application should define a durable subset.

### Versioning

state_version supports optimistic concurrency.

A state update should conceptually behave as:

~~~sql
UPDATE discovery_states
SET state = ..., state_version = state_version + 1
WHERE session_id = ...
  AND state_version = expected_version
~~~

If zero rows are updated, the application should treat this as a concurrent-state conflict rather than silently overwriting another request.

## 10. Discovery Results

### Table: discovery_results

Purpose: store normalized recommendations returned by the discovery pipeline.

Suggested columns:

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| session_id | UUID | FK |
| query_id | UUID | Groups results from one discovery execution |
| result_type | TEXT | Normalized domain/type |
| provider | TEXT | qloo or future provider |
| provider_entity_id | TEXT | External entity identifier |
| name | TEXT | Display name |
| description | TEXT | Optional |
| image_url | TEXT | Optional |
| url | TEXT | Optional |
| location | JSONB | Optional location metadata |
| score | NUMERIC | Optional normalized score |
| explanation | JSONB | Explainability data |
| metadata | JSONB | Provider-independent metadata |
| position | INTEGER | Display ordering |
| created_at | TIMESTAMPTZ | Required |

The table should contain normalized product-facing data, not an unbounded copy of the complete Qloo response.

provider_entity_id should be treated as an external identifier and should not be assumed to be globally unique across providers.

Recommended index:

- (session_id, query_id, position)

Optional index:

- (provider, provider_entity_id)

## 11. Discovery Query Groups

A discovery request may produce several Qloo calls because of refinement, cross-domain exploration, or result improvement.

### Table: discovery_queries

Suggested columns:

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| session_id | UUID | FK |
| attempt_number | INTEGER | Ordered execution attempt |
| query_type | TEXT | discovery, refinement |
| target_type | TEXT | Qloo target type |
| request_summary | JSONB | Internal normalized request |
| result_count | INTEGER | Number of normalized results |
| created_at | TIMESTAMPTZ | Required |

This table gives the application a durable boundary around one discovery execution without storing every HTTP detail.

Raw Qloo request/response payloads should not be persisted by default.

## 12. Saved Discoveries

### Table: saved_discoveries

Purpose: allow users to retain useful discoveries independently of the original active session.

Suggested columns:

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| user_id | UUID | FK |
| result_id | UUID | Optional FK |
| session_id | UUID | Optional FK |
| title | TEXT | User-visible label |
| note | TEXT | Optional user note |
| snapshot | JSONB | Stable saved result representation |
| created_at | TIMESTAMPTZ | Required |
| updated_at | TIMESTAMPTZ | Required |

A snapshot is important because an external provider's metadata can change or disappear.

The snapshot should contain only the information required to display the saved discovery. It should not contain the entire original provider response.

At least one source reference should be present:

- result_id, or
- session_id plus sufficient snapshot data

A future migration may make result_id mandatory if the product settles on that model.

## 13. Discovery History

The initial design does not require a separate full history table.

Completed sessions can serve as history:

~~~text
discovery_sessions
WHERE status = 'completed'
ORDER BY updated_at DESC
~~~

This avoids duplicating large conversation/result structures.

A dedicated history table should only be introduced if product requirements later require:

- immutable audit records
- aggressive session pruning
- separate retention policies
- analytics optimized independently from operational sessions

## 14. Relationships

Conceptual relationships:

~~~text
users 1 ──────── * discovery_sessions
users 1 ──────── 1 user_preferences

discovery_sessions 1 ──────── * discovery_messages
discovery_sessions 1 ──────── 1 discovery_states
discovery_sessions 1 ──────── * discovery_queries
discovery_queries 1 ──────── * discovery_results

users 1 ──────── * saved_discoveries
discovery_results 1 ──────── * saved_discoveries
~~~

Foreign keys should use explicit delete behavior.

Recommended default:

- deleting a user should remove or anonymize dependent product data according to the application's retention policy
- deleting a session should cascade to messages, state, queries, and results
- deleting a saved discovery should not delete the underlying session or result

## 15. Index Strategy

Initial indexes should support:

### User access

~~~text
users(auth_provider, auth_subject)
users(email)
~~~

### Sessions

~~~text
discovery_sessions(user_id, updated_at DESC)
discovery_sessions(user_id, status, updated_at DESC)
~~~

### Messages

~~~text
discovery_messages(session_id, sequence_number)
~~~

### Results

~~~text
discovery_results(session_id, query_id, position)
~~~

### Queries

~~~text
discovery_queries(session_id, attempt_number)
~~~

### Saved discoveries

~~~text
saved_discoveries(user_id, created_at DESC)
~~~

Do not add indexes for every JSONB field. JSONB indexes should be introduced only after a demonstrated query requirement.

## 16. Transactions

Transactions are required when multiple records must represent one logical state change.

Examples:

### Start discovery

Create:

1. discovery session
2. initial discovery state
3. first user message, if applicable

These should succeed or fail together.

### Complete discovery

A completion transaction may update:

1. discovery state
2. session status
3. discovery query
4. normalized results

The exact transaction boundary belongs to the service layer.

## 17. Concurrency

The backend may receive multiple requests for the same session.

The initial implementation should prevent lost updates through:

- state_version optimistic locking
- session-level application checks
- deterministic sequence numbers for messages

The application should not hold a database transaction open while waiting for an LLM or Qloo network request.

Preferred pattern:

~~~text
read durable state
→ perform external calls
→ validate response
→ short database transaction
→ persist state/result changes
~~~

## 18. Retention

Initial retention principles:

- active sessions remain available to the user
- completed sessions are retained as history according to product settings
- saved discoveries remain until the user removes them
- transient provider payloads are not retained by default
- voice audio is not retained by default
- operational logs must avoid storing message content unless explicitly required for debugging

A future retention setting may allow users to delete discovery history separately from saved discoveries.

## 19. Privacy

Discover should persist the minimum information necessary for the product.

Do not persist:

- passwords
- raw authentication credentials
- provider access tokens unless explicitly required
- hidden model reasoning
- unnecessary sensitive personal attributes
- complete raw Qloo responses by default
- raw voice recordings by default

If the user enters sensitive information into a discovery request, the application should not automatically promote that information into a durable user profile.

## 20. Qloo Data Boundary

The database should distinguish between:

**Product data**

- normalized entity name
- domain/type
- provider entity ID
- result position
- explanation
- display metadata

and:

**Provider transport data**

- HTTP request structure
- raw response payload
- provider-specific diagnostics
- transient query parameters

Provider transport data belongs in application memory unless there is a documented operational reason to retain a sanitized subset.

This keeps the product schema stable if Qloo changes response details.

## 21. LLM Data Boundary

The database must not depend on one LLM provider.

Persist structured application state such as:

~~~text
request
preferences
constraints
resolved entities
missing information
discovery mode
refinement status
~~~

Do not persist provider-specific prompt formats, hidden chain-of-thought, or provider-specific response objects as the canonical application state.

## 22. Migration Strategy

Schema changes should be version-controlled.

The project should use a migration system before production data exists.

Rules:

1. every schema change gets a migration
2. migrations must be deterministic
3. destructive migrations require explicit review
4. seed data must be separate from schema migrations
5. production migrations must be backward-compatible where practical
6. application code should not assume a migration succeeded unless startup/readiness checks confirm the required schema

The exact migration library can be selected during implementation.

## 23. Development and Test Databases

Development should use PostgreSQL rather than silently substituting SQLite because PostgreSQL-specific behavior matters for:

- UUIDs
- JSONB
- transactions
- indexing
- constraints
- concurrency behavior

Tests should use an isolated database/schema and deterministic fixtures.

No production credentials should be committed to the repository.

## 24. Backup and Recovery

Production PostgreSQL must use the hosting provider's supported backup mechanism or an explicitly configured backup process.

The application itself should not implement database backups.

Recovery requirements should eventually define:

- backup frequency
- retention period
- restoration procedure
- acceptable data loss
- restoration testing

These are deployment concerns rather than application schema concerns.

## 25. Analytics

Initial product analytics should not require copying the entire conversation into an analytics database.

Useful operational/product metrics can be derived from:

- session mode
- session lifecycle
- query count
- result count
- refinement count
- latency metadata
- errors

Analytics should avoid storing unnecessary message content or sensitive user data.

## 26. Suggested Initial Physical Schema

The first implementation should create these tables:

~~~text
users
user_preferences
discovery_sessions
discovery_messages
discovery_states
discovery_queries
discovery_results
saved_discoveries
~~~

No separate history table is required for the initial MVP.

## 27. Schema-to-API Mapping

~~~text
POST /api/v1/discovery
    → users
    → discovery_sessions
    → discovery_states
    → discovery_messages

POST /api/v1/discovery/{session_id}/message
    → discovery_messages
    → discovery_states
    → discovery_queries
    → discovery_results

GET /api/v1/discovery/sessions/{id}
    → discovery_sessions
    → discovery_states
    → discovery_messages
    → discovery_results

GET /api/v1/discovery/sessions            (history)
    → discovery_sessions

GET /api/v1/discovery/runs/{id}/events
    → discovery_runs
    → run_events

POST /api/v1/saved
    → saved_discoveries

GET /api/v1/saved
    → saved_discoveries

DELETE /api/v1/saved/{id}
    → saved_discoveries
~~~

## 28. Implementation Order

Database implementation should proceed in this order:

1. PostgreSQL connection/configuration
2. migration framework
3. users
4. user_preferences
5. discovery_sessions
6. discovery_messages
7. discovery_states
8. discovery_queries
9. discovery_results
10. saved_discoveries
11. foreign keys and indexes
12. repository layer
13. transaction boundaries
14. concurrency tests
15. retention/privacy behavior
16. integration tests

## 29. Definition of Done

The database architecture is ready for implementation when:

- all core entities have defined ownership
- relationships are explicit
- durable versus transient state is clear
- Qloo transport data is separated from product data
- LLM-provider-specific structures are excluded from canonical state
- indexes support the initial API
- concurrency behavior is defined
- deletion and retention behavior is defined
- migration strategy is established
- development and test environments use PostgreSQL
- repository boundaries can be implemented without leaking SQL into API routes

## 30. Architectural Summary

Discover's database should be deliberately boring.

PostgreSQL stores the user's durable discovery workspace, structured state, normalized results, and saved discoveries. The agent remains responsible for reasoning, while deterministic services remain responsible for execution. Qloo remains an external cultural-intelligence provider rather than becoming the database schema.

The central rule is:

> **Persist what the product needs to remember; do not persist everything the agent happens to process.**


---

# Alignment addendum (REQUIREMENTS v1.0)

The canonical entity list is REQUIREMENTS §8.1. Relative to the earlier drafts in this document:

| Change | Detail |
|---|---|
| `discovery_sessions.mode` | Values `self, someone_else, group, community, business`; add `intent TEXT` |
| New `users.is_guest`, `last_seen_at` | Guest-first identity (ADR-007); guests purged after `GUEST_RETENTION_DAYS` |
| New `user_preferences` | Settings and memory toggle |
| New `discovery_participants` | Group and recipient participants |
| New `discovery_runs`, `run_events` | Detached runs and persisted SSE events (PK `run_id, seq`); retention per `RUN_EVENT_RETENTION_DAYS` |
| `discovery_results` | Add `run_id`, `kind`, `rank`, `group_key`, `payload JSONB`, `explanation JSONB`, `source JSONB`, `schema_version` |
| New `result_feedback` | Closes the earlier gap: Feedback was required but had no table |
| `saved_items` | Stores a `snapshot JSONB`, `note`, `tags TEXT[]` |
| New `reports` | `ReportDocument` JSONB with `template`, `status` |
| New `share_links` | Immutable snapshot, hashed token, redaction, expiry, revocation, `view_count` |
| New `group_invites`, `group_contributions` | Invite links and moderated invitee input |

Indexes to add: `run_events(run_id, seq)`; `discovery_sessions(user_id, status, updated_at DESC)`; `share_links(token_hash)` unique; `group_invites(token_hash)` unique; `result_feedback(result_id, user_id)` unique; `discovery_runs(session_id, started_at DESC)`; partial unique index enforcing one `running` run per session (API-001).
