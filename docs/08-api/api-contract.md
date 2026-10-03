# API Contract

> **Alignment:** Normative endpoints, enums, error codes, and the SSE protocol are defined in [`REQUIREMENTS.md`](../../REQUIREMENTS.md) §4 and §7. This document gives request/response schemas and worked examples. If it conflicts with `REQUIREMENTS.md`, the requirements win and this document must be fixed.  
> **Source of truth in code:** Pydantic models → generated OpenAPI (REST) and exported JSON Schema (SSE events). The frontend API client is generated from them in CI.

## 1. Principles

1. JSON bodies, `snake_case`, UUIDs, ISO-8601 UTC timestamps.
2. Versioned under `/api/v1`; additive changes only (REQUIREMENTS §7.1).
3. Product-level contract: no Qloo, LLM, database, or internal-tool structures leak out.
4. The backend owns discovery state; clients never send user IDs as proof of ownership.
5. Agent work is a **run**: it streams events, survives disconnects, and can be resumed or polled.
6. Errors are machine-readable (REQUIREMENTS §7.2); errors during a stream arrive as `run.failed`.
7. Keys and raw provider requests are never exposed.

## 2. Authentication

Bearer tokens on all non-public endpoints: `Authorization: Bearer <jwt>`.

### POST `/api/v1/auth/guest`
Creates a guest identity.

~~~json
// 201
{ "token": "eyJ...", "expires_at": "2026-10-31T00:00:00Z",
  "user": { "id": "usr_...", "is_guest": true } }
~~~

### POST `/api/v1/auth/claim`
Header: guest bearer **and** the account token in body.

~~~json
// request
{ "account_token": "eyJ..." }
// 200
{ "merged": { "sessions": 3, "saved": 5, "shares": 1 } }
~~~

### GET `/api/v1/me`
~~~json
{ "id": "usr_...", "is_guest": false, "display_name": "…", "email": "…",
  "preferences": { "default_location": "Lagos", "currency": "NGN", "language": "en",
                   "theme": "system", "memory_enabled": true } }
~~~

## 3. Meta

### GET `/api/v1/meta`
~~~json
{
  "version": "1.0",
  "profile": "mock",
  "synthetic_data": true,
  "modes": ["self","someone_else","group","community","business"],
  "intents": [{ "id": "recommend", "available": true },
              { "id": "compare",   "available": false, "reason": "not_verified" }],
  "result_kinds": ["movie","tv_show","artist","album","book","podcast","videogame",
                   "brand","product","place","restaurant","destination","event",
                   "experience","audience","trend","comparison","market_opportunity","insight"],
  "features": { "voice_fallback": false, "reports": true, "sharing": true,
                "group_invites": true, "current_info_search": false },
  "limits": { "max_message_chars": 4000, "max_participants": 12 },
  "providers": { "qloo": "mock", "llm": "mock", "search": "mock" }
}
~~~

## 4. Sessions

### POST `/api/v1/discovery/sessions`
~~~json
// request (all fields optional)
{ "mode": "someone_else", "intent": "recommend", "title": null,
  "initial_message": null }
// 201
{ "id": "ses_...", "mode": "someone_else", "intent": "recommend",
  "status": "active", "title": null, "created_at": "…" }
~~~
If `initial_message` is present, the response includes `run: { id, events_url }` and the client opens the event stream (see §5).

### GET `/api/v1/discovery/sessions`
Query: `status`, `mode`, `q`, `limit`, `cursor`. Returns `{ items: [SessionSummary], next_cursor }`.

### GET `/api/v1/discovery/sessions/{id}`
~~~json
{
  "id": "ses_...", "mode": "group", "intent": "recommend", "status": "active",
  "title": "Friday plans", "created_at": "…", "updated_at": "…",
  "state_summary": { "…": "see §9" },
  "participants": [ { "id": "par_...", "role": "member", "display_name": "Ada" } ],
  "active_run": { "id": "run_...", "status": "running", "last_seq": 14 },
  "latest_results": { "run_id": "run_...", "items": [ "DiscoveryResult" ], "groups": [], "limitations": [] }
}
~~~

### PATCH `/api/v1/discovery/sessions/{id}`
Allowed fields: `title`, `status` (`active|archived`), `mode`, `intent`.

### DELETE `/api/v1/discovery/sessions/{id}` → `204`

