# Architecture Decision Records

**Normative source:** [`REQUIREMENTS.md`](../../REQUIREMENTS.md) §16 (Decision Register).  
Each record: **Context → Decision → Consequences**. Status: *Accepted* unless noted. Changing a decision means adding a new ADR that supersedes the old one (do not rewrite history).

| ADR | Title |
|---|---|
| 001 | Custom bounded agent orchestration |
| 002 | Single Qloo adapter with normalization layer |
| 003 | FastAPI async backend |
| 004 | PostgreSQL with JSONB |
| 005 | Voice is an input method |
| 006 | Streaming via SSE over fetch; detached runs |
| 007 | Guest-first identity and bearer JWTs |
| 008 | OpenAI-compatible LLM adapter |
| 009 | Mock / record / replay / live profiles |
| 010 | Mode and intent taxonomy |
| 011 | Shareable pages as immutable snapshots |
| 012 | Reports as a document model with multiple renderers |
| 013 | Pluggable current-information search |
| 014 | Documentation governance |
| 015 | Frontend stack |
| 016 | Hosting topology |

---

## ADR-001 — Custom bounded agent orchestration
**Context.** Discover must ask, call tools, evaluate, refine, and stop, with a visible trace and strict limits (AGT-001..003).  
**Decision.** Implement a small explicit loop (decide → act → observe → update state) with a Pydantic-validated decision object and a `ToolRegistry`. No general-purpose agent framework.  
**Consequences.** Full control of limits, events, and failure handling; less framework magic to debug; we own prompt/version hygiene and tests.

## ADR-002 — Single Qloo adapter with normalization layer
**Context.** Qloo wire formats and entity types are not yet verified against a live key (RSK-003).  
**Decision.** All Qloo access passes through `QlooClient` with intent-level methods returning internal models; raw→normalized conversion is a pure, fixture-tested layer.  
**Consequences.** Format surprises are absorbed in one module; the rest of the system is insulated; recorded fixtures become the source of truth.

## ADR-003 — FastAPI async backend
**Context.** I/O-bound orchestration with streaming responses.  
**Decision.** Python, FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic.  
**Consequences.** Native async + SSE support; typed schemas feed the API contract and tests.

## ADR-004 — PostgreSQL with JSONB
**Context.** State, results, reports, and events evolve quickly but need relational ownership and indexing.  
**Decision.** Relational keys and ownership as columns; evolving structures as JSONB with `schema_version` (DAT-001).  
**Consequences.** Schema churn rarely needs migrations; query ergonomics for flexible blobs are limited, so anything filtered frequently becomes a column.

## ADR-005 — Voice is an input method
**Context.** Voice must not become a parallel product path.  
**Decision.** Speech becomes editable text and enters the standard pipeline; browser recognition first, server STT fallback later (VOI-001..005). No audio storage.  
**Consequences.** One pipeline to test; browser support gaps handled by explicit UI states.

## ADR-006 — Streaming via SSE over `fetch`; detached runs
**Context.** The agent takes tens of seconds; the UI needs a live timeline; hosts have request-time limits; users close tabs and lose connectivity.  
**Decision.**  
- Use Server-Sent Events delivered over `fetch` (POST) rather than `EventSource`, so we can send bodies and `Authorization` headers.  
- A **run** is a background task independent of the HTTP connection. Every event is persisted with a per-run `seq`.  
- Clients resume with `Last-Event-ID`. Non-streaming clients receive JSON, or `202` plus polling after `RUN_SYNC_WAIT_SECONDS`.  
- Heartbeats keep idle proxies open.  
**Alternatives considered.** WebSockets (heavier, no replay semantics for free); long polling only (poor UX); fully synchronous request (host timeouts, no progress).  
**Consequences.** Resilient to disconnects and cold starts; requires an event table, orphaned-run recovery, and staging verification of proxy behavior (DEP-003). Single-instance in-process executor is acceptable for v1; DB-backed replay keeps scale-out possible.

## ADR-007 — Guest-first identity and bearer JWTs
**Context.** Users must try Discover instantly, yet accounts, history, and sharing are required.  
**Decision.**  
- `POST /auth/guest` issues a backend-signed guest JWT (a `users` row with `is_guest = true`).  
- Accounts use an external identity provider (default candidate: Supabase Auth; any OIDC/JWKS provider works). The backend only verifies tokens (`AUTH_JWKS_URL`, issuer, audience) and never stores passwords.  
- On sign-in, `POST /auth/claim` merges guest data into the account in one transaction.  
- Tokens travel as `Authorization: Bearer`; no cross-site cookies needed.  
**Consequences.** Zero-friction first use; simple CORS; IdP vendor can change without API changes. Guest tokens in browser storage are low-sensitivity by design (guest data is short-retention, ACC-007).

## ADR-008 — OpenAI-compatible LLM adapter
**Context.** Provider and model are not yet chosen; keys are not yet available.  
**Decision.** Define `LLMClient` against the OpenAI-compatible Chat Completions shape with native tool/function calling and JSON-schema output where available; model and base URL are environment settings. Structured decisions are validated with Pydantic; one retry; then safe failure.  
**Consequences.** Swap providers via env; a scripted `mock` LLM drives tests and demos; model-specific prompt tuning stays inside prompt modules.