## 5. Messages and runs

### POST `/api/v1/discovery/sessions/{id}/messages`

Request (see REQUIREMENTS §7.4):

~~~json
{
  "message": "A birthday experience for my sister in Lagos under ₦100,000",
  "mode": "someone_else",
  "intent": "recommend",
  "input_type": "text",
  "action": null,
  "client_context": { "locale": "en-NG", "timezone": "Africa/Lagos" }
}
~~~

Headers: `Idempotency-Key: <uuid>` (recommended), `Accept: text/event-stream` (streaming) or `application/json`.

#### 5.1 Streaming response (`Accept: text/event-stream`)

~~~text
id: run_01H…:1
event: run.started
data: {"v":1,"run_id":"run_01H…","seq":1,"ts":"…","type":"run.started","data":{"session_id":"ses_…","mode":"someone_else","intent":"recommend"}}

id: run_01H…:2
event: phase.changed
data: {"v":1,"run_id":"run_01H…","seq":2,"ts":"…","type":"phase.changed","data":{"phase":"understanding","label":"Understanding your request"}}

id: run_01H…:3
event: tool.started
data: {"v":1,"run_id":"run_01H…","seq":3,"ts":"…","type":"tool.started","data":{"tool":"resolve_entities","step":1,"provider":"qloo","label":"Looking up the places and interests you mentioned"}}

id: run_01H…:4
event: tool.completed
data: {"v":1,"run_id":"run_01H…","seq":4,"ts":"…","type":"tool.completed","data":{"tool":"resolve_entities","step":1,"duration_ms":842,"summary":"Matched 2 of 2 interests"}}

id: run_01H…:7
event: result.partial
data: {"v":1,"run_id":"run_01H…","seq":7,"ts":"…","type":"result.partial","data":{"items":[ "DiscoveryResult" ]}}

id: run_01H…:9
event: response.delta
data: {"v":1,"run_id":"run_01H…","seq":9,"ts":"…","type":"response.delta","data":{"text":"Here are experiences that fit her taste"}}

id: run_01H…:12
event: result.set
data: {"v":1,"run_id":"run_01H…","seq":12,"ts":"…","type":"result.set","data":{"items":[ "DiscoveryResult" ],"groups":[{"key":"because_you_liked","label":"Because she likes …"}],"limitations":["Few verified prices in this area"]}}

id: run_01H…:13
event: run.completed
data: {"v":1,"run_id":"run_01H…","seq":13,"ts":"…","type":"run.completed","data":{"status":"completed","usage":{"steps":3,"duration_ms":14200}}}
~~~

Heartbeats: `event: heartbeat` every `SSE_HEARTBEAT_SECONDS`.

#### 5.2 Clarifying question

~~~text
id: run_01H…:5
event: question
data: {"v":1,…,"type":"question","data":{"question_id":"q_1","text":"Do you want something active or relaxed?","options":["Active","Relaxed","No preference"],"allow_free_text":true}}
~~~

The stream **closes** after `question`; the run is `needs_input`. The client answers with:

~~~json
{ "action": { "type": "answer_question", "question_id": "q_1", "answer": "Relaxed" } }
~~~

which starts a continuation run (new stream).

#### 5.3 Failure inside a stream

~~~text
event: run.failed
data: {"v":1,…,"type":"run.failed","data":{"error_code":"upstream_unavailable","message":"We couldn't reach one of our data sources.","recoverable":true,"resume_hint":"retry"}}
~~~

#### 5.4 JSON response (`Accept: application/json`)

`200` when the run finishes within `RUN_SYNC_WAIT_SECONDS`:

~~~json
{ "run": { "id": "run_...", "status": "completed" },
  "message": { "id": "msg_...", "role": "assistant", "content": "…" },
  "results": { "items": [], "groups": [], "limitations": [] },
  "question": null,
  "state_summary": {} }
~~~

Otherwise `202`:

~~~json
{ "run_id": "run_...", "status": "running",
  "events_url": "/api/v1/discovery/runs/run_.../events",
  "poll_url": "/api/v1/discovery/runs/run_..." }
~~~

### GET `/api/v1/discovery/runs/{run_id}`
~~~json
{ "id": "run_...", "session_id": "ses_...", "status": "completed", "phase": "composing",
  "mode": "someone_else", "intent": "recommend",
  "started_at": "…", "ended_at": "…", "last_seq": 13,
  "usage": { "steps": 3, "duration_ms": 14200 }, "error_code": null }
~~~

### GET `/api/v1/discovery/runs/{run_id}/events`
- `Accept: text/event-stream` with optional `Last-Event-ID: run_…:<seq>` → replays later events, then continues live if still running.
- `Accept: application/json` → `{ "events": [ … ], "last_seq": N }` (used for History timelines).

### POST `/api/v1/discovery/runs/{run_id}/cancel`
`202` → run emits `run.cancelled`. Cancelling a finished run returns `409`.

### GET `/api/v1/discovery/sessions/{id}/messages`
Cursor-paginated conversation messages (`role`, `content`, `input_type`, `run_id`, `created_at`).

## 6. Participants (group) and invites

### POST `/api/v1/discovery/sessions/{id}/participants`
~~~json
{ "role": "member", "display_name": "Ada",
  "profile": { "likes": ["Afrobeats","Nollywood thrillers"], "dislikes": ["horror"],
               "notes": "Vegetarian-friendly places" } }
~~~
`PATCH`/`DELETE` on `/participants/{pid}`. Limit: `MAX_PARTICIPANTS`.

### POST `/api/v1/discovery/sessions/{id}/invites`  (P2)
~~~json
// request
{ "expires_in_hours": 72, "max_contributions": 10 }
// 201
{ "id": "inv_...", "url": "https://<frontend>/join/<token>", "expires_at": "…" }
~~~
The token appears only in this response.

### Public: GET `/api/v1/public/invites/{token}`, POST `/api/v1/public/invites/{token}/contributions`
~~~json
// contribution request
{ "display_name": "Femi", "likes": ["jazz","street food"], "dislikes": [], "note": "…" }
// 202 — pending organizer acceptance
{ "status": "pending" }
~~~
Organizer: `POST …/contributions/{cid}/accept` or `/reject`.

## 7. Results and feedback

### GET `/api/v1/discovery/sessions/{id}/results`
Query: `run_id`, `kind`, `group`. Returns `{ items: [DiscoveryResult], groups: [...], limitations: [...] }`.

### GET `/api/v1/results/{result_id}`
Full `DiscoveryResult` including evidence fragments.

### `DiscoveryResult`
See REQUIREMENTS §8.3 for the normative shape and the explanation-fragment rules (`evidence` | `user_context` | `interpretation`).

### PUT `/api/v1/results/{result_id}/feedback`
~~~json
{ "value": "dislike" }   // like | dislike | not_relevant | already_know
~~~
`204`. `DELETE` clears it.

## 8. Direct analysis (P2)

### POST `/api/v1/analysis/compare`
~~~json
{ "subjects": [
    { "type": "entity", "ref": "Burna Boy" },
    { "type": "entity", "ref": "Wizkid" } ],
  "location": "Lagos",
  "dimensions": ["tags","audiences"] }
~~~
Streams or returns a `comparison` result (`payload` with `shared`, `unique_by_subject`, `differences`).

### POST `/api/v1/analysis/trends`
~~~json
{ "subject": { "type": "category", "ref": "streetwear" },
  "location": "Lagos", "window": { "from": "2025-10-01", "to": "2026-10-01" } }
~~~
Returns a `trend` result (`payload.series`, `payload.window`). If not supported, `422` with `unsupported_intent_context` and a suggested alternative.

## 9. State summary

The user-safe projection of durable state (never the full internal state):

~~~json
{
  "mode": "someone_else",
  "intent": "recommend",
  "goal": "Birthday experience",
  "subject": { "type": "person", "description": "Sister", "relationship": "sister" },
  "resolved_entities": [ { "id": "ent_1", "name": "…", "kind": "artist" } ],
  "constraints": { "budget": { "amount": 100000, "currency": "NGN" },
                   "location": "Lagos", "exclusions": [] },
  "assumptions": [ "Assumed a daytime outing" ],
  "missing_information": [ { "key": "occasion_date", "reason": "…" } ],
  "participants": []
}
~~~

## 10. Saved

### POST `/api/v1/saved`
~~~json
{ "target_type": "result", "target_id": "res_...", "note": "For her birthday", "tags": ["gift"] }
~~~
`201` with the saved item (including a snapshot, so the item survives session deletion).  
`GET /saved?tag=&kind=&limit=&cursor=`; `GET|PATCH|DELETE /saved/{id}`.