## ADR-009 — Mock / record / replay / live profiles
**Context.** No Qloo key yet; tests must still be meaningful and the frontend must not wait.  
**Decision.** Every external provider has four implementations selected by `DISCOVER_PROFILE` (with per-provider overrides). `mock` uses deterministic scenario packs at the *normalized-model* level; `record` captures sanitized real traffic; `replay` serves it in CI; `live` is production (REQUIREMENTS §11).  
**Consequences.** Parallel work from day 1; the first live session is a short, scripted spike (TST-020). Mock output is always labelled synthetic (UX-105, TST-003) so it cannot masquerade as Qloo output. Mock fixtures do not prove wire-format correctness; only recorded fixtures do.

## ADR-010 — Mode and intent taxonomy
**Context.** Early docs mixed `personal/gift/community/business`, "someone else", and subject types; new needs include group discovery, compare, and trends.  
**Decision.** Five **modes** (who/what): `self`, `someone_else`, `group`, `community`, `business`. Separate **intents** (what operation): `recommend`, `taste_profile`, `audience_insight`, `location_insight`, `compare`, `trend`, `market_scan`. "Gift" is a goal type within `someone_else`.  
**Consequences.** New analysis capabilities do not multiply modes; the UI composes mode views from shared components. `personal` and `gift` are retired values (TAX-002).

## ADR-011 — Shareable pages as immutable snapshots
**Context.** Sharing results must not leak private data or change retroactively.  
**Decision.** A share copies a redacted, self-contained snapshot into `share_links`; tokens are ≥128-bit, stored hashed, revocable, optionally expiring; public pages are read-only and `noindex`. Link previews use a server-rendered metadata route on the frontend host (P2).  
**Consequences.** Deleting a session does not break or leak via shares unless the user revokes; storage duplication is accepted; the SPA alone cannot produce rich previews, hence the metadata route.

## ADR-012 — Reports as a document model with multiple renderers
**Context.** Business reports need export; formats multiply.  
**Decision.** Generate a structured `ReportDocument` (REQUIREMENTS §8.5). Renderers for HTML, Markdown, CSV, JSON, and PDF consume only that model. PDF is generated server-side by a lightweight pure-Python renderer under time/memory bounds, with a print-stylesheet fallback in the browser.  
**Consequences.** One generation path, many outputs; avoids headless-browser memory costs on small hosts; PDF styling is intentionally simpler than the on-screen report.

## ADR-013 — Pluggable current-information search
**Context.** Qloo provides affinity, not prices or availability; gift and product goals need current facts.  
**Decision.** `SearchProvider` interface; first implementation is an LLM-oriented search API (Tavily-class) chosen when keys are available. Results are labelled `web_search`, carry URL and retrieval time, and are treated as untrusted text. Without a provider, flows degrade to Qloo-only kinds and say so (INF-006).  
**Status.** Accepted; concrete vendor pending.

## ADR-014 — Documentation governance
**Context.** Duplicated detail across documents produced contradictions (endpoint names, mode names, stale status tables).  
**Decision.** `REQUIREMENTS.md` is canonical. Detail documents reference requirement IDs and carry an *Alignment* banner; conflicts are resolved in favor of `REQUIREMENTS.md` and fixed in the same change (REQUIREMENTS §0).  
**Consequences.** Small PRs touch one canonical table and the affected detail doc; reviewers check IDs.

## ADR-015 — Frontend stack
**Context.** Responsive SPA with streaming, maps, and many shared components.  
**Decision.** React + TypeScript + Vite; a typed API client generated from the contract; TanStack Query for server state; a streaming hook built on `fetch` + SSE parsing with resume; a single token-based component library shared by all mode views and the public share page.  
**Consequences.** Fast iteration and type safety; code-split by route (NFR-004).

## ADR-016 — Hosting topology
**Context.** Low-cost deployment with SSE support.  
**Decision.** Static/edge frontend host; containerized backend on a managed host; managed Postgres. Vendors are defaults (Vercel, Render, managed Postgres) and revisitable. SSE buffering disabled; heartbeats on; cold-start UI and keep-warm ping.  
**Status.** Accepted; vendors pending confirmation at M0.  
**Consequences.** Must verify long-lived streams in staging before the demo (DEP-003).

## ADR-017 — Business-first sequencing with mode modules
**Context.** The team narrowed hackathon focus to Discover for Business (market discovery), validated through a Qloo Ask-AI workflow, while insisting the other modes stay in scope.  
**Decision.** Build Business to full depth first as a *mode module* on shared foundations (Qloo client, evidence model, LLM client, run recorder, validation). Other modes are added later as sibling modules; unbuilt modes return `501 mode_not_available`. A CLI harness (REQUIREMENTS §11.3) is the first deliverable and verifies real Qloo behaviour before any UI.  
**Consequences.** Scope is unchanged; sequencing changes. Shared code must stay free of business vocabulary (FOC-003). Unverified Qloo parameter spellings are isolated as variants in one file and corrected after the first live run.