## 11. Reports

### POST `/api/v1/reports`
~~~json
{ "session_id": "ses_...", "template": "business_market",
  "options": { "include_compare": true, "include_trends": false, "title": null } }
// 202
{ "id": "rpt_...", "status": "queued", "events_url": "/api/v1/reports/rpt_.../events" }
~~~

`GET /reports/{id}` returns status and, when `ready`, the `ReportDocument` (REQUIREMENTS §8.5).  
`GET /reports/{id}/events` emits `phase.changed`, `report.section`, `report.completed`, `run.failed`.

### GET `/api/v1/reports/{id}/export?format=pdf|md|csv|json|html`
Returns the file with `Content-Disposition: attachment`. `422 export_unsupported` for unknown formats; `409 report_not_ready` while generating.

## 12. Sharing

### POST `/api/v1/shares`
~~~json
{ "target_type": "report",           // result | result_set | report | saved
  "target_id": "rpt_...",
  "redaction": { "hide_names": true, "hide_prompt": true, "hide_notes": true },
  "expires_in_days": 30,
  "allow_download": false }
// 201 (token appears only here)
{ "id": "shr_...", "url": "https://<frontend>/s/<token>", "expires_at": "…" }
~~~

### GET `/api/v1/public/shares/{token}` (no auth)
~~~json
{ "type": "report", "title": "…", "created_at": "…", "synthetic_data": false,
  "content": { "…": "ReportDocument | results | result" },
  "attribution": { "powered_by": ["Qloo"] },
  "allow_download": false }
~~~
`410 share_revoked | share_expired`; unknown tokens return `404`. Responses carry `X-Robots-Tag: noindex` and `Cache-Control: no-store` for revoked/expired lookups.

`GET /shares`, `PATCH /shares/{id}`, `DELETE /shares/{id}` (revoke) as in REQUIREMENTS §7.3.

## 13. Voice (P2)

### POST `/api/v1/voice/transcriptions`
`multipart/form-data` with `audio` (size/duration limited). Returns `{ "text": "…", "language": "en" }`. Audio is not stored.

## 14. Pagination, idempotency, concurrency

- **Pagination:** `limit` (default 20, max 100) and opaque `cursor`; responses return `next_cursor`.
- **Idempotency:** the same `Idempotency-Key` on the same endpoint and identity returns the original outcome (including the same `run_id`) for 24h; a different body with the same key returns `409 idempotency_conflict`.
- **Concurrency:** one active run per session (`409 run_in_progress`); state writes use optimistic `state_version` (`409 state_conflict`, retried once server-side).

## 15. Errors and status mapping

Error body and `code` vocabulary: REQUIREMENTS §7.2. Mid-stream failures: `run.failed`. Provider errors map as: Qloo/LLM/search unavailable → `upstream_unavailable` (502/503); provider timeout → `upstream_timeout` (504); provider rate limit → `rate_limited` (429, with `Retry-After` when known).

## 16. Security boundary

Authentication and ownership are enforced server-side for every non-public endpoint. A resource owned by another user returns `404`. Public endpoints are rate-limited, hash-lookup tokens, return no private fields, and send `noindex`. Provider text is escaped by clients; the API never returns raw HTML from providers.

## 17. Rate limits

`429 rate_limited` with `Retry-After` and `X-RateLimit-Limit/Remaining/Reset` headers. Defaults in REQUIREMENTS §9.2.

## 18. Contract testing

1. OpenAPI generated from the app is diffed in CI; breaking changes fail the build.
2. SSE event models export JSON Schema; the mock server and the frontend parser both validate against it.
3. Replay tests assert that the same scenario yields the same ordered event types in `mock` and in `replay`.
4. Access-control tests hit every endpoint with another user's identifiers (ACC-008).
5. Resume tests: drop the connection at every event index and verify `Last-Event-ID` replay yields no gaps or duplicates.

## 19. Implementation order

Follows REQUIREMENTS §14.2: `/health`, `/meta`, `/auth/guest`, sessions, messages with SSE (scripted agent), runs/replay → results/feedback → saved/history → participants → reports/exports → shares/public → analysis → invites → voice.
