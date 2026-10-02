# Discover — Requirements Specification

**Project:** Discover  
**Repository:** `Inialpha/Discover`  
**Version:** 1.0 (canonical baseline)  
**Status:** Living specification — ready for implementation  
**License:** MIT  
**Primary integration:** Qloo Cultural Intelligence API  
**Submission deadline:** 30 Oct 2026, 11:45 PM EDT (re-verify against the official rules)

---

## 0. How to Use This Document

### 0.1 Precedence rule

`REQUIREMENTS.md` is the **single canonical source of truth**. Every other document in this repository is a *detail document*: it elaborates a part of this specification and must reference requirement IDs from here rather than redefine them.

If a detail document conflicts with this file, **this file wins**, and the detail document must be corrected in the same change.

Canonical items that live only here (and are merely referenced elsewhere):

| Canonical item | Section |
|---|---|
| Glossary and terminology | §2 |
| Mode, intent, subject, result-kind, status enums | §4 |
| Functional requirements and IDs | §5 |
| UX and page requirements | §6 |
| API surface, streaming protocol, error codes | §7 |
| Data model entities and enums | §8 |
| Configuration and runtime limits | §9 |
| Test and delivery profiles | §11 |
| Delivery plan and priorities | §14 |
| Decision register | §16 |

### 0.2 Requirement IDs and priorities

Requirements use the form `AREA-NNN` (for example `STR-004`). IDs are never reused. A removed requirement is marked `withdrawn`, not deleted.

**Priority tiers sequence the work; they never remove scope.** Everything in this document is in scope for the submission.

| Tier | Meaning |
|---|---|
| **P0** | Backbone. Needed for the core journey to work end to end. Built first. |
| **P1** | Completes the primary product experience and every discovery mode. |
| **P2** | Completes breadth: advanced analysis, collaboration, exports, polish. Built in parallel tracks once P0 is stable. |

### 0.3 Document map

| Document | Role |
|---|---|
| `docs/01-decisions/decision-records.md` | ADRs: why each major decision was made |
| `docs/02-architecture/system-architecture.md` | Layers, lifecycle, runtime model |
| `docs/03-backend/backend-architecture.md` | Backend structure and conventions |
| `docs/04-database/database-architecture.md` | Table-level schema detail |
| `docs/05-frontend/frontend-architecture.md` | Frontend structure and component detail |
| `docs/06-discovery-modes/discovery-state-and-agent-tools.md` | State models, tool schemas, agent prompts |
| `docs/07-qloo/qloo-integration.md` | Qloo adapter detail, query construction |
| `docs/08-api/api-contract.md` | Request/response schemas and examples for §7 |
| `docs/09-deployment/deployment-architecture.md` | Hosting, Docker, environments |
| `docs/10-testing/testing-strategy.md` | Test layers and profile mechanics for §11 |
| `docs/11-hackathon/hackathon-strategy.md` | Submission mapping and demo narrative |

### 0.4 Iteration rule

When a significant product or architectural decision changes:

1. Update this document (and bump the minor version).
2. Add or amend an ADR.
3. Update the affected detail documents.
4. Only then change the implementation.

Implementation must not silently diverge from this document.

---

## 1. Purpose and Vision

Discover is an agentic cultural-intelligence and discovery platform. People, groups, communities, and businesses describe what they want in natural language (text or voice). The Discover agent interprets the goal, extracts preferences and context, asks only the questions that matter, grounds entities through Qloo, queries Qloo's cultural intelligence, evaluates and refines the results, and presents discoveries with honest, evidence-based explanations. Where the goal needs time-sensitive facts (prices, availability, opening hours), it supplements Qloo with a clearly labelled current-information source.

Discover answers a broader question than "what is similar to this?":

> **Given what matters to me, this person, this group, this community, or this business, what should we discover next?**

**PRD-001 (P0)** Qloo materially influences every discovery outcome; removing Qloo must visibly remove capability.  
**PRD-002 (P0)** Users never need to know Qloo syntax, entity IDs, tags, or parameters.  
**PRD-003 (P0)** Discover behaves as an agent, not a chatbot: it keeps state, asks, uses tools, iterates, and stops.  
**PRD-004 (P0)** The product shows its work: users see what the agent is doing (timeline) and why each result was chosen (evidence).  

---

## 2. Glossary

| Term | Meaning |
|---|---|
| **Mode** | *Who or what* the discovery is for: `self`, `someone_else`, `group`, `community`, `business` (§4.1). |
| **Intent** | *What kind of operation* is wanted: recommend, compare, trends, audience insight, etc. (§4.2). Orthogonal to mode. |
| **Session** | A durable discovery workspace holding conversation, state, runs, and results. |
| **Run** | One agent execution triggered by one user message or action. Runs are detached from the HTTP connection. |
| **Event** | A user-safe record emitted during a run (status, tool step, question, partial result). Streamed over SSE and persisted. |
| **Participant** | A person inside a session whose tastes contribute to discovery (the user, a recipient, a group member). |
| **Signal** | An input that influences affinity (entities, tags, audiences, location signals). |
| **Filter** | A constraint on which results are eligible (type, location, price level, exclusions). |
| **Result** | A normalized discovery item of a defined `kind`, with explanation and provenance. |
| **Evidence** | Information returned directly by an external source (Qloo or search). |
| **Interpretation** | A connection the LLM reasoned from evidence. Always labelled as such. |
| **Report** | A structured document composed from a session's results (§5.10). |
| **Share link** | A revocable public read-only snapshot of a result set, report, or saved list (§5.11). |
| **Profile** | A runtime test/delivery configuration: `mock`, `record`, `replay`, `live` (§11). |

---

## 3. Users

| User | Needs |
|---|---|
| **Individual** | Personalized discovery across movies, TV, music, food, places, travel, brands, events. |
| **Gift giver / planner** | Gifts and experiences for another person, within budget and location. |
| **Group organizer** | Shared plans that fit several people's tastes at once. |
| **Community leader / researcher** | Culturally relevant experiences and understanding of an audience without stereotyping. |
| **Business user** | Market, audience, product and location intelligence; exportable reports; evidence they can defend. |
| **Judge / reviewer** | A fast, honest demonstration that Qloo and agentic behavior matter. |

---

# 4. Canonical Taxonomy

These enums are authoritative. Code, database, API, prompts, and UI must use exactly these values. Adding a value is a requirements change (§19).

## 4.1 Discovery modes (`mode`)

| Value | Label | Subject | Notes |
|---|---|---|---|
| `self` | Discover for Me | The current user | Replaces `personal`. |
| `someone_else` | Discover for Someone Else | One other person | Gifts, outings, and occasions are *goals* within this mode (`goal_type = gift` etc.), not a separate mode. Replaces `gift`. |
| `group` | Discover for a Group | Two or more specific people | Blended tastes for shared plans. |
| `community` | Discover for Community | A community, audience, or place-based group | Context, not individual taste. |
| `business` | Discover for Business | A business, brand, or market | Cultural intelligence and opportunity exploration. |

**TAX-001 (P0)** `mode` may be omitted by the client; the agent infers it, records it in state with a confidence note, and the user can change it at any time.  
**TAX-002 (P0)** Legacy values (`personal`, `gift`) must not appear in code or docs except in a migration note.

## 4.2 Intents (`intent`)

| Value | Meaning | Typical Qloo capability |
|---|---|---|
| `recommend` | Return recommended entities (default). | Insights |
| `taste_profile` | Summarize a subject's taste across domains. | Lookup + Insights (tags/affinities) |
| `audience_insight` | Describe audience affinities/demographics for a context. | Insights (audience/demographics) |
| `location_insight` | Explore place-based affinity and heatmaps. | Insights (location/heatmap) |
| `compare` | Compare entities, audiences, markets, or taste sets. | Analysis/compare |
| `trend` | Show change over time for entities or categories. | Trends |
| `market_scan` | Business-oriented exploration combining the above. | Composite |

**TAX-003 (P0)** A session may hold several runs with different intents (for example `recommend` then `compare`).  
**TAX-004 (P1)** Qloo capability availability per intent must be discoverable at runtime via `GET /api/v1/meta` so the UI can hide unsupported intents.

## 4.3 Subject types (`subject.type`)

`self`, `person`, `group`, `community`, `business`. Mode → default subject: `self→self`, `someone_else→person`, `group→group`, `community→community`, `business→business`.

## 4.4 Statuses

| Entity | Values |
|---|---|
| Session `status` | `active`, `archived`, `deleted` |
| Run `status` | `queued`, `running`, `needs_input`, `completed`, `failed`, `cancelled`, `timed_out` |
| Run `phase` (user-visible) | `understanding`, `clarifying`, `grounding`, `querying`, `evaluating`, `refining`, `enriching`, `composing` |
| Report `status` | `queued`, `generating`, `ready`, `failed` |
| Share `status` | `active`, `revoked`, `expired` |

## 4.4a Result kinds (`result.kind`)

`movie`, `tv_show`, `artist`, `album`, `book`, `podcast`, `videogame`, `brand`, `product`, `place`, `restaurant`, `destination`, `event`, `experience`, `audience`, `trend`, `comparison`, `market_opportunity`, `insight`.

**TAX-005 (P0)** Qloo entity-type identifiers are mapped to result kinds by a declarative `ResultKindRegistry`. The set of Qloo entity types must be taken from Qloo's current entity-type guide, never hard-coded from memory.  
**TAX-006 (P0)** Unknown kinds must render with a safe generic card and must not crash the UI or API.

## 4.5 Provenance labels (`source`, `basis`)

Every result and every explanation fragment carries provenance:

| Field | Values |
|---|---|
| `source.provider` | `qloo`, `web_search`, `user`, `agent` |
| `explanation.basis` (per fragment) | `evidence` (returned by a provider), `user_context` (stated by the user), `interpretation` (reasoned by the LLM) |

**TAX-007 (P0)** Interpretation must never be displayed or exported as if a provider stated it.

---

# 5. Functional Requirements

## 5.1 Discovery modes

### Self (`self`)
| ID | Requirement | Pri |
|---|---|---|
| MOD-001 | Accept free-form goals ("a movie for tonight, intelligent thrillers, nothing too depressing"). | P0 |
| MOD-002 | Extract liked/disliked entities, tags, moods, constraints (time, place, budget, exclusions) into state. | P0 |
| MOD-003 | Support cross-domain discovery (taste in one domain informs results in another). | P0 |
| MOD-004 | Offer a Taste Canvas: resolved entities and tags shown as editable chips the user can remove, add, or mark as dislikes. | P1 |
| MOD-005 | Produce a `taste_profile` insight on request (themes across the user's inputs). | P2 |

### Someone else (`someone_else`)
| ID | Requirement | Pri |
|---|---|---|
| MOD-010 | Capture recipient description, relationship, occasion, location, and constraints as conversational context. | P0 |
| MOD-011 | Support `goal_type` values: `gift`, `outing`, `experience`, `media`, `general`. | P0 |
| MOD-012 | Respect budget (amount + currency) and location. Gifts that need prices use the current-information source (§5.6); Qloo-only results never claim prices. | P0 |
| MOD-013 | Ask only about information that materially changes results (age range, budget, occasion, location). | P0 |
| MOD-014 | Provide a Gift Brief view: recipient card, occasion, budget, results grouped as *Experiences*, *Things*, *Media*. | P1 |
| MOD-015 | Allow shortlisting and side-by-side comparison of up to 4 results. | P1 |

### Group (`group`)
| ID | Requirement | Pri |
|---|---|---|
| MOD-020 | Support two or more participants, each with their own preferences, dislikes, and constraints. | P0 |
| MOD-021 | Build the blended query from per-participant signals; support blend strategies `consensus` (maximize overlap), `balanced` (fair coverage), `variety` (each member gets something). | P1 |
| MOD-022 | Show per-participant fit on each result ("fits Ada, Tolu; weaker for Femi"). Fit statements must be `evidence` or `interpretation`-labelled. | P1 |
| MOD-023 | Hard constraints (allergies are *not* stored, see PRIV-005; stated exclusions, budget, location) apply to the whole group. | P1 |
| MOD-024 | Invite collection: the organizer can create an invite link; invitees submit their own tastes without an account (§5.12, `GRP-*`). | P2 |
| MOD-025 | Group dashboard: shared signals vs unique signals visualization and a "why this works for everyone" summary. | P1 |

### Community (`community`)
| ID | Requirement | Pri |
|---|---|---|
| MOD-030 | Capture community description, location, event/experience goal, audience size/character as context. | P0 |
| MOD-031 | Use location- and audience-oriented Qloo signals where supported. | P0 |
| MOD-032 | Avoid stereotypes: no demographic assumptions beyond what the user supplied or Qloo returned. | P0 |
| MOD-033 | State uncertainty and limitations explicitly in the response. | P0 |
| MOD-034 | Community Landscape view: categories, top affinities, map/heat view when location data exists. | P1 |

### Business (`business`)
| ID | Requirement | Pri |
|---|---|---|
| MOD-040 | Capture business description, category, objective, audience, market/location, competitors (optional). | P0 |
| MOD-041 | Support objectives: market exploration, audience understanding, product positioning, location planning, partnership/brand-affinity discovery. | P1 |
| MOD-042 | Produce business-grade output: market overview, audience affinities, adjacent categories, opportunities, risks, limitations. | P1 |
| MOD-043 | Separate observed evidence from recommendations in every business output. | P0 |
| MOD-044 | Business Workspace UI: brief builder, insights dashboard, opportunity cards, compare and trends panels, report builder (§6.7). | P1 |
| MOD-045 | Never assert revenue, market-size, or ROI figures unless returned by a provider and cited. | P0 |

## 5.2 Analysis intents

| ID | Requirement | Pri |
|---|---|---|
| INT-001 | `recommend` runs the standard agent loop. | P0 |
| INT-002 | `compare`: compare two or more entities, taste sets, audiences, or markets; result kind `comparison` with per-dimension differences, shared affinities, and unique affinities. | P2 |
| INT-003 | `trend`: show direction/magnitude over time for entities or categories where Qloo supports it; result kind `trend`; must state the time window. | P2 |
| INT-004 | `audience_insight` and `location_insight`: return structured insight results (kinds `audience`, `insight`) with map/heatmap payloads when available. | P1 |
| INT-005 | `market_scan` composes INT-002/003/004 into a business overview. | P2 |
| INT-006 | Direct (non-conversational) endpoints exist for compare and trends so the UI can offer explorer panels without a chat turn (§7.4). | P2 |
| INT-007 | If Qloo does not support an intent for the requested context, the agent says so plainly and offers the nearest supported alternative. | P0 |

## 5.3 Agent behavior

| ID | Requirement | Pri |
|---|---|---|
| AGT-001 | Controlled loop: understand → decide → act → observe → update state → decide again → respond. | P0 |
| AGT-002 | Bounded execution: max 8 steps per run (configurable), per-tool timeouts, total run budget, no unbounded loops. | P0 |
| AGT-003 | Structured decisions: the LLM emits a validated decision object (`ask_user`, `call_tool`, `respond`); invalid output is retried once, then fails safely. | P0 |
| AGT-004 | Ask at most one question per turn, only when missing information materially changes results; never ask what can be inferred. | P0 |
| AGT-005 | If the user declines to answer, proceed with stated assumptions and say so. | P0 |
| AGT-006 | Ground every named entity through lookup before using it as a signal; disambiguate when confidence is low. | P0 |
| AGT-007 | Evaluate results against constraints; refine at most twice automatically before presenting best-effort results with caveats. | P0 |
| AGT-008 | Support user refinement actions (exclude, "more like this", change constraint, change mode/intent) without losing prior state. | P0 |
| AGT-009 | Internal prompts, tool schemas, and chain-of-thought are never exposed. Only user-safe event summaries are streamed. | P0 |
| AGT-010 | The agent states when it cannot find enough information, and why. | P0 |
| AGT-011 | Prompt-injection hygiene: content from search results or user-contributed text (invites) is treated as data, never as instructions. | P0 |
| AGT-012 | The tool set is registry-driven (`ToolRegistry`); adding a tool requires a schema, a timeout, a user-safe label, and tests, not agent-core changes. | P1 |

## 5.4 Tools (agent-visible)

| Tool | Purpose | Pri |
|---|---|---|
| `resolve_entities` | Lookup free-text names → Qloo entities (with disambiguation candidates). | P0 |
| `query_recommendations` | Qloo insights from signals + filters. | P0 |
| `query_audience_insights` | Audience/demographic/location insights. | P1 |
| `query_trends` | Trend data. | P2 |
| `compare_subjects` | Compare entities/audiences/markets. | P2 |
| `search_current_info` | Prices, availability, hours, recent news (§5.6). | P1 |
| `evaluate_results` | Check results against state constraints; produce keep/drop/refine verdicts. | P0 |
| `compose_response` | Produce the user-facing response and explanation fragments. | P0 |

Tool schemas live in `docs/06-discovery-modes/discovery-state-and-agent-tools.md` and must not contradict this table.

## 5.5 Qloo integration

| ID | Requirement | Pri |
|---|---|---|
| QLO-001 | All Qloo access goes through a single adapter (`QlooClient` interface); no Qloo URLs, parameter names, or raw payloads outside it. | P0 |
| QLO-002 | The adapter exposes *intent-level* methods (`resolve`, `recommend`, `audience`, `compare`, `trends`) returning normalized internal models. | P0 |
| QLO-003 | Raw Qloo responses are normalized by a pure function layer, testable from recorded fixtures. | P0 |
| QLO-004 | Explainability data from Qloo, where available, is preserved as `evidence` and surfaced in the UI. | P0 |
| QLO-005 | Bounded retries with backoff for transient failures; clear typed errors (`rate_limited`, `upstream_unavailable`, `invalid_request`, `empty_result`). | P0 |
| QLO-006 | Response caching for lookup and repeatable insights, keyed by normalized request; TTL configurable. | P1 |
| QLO-007 | Location handling is configurable per request; no hard-coded city. Supported locations are validated at runtime in `record` mode (RSK-002). | P0 |
| QLO-008 | A capability probe (`GET /meta`) reports which Qloo capabilities work with the configured key. | P1 |
| QLO-009 | The Qloo API key is server-side only. | P0 |
| QLO-010 | Qloo attribution/branding requirements from the hackathon and terms of use are honored in the UI (§13). | P0 |

## 5.6 Current-information source

| ID | Requirement | Pri |
|---|---|---|
| INF-001 | A `SearchProvider` interface supplies time-sensitive facts (prices, availability, hours, recent events). The provider is configurable (ADR-013). | P1 |
| INF-002 | Qloo selects *what* to consider (affinity, brands, categories); the search provider supplies *current specifics*. Their contributions are labelled `source.provider = qloo` vs `web_search`. | P1 |
| INF-003 | Budget filtering applies only to items with a stated price. Items without a verified price are labelled "price unverified" and are excluded from strict budgets unless the user allows them. | P1 |
| INF-004 | Product (`kind = product`) results must include a source URL and retrieval timestamp. | P1 |
| INF-005 | Search snippets are treated as untrusted data (AGT-011). | P0 |
| INF-006 | If no search provider is configured, gift and product flows degrade to experiences, places, brands, and media, and say so. | P0 |

## 5.7 Streaming, runs, and the agent timeline

| ID | Requirement | Pri |
|---|---|---|
| STR-001 | Message submission streams run events over Server-Sent Events (SSE) when the client sends `Accept: text/event-stream`. | P0 |
| STR-002 | A **run** is detached from the connection: closing the browser tab does not cancel it; explicit cancel does. | P0 |
| STR-003 | Every event is persisted with a monotonically increasing `seq` per run and can be replayed with `Last-Event-ID`. | P0 |
| STR-004 | Non-streaming clients may request JSON; the server waits up to `RUN_SYNC_WAIT_SECONDS`, then returns `202` with a run reference to poll. | P0 |
| STR-005 | Event types are fixed and versioned (§7.6); unknown event types must be ignored by clients. | P0 |
| STR-006 | Heartbeat events every `SSE_HEARTBEAT_SECONDS` keep proxies from closing idle streams. | P0 |
| STR-007 | The final answer streams token-by-token (`response.delta`) before the structured `result.set` / `run.completed` events. | P1 |
| STR-008 | Partial results may be emitted as soon as they normalize (`result.partial`) so the UI can render progressively. | P1 |
| STR-009 | Events expose only user-safe labels and summaries; never prompts, raw provider payloads, keys, or hidden reasoning. | P0 |
| STR-010 | Run events are retained for `RUN_EVENT_RETENTION_DAYS` for timeline replay in History, then pruned (results persist independently). | P1 |
| STR-011 | Stream failure after partial progress ends with a terminal `run.failed` carrying a recoverable flag and the last good state; the user can retry from state. | P0 |
| STR-012 | Report generation uses the same event mechanism (§5.10). | P2 |

## 5.8 Results and explanations

| ID | Requirement | Pri |
|---|---|---|
| RES-001 | Results are normalized into the `DiscoveryResult` model (§8.3) regardless of source. | P0 |
| RES-002 | Each result carries an explanation split into fragments tagged `evidence`, `user_context`, or `interpretation` (TAX-007). | P0 |
| RES-003 | Results state a match strength using only provider-supplied or clearly-derived values; no invented percentages. | P0 |
| RES-004 | Results are grouped into labelled sections when useful ("Because you liked…", "Adventurous picks", "Closest to the group"). | P1 |
| RES-005 | Each result has: title, kind, image (if available), short description, key facts, links, provenance, and actions (save, feedback, share, compare, more-like-this, exclude). | P0 |
| RES-006 | Place results carry coordinates when available and appear on a map view. | P1 |
| RES-007 | Results expose "why this?" with the evidence chain: input signals → connection → result. | P1 |
| RES-008 | Filtering and sorting in the UI (kind, group, strength) without a server round-trip when the result set is loaded. | P1 |
| RES-009 | The response includes limitations ("fewer matches than expected for this location"). | P0 |
| RES-010 | Result payloads carry `schema_version`; new kinds add a `payload` shape, not a new table. | P0 |

## 5.9 Refinement and feedback

| ID | Requirement | Pri |
|---|---|---|
| FBK-001 | Per-result feedback: `like`, `dislike`, `not_relevant`, `already_know`. | P0 |
| FBK-002 | Feedback is stored and applied to subsequent runs in the same session as exclusions or signal adjustments. | P0 |
| FBK-003 | Authenticated users' feedback may also inform later sessions (taste memory), controllable in Settings. | P2 |
| FBK-004 | Refinement actions are structured (`exclude_result`, `more_like_this`, `update_constraint`, `change_mode`, `change_intent`) and may accompany or replace free text. | P0 |
| FBK-005 | Maximum automatic refinements per run: 2. Maximum user refinement turns per session: soft limit with guidance, hard limit via rate limiting. | P0 |

## 5.10 Reports and export

| ID | Requirement | Pri |
|---|---|---|
| RPT-001 | A **Report** is generated from a session's results, state summary, and evidence using a template (§8.5): `business_market`, `audience_brief`, `community_brief`, `gift_brief`, `group_plan`, `personal_taste`. | P1 |
| RPT-002 | Reports are structured documents (`ReportDocument`: title, summary, sections, tables, charts, evidence appendix, limitations, methodology). | P1 |
| RPT-003 | Every report section labels content `evidence` vs `interpretation` and lists sources and retrieval times. | P0 |
| RPT-004 | Report narrative generation streams via events (STR-012) and can be edited in place by the user before export. | P2 |
| RPT-005 | Export formats: **PDF**, **Markdown**, **CSV** (result tables), **JSON** (full structured), **HTML** (standalone). | P1 |
| RPT-006 | Business reports include: executive summary, market/audience overview, key affinities, opportunity cards, comparison and trend sections (if run), risks and limitations, methodology. | P1 |
| RPT-007 | Reports never include fabricated figures (MOD-045) and always include the data-as-of timestamp. | P0 |
| RPT-008 | Branding: reports carry Discover branding and the required Qloo attribution. | P0 |
| RPT-009 | Export generation is bounded in time and memory (§9.2) and runs off the request path. | P1 |
| RPT-010 | A report can be shared (§5.11) and regenerated from the same session with updated state. | P2 |

## 5.11 Sharing

| ID | Requirement | Pri |
|---|---|---|
| SHR-001 | Users can create a **share link** for: a result set, a single result, a report, or a saved list. | P1 |
| SHR-002 | A share is an immutable **snapshot** (content copied at creation), so later edits or deletions of the session do not alter or leak through the link. | P0 |
| SHR-003 | Tokens are unguessable (≥128 bits), looked up by hash, and revocable; shares support optional expiry. | P0 |
| SHR-004 | Shared pages require no login, are read-only, send `noindex`, and show a "Created with Discover" footer with attribution. | P0 |
| SHR-005 | Redaction controls at creation: hide recipient/participant names, hide original prompt, hide notes. Default hides names and the raw conversation; the conversation is never shared. | P0 |
| SHR-006 | Shared pages render the same result presentation components as the workspace (§6.5), including evidence. | P1 |
| SHR-007 | Rich link previews (title, description, image) for shared URLs (ADR-011). | P2 |
| SHR-008 | Optional download permission: viewers may export a shared report if the creator allows it. | P2 |
| SHR-009 | Share view counts visible to the creator (aggregate only; no viewer identification). | P2 |

## 5.12 Accounts, guests, history, saved, and group contribution

| ID | Requirement | Pri |
|---|---|---|
| ACC-001 | **Guest first:** a visitor can use the product immediately; the server issues a guest identity (`POST /auth/guest`). | P0 |
| ACC-002 | **Accounts:** sign-up/sign-in via the configured identity provider (ADR-007); the backend verifies tokens and never stores passwords. | P1 |
| ACC-003 | **Claiming:** on sign-in, a guest's sessions, saved items, and shares are merged into the account atomically. | P1 |
| ACC-004 | History: list, search, resume, rename, archive, and delete sessions; view past run timelines. | P1 |
| ACC-005 | Saved: save results or whole sessions with notes and tags; edit and delete. | P1 |
| ACC-006 | Settings: default location, currency, language, units, theme, memory/personalization toggle, data export, account deletion. | P1 |
| ACC-007 | Guest data retention is limited (`GUEST_RETENTION_DAYS`) and disclosed. | P1 |
| ACC-008 | Access control: a user can only access their own sessions, results, saved items, reports, and shares. Verified by tests for every endpoint. | P0 |
| GRP-001 | Invite links let non-account invitees submit taste input to a group session (names, liked/disliked entities, free text). | P2 |
| GRP-002 | Invitee input is treated as untrusted (AGT-011), rate-limited, size-limited, and moderated for abuse. | P2 |
| GRP-003 | The organizer reviews and accepts contributions before they influence results. | P2 |
| GRP-004 | Invites expire and are revocable. | P2 |

## 5.13 Voice

| ID | Requirement | Pri |
|---|---|---|
| VOI-001 | Voice is an *input method*: speech becomes editable text that enters the same pipeline as typed text. | P0 |
| VOI-002 | Default: browser speech recognition where available, behind a `SpeechInput` abstraction. | P1 |
| VOI-003 | Fallback: `POST /voice/transcriptions` using the configured STT provider when browser support is missing. | P2 |
| VOI-004 | Audio is not stored by default; the transcript is shown for correction before send (configurable auto-send). | P0 |
| VOI-005 | Microphone permission and unsupported-browser states have explicit UI. | P1 |

---

# 6. Experience and UI Requirements

## 6.1 Routes and pages

| Route | Page | Auth | Pri |
|---|---|---|---|
| `/` | Home: value proposition, input (text + voice), mode picker, example prompts, recent sessions | guest/any | P0 |
| `/d/:sessionId` | Discovery Workspace (mode-aware) | owner | P0 |
| `/history` | History: searchable session list, run timelines | owner | P1 |
| `/saved` | Saved items, notes, tags | owner | P1 |
| `/reports` | Reports list | owner | P1 |
| `/reports/:reportId` | Report viewer/editor + export | owner | P1 |
| `/compare` | Compare/Trends explorer (direct endpoints) | any | P2 |
| `/settings` | Settings, privacy, data export, deletion | any | P1 |
| `/s/:token` | Public shared page | public | P1 |
| `/join/:token` | Group invite contribution page | public | P2 |
| `/auth/*` | Sign-in/up handled by the identity provider flow | public | P1 |
| `*` | Not-found and error pages | any | P0 |

**UX-001 (P0)** The active session survives navigation and refresh: the workspace restores from the server (`GET /discovery/sessions/{id}`), reattaching to a running run via `GET /discovery/runs/{id}/events`.

## 6.2 Workspace layout

**UX-010 (P0)** Desktop uses a three-region layout: **Conversation** (left), **Results** (center/primary), **Context & Timeline** (right, collapsible). Mobile uses a single column with a bottom sheet for Context/Timeline and tabs for Chat / Results.  
**UX-011 (P0)** The input bar is always reachable and supports text, voice, and refinement chips.  
**UX-012 (P0)** Follow-up questions render as a clear question card with quick-reply options plus free text; answering resumes the run.  
**UX-013 (P0)** Empty, loading, partial, error, and limited-results states are designed for every region (no blank screens).

## 6.3 Agent Timeline

**UX-020 (P0)** A visible **Agent Timeline** renders run events live: phase headers, tool steps with user-safe labels ("Looking up *Dune*…"), durations, success/failure markers, and the questions asked.  
**UX-021 (P0)** Timeline steps for Qloo calls show a **Qloo badge** and what was asked in plain language (never raw parameters).  
**UX-022 (P1)** The timeline collapses to a one-line status once the run completes and can be re-expanded; past runs are viewable from History.  
**UX-023 (P1)** The timeline shows the **state summary** evolving: resolved entities, constraints, assumptions made.  
**UX-024 (P0)** On failure or timeout the timeline shows what completed, what failed, and offers Retry / Continue with partial results.  
**UX-025 (P1)** `prefers-reduced-motion` is honored; streaming text and timeline animations degrade gracefully.

## 6.4 Streaming experience

**UX-030 (P0)** Responses stream progressively: status → question or partial results → streaming explanation → final structured results.  
**UX-031 (P0)** Reconnection is automatic and invisible (resume by `Last-Event-ID`); persistent failure shows a recoverable message.  
**UX-032 (P1)** Users can cancel a running discovery at any time.

## 6.5 Result presentation (all modes)

| ID | Requirement | Pri |
|---|---|---|
| UX-040 | **Result card**: image, title, kind badge, one-line "why", match strength (RES-003), provenance badge (Qloo / Web / Agent), actions. | P0 |
| UX-041 | **Detail drawer**: full explanation with evidence fragments styled differently from interpretation, source links, retrieval time, similar results. | P0 |
| UX-042 | **Influence view**: which of the user's inputs drove this result (chips with weights where provided). | P1 |
| UX-043 | **Sections**: results grouped (RES-004) with collapsible headers and counts. | P1 |
| UX-044 | **Lenses**: tab/filter by kind (Movies, Music, Places, Brands…) when results are cross-domain. | P1 |
| UX-045 | **Map view** for place results with list/map sync. | P1 |
| UX-046 | **Compare tray**: pin up to 4 results; side-by-side attributes and shared/unique affinities. | P1 |
| UX-047 | **Layouts**: grid, list, and (for ranked sets) a "top picks" hero treatment. | P1 |
| UX-048 | **Limitations banner** when results are thin, approximate, or unverified. | P0 |
| UX-049 | **Skeletons and progressive rendering** from `result.partial` events. | P1 |
| UX-050 | Actions: save, like/dislike, exclude, more-like-this, share, add-to-report. | P0 |

## 6.6 Mode-specific UI

**Self — "Taste Canvas"** (UX-060..063)  
P0: input → results with sections. P1: editable taste chips (entities, tags, dislikes); cross-domain lens tabs; "Because you liked…" clusters; influence view.

**Someone else — "Gift Brief"** (UX-064..067)  
P0: recipient/occasion/budget summary strip (editable). P1: results grouped *Experiences / Things / Media*; budget badges with "price verified/unverified"; shortlist and compare tray; share the shortlist as a page (SHR-001).

**Group — "Group Board"** (UX-068..072)  
P1: participant roster with per-person taste chips; add/remove participants; blend-strategy toggle (consensus / balanced / variety); per-result **fit meter per participant**; "shared vs unique signals" panel. P2: invite link manager showing pending/accepted contributions.

**Community — "Community Landscape"** (UX-073..076)  
P0: context header (community, place, goal) and limitations/uncertainty callout. P1: audience affinity categories, map/heat view, experience ideas grouped by theme, "what we don't know" panel.

**Business — "Business Workspace"** (UX-077..082)  
P1: **Brief builder** (objective, category, audience, market, competitors) that doubles as the agent's context; **Insights dashboard** (market overview, audience affinities, adjacent categories); **Opportunity cards** each labelled *Observed* or *Interpreted*; **Evidence panel** per card; **Report builder** (§6.7). P2: **Compare** panel (markets/audiences/brands), **Trends** panel with time-window controls, **map/heatmap** for location planning.

**UX-083 (P0)** Mode-specific views are composed from shared components (`ResultCard`, `EvidenceList`, `Timeline`, `ContextChips`, `MapView`, `ComparePanel`); a new mode must not require a new design system.

## 6.7 Reports and sharing UI

**UX-090 (P1)** Report viewer shows structured sections, tables, charts, evidence appendix, limitations, and a data-as-of stamp, with an **Export** menu (PDF / Markdown / CSV / JSON / HTML).  
**UX-091 (P2)** In-place section editing, reordering, and regeneration of a section with streaming progress.  
**UX-092 (P1)** **Share dialog**: scope (result / set / report / saved), redaction toggles (SHR-005), expiry, download permission, copy link, revoke.  
**UX-093 (P1)** **Public share page** (`/s/:token`): clean read-only layout, Discover and Qloo attribution, "Try Discover" call to action, no private data.  
**UX-094 (P0)** Print stylesheet produces a clean printable report even if server PDF generation is unavailable.

## 6.8 Design system, accessibility, responsiveness

**UX-100 (P0)** Responsive from 360px; touch targets ≥ 44px; works on mobile and desktop.  
**UX-101 (P0)** WCAG 2.1 AA targets: keyboard operable, visible focus, ARIA live regions for streaming status, sufficient contrast, alt text for images.  
**UX-102 (P1)** Light and dark themes with a defined token set.  
**UX-103 (P0)** A single design-token and component library underpins every page (typography, spacing, color, elevation, motion).  
**UX-104 (P1)** Internationalization-ready: strings externalized; currency and number formatting via `Intl`; right-to-left not required for v1 but must not be precluded.  
**UX-105 (P0)** The UI visibly marks **demo/mock data** whenever the backend runs a non-`live` profile (§11) so synthetic content is never mistaken for real Qloo output.

---

# 7. Canonical API

Detailed schemas and examples live in `docs/08-api/api-contract.md`. **This section is the endpoint authority.**

## 7.1 Conventions

| Item | Rule |
|---|---|
| Base path | `/api/v1` (health endpoints unversioned at `/health`, `/ready`) |
| Format | JSON, `snake_case` fields, ISO-8601 UTC timestamps, UUID identifiers |
| Auth | `Authorization: Bearer <token>`; guest tokens and account tokens are both bearer JWTs (ADR-007). Public endpoints under `/public/*` need no auth. |
| Streaming | SSE (`text/event-stream`) over `fetch` (POST), not browser `EventSource` (ADR-006) |
| Idempotency | `Idempotency-Key` header supported on `POST /discovery/sessions/{id}/messages`, `POST /reports`, `POST /shares` |
| Pagination | Cursor-based: `?limit=&cursor=`; responses return `next_cursor` |
| Versioning | Additive changes only within `v1`: new fields and event types are allowed, clients ignore unknown ones |
| Correlation | `X-Request-ID` echoed on every response and included in error bodies |
| Rate limits | `429` with `Retry-After`; limits per identity and per IP (§9.2) |
| Money | `{ "amount": 100000, "currency": "NGN" }` (integer minor-unit-safe decimals as strings if needed) |

## 7.2 Error model

~~~json
{
  "error": {
    "code": "validation_error",
    "message": "Human-readable summary",
    "details": [],
    "request_id": "req_...",
    "retryable": false
  }
}
~~~

| HTTP | `code` examples |
|---|---|
| 400 | `validation_error`, `invalid_action` |
| 401 | `unauthenticated`, `token_expired` |
| 403 | `forbidden` |
| 404 | `not_found` (also returned for other users' resources) |
| 409 | `state_conflict`, `run_in_progress`, `idempotency_conflict` |
| 410 | `share_revoked`, `share_expired` |
| 413 | `payload_too_large` |
| 422 | `unprocessable_input` |
| 429 | `rate_limited`, `quota_exceeded` |
| 502/503 | `upstream_unavailable` (Qloo/LLM/search), `service_unavailable` |
| 504 | `upstream_timeout` |

Errors that occur *during* a stream are delivered as a `run.failed` event (§7.6), not as an HTTP error.

## 7.3 Endpoint table (authoritative)

### Platform
| Method | Path | Purpose | Pri |
|---|---|---|---|
| GET | `/health` | Liveness | P0 |
| GET | `/ready` | Readiness (DB, config; provider status in non-prod) | P0 |
| GET | `/api/v1/meta` | Capabilities: modes, intents, result kinds, feature flags, limits, active profile, provider health | P0 |

### Identity
| Method | Path | Purpose | Pri |
|---|---|---|---|
| POST | `/api/v1/auth/guest` | Create guest identity and token | P0 |
| POST | `/api/v1/auth/claim` | Merge guest data into authenticated account | P1 |
| GET | `/api/v1/me` | Current identity (guest or account) | P0 |
| PATCH | `/api/v1/me` | Update profile fields | P1 |
| GET / PUT | `/api/v1/me/preferences` | Read/replace preferences and settings | P1 |
| GET | `/api/v1/me/export` | Export all of the user's data | P1 |
| DELETE | `/api/v1/me` | Delete account and data | P1 |

### Discovery sessions, messages, runs
| Method | Path | Purpose | Pri |
|---|---|---|---|
| POST | `/api/v1/discovery/sessions` | Create session (optional `mode`, `intent`, `title`, `initial_message`) | P0 |
| GET | `/api/v1/discovery/sessions` | List/search sessions (`status`, `mode`, `q`, cursor) — this **replaces** any `/history` endpoint | P1 |
| GET | `/api/v1/discovery/sessions/{id}` | Session with state summary, latest results, active run | P0 |
| PATCH | `/api/v1/discovery/sessions/{id}` | Rename, archive, change mode/intent | P1 |
| DELETE | `/api/v1/discovery/sessions/{id}` | Soft-delete | P1 |
| POST | `/api/v1/discovery/sessions/{id}/messages` | Submit a message and/or structured `action`; starts a run. SSE if `Accept: text/event-stream`, otherwise JSON/202 | P0 |
| GET | `/api/v1/discovery/sessions/{id}/messages` | Conversation messages | P0 |
| GET | `/api/v1/discovery/sessions/{id}/runs` | Runs for a session | P1 |
| GET | `/api/v1/discovery/runs/{run_id}` | Run status and summary | P0 |
| GET | `/api/v1/discovery/runs/{run_id}/events` | Replay/resume event stream (`Last-Event-ID`); JSON timeline when `Accept: application/json` | P0 |
| POST | `/api/v1/discovery/runs/{run_id}/cancel` | Cancel a running run | P1 |
| GET | `/api/v1/discovery/sessions/{id}/state` | Durable state summary | P1 |

### Group participants and invites
| Method | Path | Purpose | Pri |
|---|---|---|---|
| GET / POST | `/api/v1/discovery/sessions/{id}/participants` | List/add participants | P1 |
| PATCH / DELETE | `/api/v1/discovery/sessions/{id}/participants/{pid}` | Edit/remove | P1 |
| POST | `/api/v1/discovery/sessions/{id}/invites` | Create invite link | P2 |
| GET | `/api/v1/discovery/sessions/{id}/invites` | List invites and pending contributions | P2 |
| POST | `/api/v1/discovery/sessions/{id}/contributions/{cid}/accept` | Accept/reject contribution (`/reject`) | P2 |
| DELETE | `/api/v1/discovery/sessions/{id}/invites/{iid}` | Revoke invite | P2 |
| GET | `/api/v1/public/invites/{token}` | Invite landing data (public) | P2 |
| POST | `/api/v1/public/invites/{token}/contributions` | Submit taste input (public, rate-limited) | P2 |

### Results and feedback
| Method | Path | Purpose | Pri |
|---|---|---|---|
| GET | `/api/v1/discovery/sessions/{id}/results` | Results for a session (filter by run, kind, group) | P0 |
| GET | `/api/v1/results/{result_id}` | Single result with full evidence | P0 |
| PUT | `/api/v1/results/{result_id}/feedback` | Set feedback (`like`, `dislike`, `not_relevant`, `already_know`) | P0 |
| DELETE | `/api/v1/results/{result_id}/feedback` | Clear feedback | P0 |

### Direct analysis (non-conversational)
| Method | Path | Purpose | Pri |
|---|---|---|---|
| POST | `/api/v1/analysis/compare` | Compare subjects (SSE-capable) | P2 |
| POST | `/api/v1/analysis/trends` | Trend query (SSE-capable) | P2 |

### Saved
| Method | Path | Purpose | Pri |
|---|---|---|---|
| POST | `/api/v1/saved` | Save a result or session | P1 |
| GET | `/api/v1/saved` | List/filter by tag/kind | P1 |
| GET / PATCH / DELETE | `/api/v1/saved/{id}` | Read, edit note/tags, remove | P1 |

### Reports and export
| Method | Path | Purpose | Pri |
|---|---|---|---|
| POST | `/api/v1/reports` | Create report from a session + template (returns `202`; SSE-capable) | P1 |
| GET | `/api/v1/reports` | List reports | P1 |
| GET | `/api/v1/reports/{id}` | Report document and status | P1 |
| PATCH | `/api/v1/reports/{id}` | Edit title/sections | P2 |
| DELETE | `/api/v1/reports/{id}` | Delete | P1 |
| GET | `/api/v1/reports/{id}/events` | Generation event stream | P2 |
| GET | `/api/v1/reports/{id}/export?format=pdf\|md\|csv\|json\|html` | Download export | P1 |

### Sharing
| Method | Path | Purpose | Pri |
|---|---|---|---|
| POST | `/api/v1/shares` | Create snapshot share (`target_type`, `target_id`, redaction, expiry, `allow_download`) | P1 |
| GET | `/api/v1/shares` | List my shares (with aggregate view counts) | P1 |
| PATCH | `/api/v1/shares/{id}` | Update expiry/download permission | P2 |
| DELETE | `/api/v1/shares/{id}` | Revoke | P1 |
| GET | `/api/v1/public/shares/{token}` | Public snapshot (no auth) | P1 |
| GET | `/api/v1/public/shares/{token}/export?format=` | Public export if permitted | P2 |

### Voice
| Method | Path | Purpose | Pri |
|---|---|---|---|
| POST | `/api/v1/voice/transcriptions` | Fallback speech-to-text (multipart audio → text) | P2 |

## 7.4 Message request

~~~json
{
  "message": "Help me find a birthday experience for my sister in Lagos under ₦100,000",
  "mode": "someone_else",
  "intent": "recommend",
  "input_type": "text",
  "action": null,
  "client_context": { "locale": "en-NG", "timezone": "Africa/Lagos" }
}
~~~

`action` (optional, structured; may accompany or replace `message`):

~~~json
{ "type": "more_like_this", "result_id": "..." }
{ "type": "exclude_result", "result_id": "..." }
{ "type": "update_constraint", "constraint": { "budget": { "amount": 80000, "currency": "NGN" } } }
{ "type": "answer_question", "question_id": "...", "answer": "..." }
~~~

**API-001 (P0)** One user message starts at most one run per session at a time; a second submission while a run is `running` returns `409 run_in_progress` unless it is an `answer_question` for a `needs_input` run.  
**API-002 (P0)** `mode` and `intent` are optional on every message; supplying them overrides inference and updates session state.

## 7.5 Non-streaming behavior

`Accept: application/json` → the server waits up to `RUN_SYNC_WAIT_SECONDS` (default 25). If the run completes, `200` with the final `RunResult`. Otherwise `202 Accepted` with `{ "run_id", "status", "events_url", "poll_url" }`.

## 7.6 SSE protocol

Response headers: `Content-Type: text/event-stream`, `Cache-Control: no-cache, no-transform`, `X-Accel-Buffering: no`.  
Each event:

~~~text
id: <run_id>:<seq>
event: <type>
data: {"v":1,"run_id":"...","seq":12,"ts":"2026-10-01T10:00:00Z","type":"tool.completed","data":{...}}
~~~

| Event `type` | `data` (summary) | Pri |
|---|---|---|
| `run.started` | `run_id`, `session_id`, `mode`, `intent` | P0 |
| `phase.changed` | `phase`, `label` | P0 |
| `state.updated` | user-safe state summary (entities, constraints, assumptions) | P1 |
| `tool.started` | `tool`, `label`, `step`, `provider` | P0 |
| `tool.completed` | `tool`, `label`, `duration_ms`, `summary` (e.g. counts) | P0 |
| `tool.failed` | `tool`, `label`, `error_code`, `retryable` | P0 |
| `question` | `question_id`, `text`, `options[]` | P0 |
| `result.partial` | one or more normalized results | P1 |
| `response.delta` | `text` token chunk of the user-facing explanation | P1 |
| `result.set` | final normalized results, groups, limitations | P0 |
| `run.completed` | `status`, `usage` summary (steps, durations) | P0 |
| `run.failed` | `error_code`, `message`, `recoverable`, `resume_hint` | P0 |
| `run.cancelled` | — | P1 |
| `heartbeat` | `ts` | P0 |
| `report.section` / `report.completed` | report generation progress | P2 |

**API-010 (P0)** `question` ends with the run in `needs_input`; the stream closes after emitting it. The client resumes by posting an `answer_question` action, which opens a new stream for the continuation run.  
**API-011 (P0)** Exactly one terminal event (`run.completed`, `run.failed`, `run.cancelled`, or `question`) closes every stream.  
**API-012 (P0)** Replaying `GET /discovery/runs/{id}/events` with `Last-Event-ID: <run_id>:<seq>` returns all later events, then continues live if the run is still active.

---

# 8. Canonical Data Model

Table-level detail lives in `docs/04-database/database-architecture.md`. Entities, enums, and relationships below are authoritative.

## 8.1 Entities

| Entity (table) | Purpose | Key fields |
|---|---|---|
| `users` | Guest or account identity | `id`, `is_guest`, `external_auth_id?`, `email?`, `display_name?`, `created_at`, `last_seen_at`, `deleted_at?` |
| `user_preferences` | Settings | `user_id`, `default_location`, `currency`, `language`, `theme`, `memory_enabled`, `extra JSONB` |
| `discovery_sessions` | Workspace | `id`, `user_id`, `mode`, `intent`, `title`, `status`, `created_at`, `updated_at` |
| `discovery_participants` | People in a session | `id`, `session_id`, `role` (`self`, `recipient`, `member`), `display_name`, `source` (`user`, `invite`), `profile JSONB` |
| `discovery_messages` | Conversation | `id`, `session_id`, `run_id?`, `role`, `content`, `input_type`, `seq`, `created_at` |
| `discovery_states` | Durable agent state | `session_id`, `state_version`, `state JSONB`, `schema_version`, `updated_at` |
| `discovery_runs` | One agent execution | `id`, `session_id`, `status`, `phase`, `mode`, `intent`, `started_at`, `ended_at`, `usage JSONB`, `error_code?`, `idempotency_key?` |
| `run_events` | Persisted SSE events | `run_id`, `seq`, `type`, `data JSONB`, `ts`; PK (`run_id`,`seq`) |
| `discovery_results` | Normalized results | `id`, `session_id`, `run_id`, `kind`, `rank`, `group_key?`, `title`, `payload JSONB`, `explanation JSONB`, `source JSONB`, `schema_version` |
| `discovery_queries` | Audit of provider calls | `id`, `run_id`, `provider`, `operation`, `request_summary JSONB`, `status`, `duration_ms`, `cache_hit` |
| `result_feedback` | Per-result feedback | `result_id`, `user_id`, `value`, `created_at` (unique per user+result) |
| `saved_items` | Saved results/sessions | `id`, `user_id`, `target_type`, `target_id`, `snapshot JSONB`, `note`, `tags TEXT[]` |
| `reports` | Report documents | `id`, `user_id`, `session_id`, `template`, `status`, `document JSONB`, `schema_version`, `generated_at` |
| `share_links` | Public snapshots | `id`, `user_id`, `token_hash`, `target_type`, `snapshot JSONB`, `redaction JSONB`, `allow_download`, `status`, `expires_at?`, `view_count`, `created_at`, `revoked_at?` |
| `group_invites` | Contribution links | `id`, `session_id`, `token_hash`, `status`, `expires_at`, `max_contributions` |
| `group_contributions` | Invitee input | `id`, `invite_id`, `display_name`, `payload JSONB`, `status` (`pending`, `accepted`, `rejected`), `created_at` |

## 8.2 Rules

**DAT-001 (P0)** Flexible, evolving structures (state, results, reports, event data) are JSONB with a `schema_version`; stable relational keys remain columns.  
**DAT-002 (P0)** Every user-owned table is filtered by `user_id` (directly or via session) in the repository layer; no unscoped queries.  
**DAT-003 (P0)** Deletion: session delete is a soft-delete followed by hard purge after `SOFT_DELETE_PURGE_DAYS`; account deletion purges all user data and revokes all shares.  
**DAT-004 (P0)** Share `snapshot` is self-contained (§5.11) and independent of live rows.  
**DAT-005 (P1)** Retention jobs: `run_events` (STR-010), guest users (ACC-007), expired shares/invites.  
**DAT-006 (P0)** Migrations via Alembic; every schema change ships with a migration and no destructive change without a data plan.  
**DAT-007 (P0)** Never store: raw provider payloads containing keys or tokens, hidden LLM reasoning, voice audio, payment or government identifiers, or the sensitive attributes listed in PRIV-005.

## 8.3 `DiscoveryResult` (normalized)

~~~json
{
  "id": "res_...",
  "schema_version": 1,
  "kind": "place",
  "title": "…",
  "subtitle": "…",
  "description": "…",
  "image_url": "https://…",
  "rank": 1,
  "group": { "key": "because_you_liked", "label": "Because you liked …" },
  "strength": { "value": 0.82, "basis": "provider", "label": "Strong match" },
  "facts": [{ "label": "Area", "value": "…" }],
  "location": { "lat": 0.0, "lng": 0.0, "address": "…" },
  "price": { "amount": 25000, "currency": "NGN", "verified": true, "retrieved_at": "…" },
  "links": [{ "label": "Website", "url": "https://…" }],
  "source": { "provider": "qloo", "entity_id": "…", "retrieved_at": "…" },
  "explanation": {
    "summary": "…",
    "fragments": [
      { "basis": "evidence", "text": "…", "signals": ["ent_1", "ent_2"] },
      { "basis": "user_context", "text": "…" },
      { "basis": "interpretation", "text": "…" }
    ],
    "limitations": ["…"]
  },
  "payload": {}
}
~~~

`strength.basis` is `provider` or `derived`; `value` may be null. `payload` carries kind-specific data (comparison tables, trend series, audience breakdowns, opportunity details).

## 8.4 `DiscoveryState` (durable)

Top-level keys (detailed Pydantic models in the state document): `schema_version`, `request`, `subject`, `participants`, `preferences`, `constraints`, `location`, `audience`, `intent`, `resolved_entities`, `missing_information`, `asked_questions`, `assumptions`, `refinement`, `feedback_adjustments`, `execution` (durable subset only).

**DAT-010 (P0)** State updates use optimistic versioning (`state_version`); a concurrent conflict raises `state_conflict` and is retried once.

## 8.5 `ReportDocument`

~~~json
{
  "schema_version": 1,
  "template": "business_market",
  "title": "…",
  "generated_at": "…",
  "data_as_of": "…",
  "summary": "…",
  "sections": [
    { "id": "overview", "title": "…", "blocks": [
      { "type": "paragraph", "basis": "interpretation", "text": "…" },
      { "type": "table", "columns": [], "rows": [] },
      { "type": "chart", "chart_type": "bar", "series": [] },
      { "type": "result_list", "result_ids": [] },
      { "type": "evidence_list", "items": [] }
    ]}
  ],
  "limitations": ["…"],
  "methodology": "…",
  "sources": [{ "provider": "qloo", "retrieved_at": "…" }]
}
~~~

**RPT-020 (P1)** Report templates are declarative (`ReportTemplateRegistry`): ordered sections, required inputs, and block generators. A new template does not change the renderer.  
**RPT-021 (P1)** Renderers (`html`, `md`, `csv`, `json`, `pdf`) consume only `ReportDocument`.

---

# 9. Backend Requirements

## 9.1 Structure and conventions

| ID | Requirement | Pri |
|---|---|---|
| BKD-001 | Python + FastAPI (async), Pydantic v2 models, SQLAlchemy 2.x async, Alembic. | P0 |
| BKD-002 | Layering: `api` (routes/schemas) → `services` (use cases) → `agent` (loop, tools) → `integrations` (Qloo, LLM, search, STT adapters) → `repositories` (persistence). No upward imports. | P0 |
| BKD-003 | All external providers sit behind interfaces with `mock`, `record`, `replay`, `live` implementations (§11). | P0 |
| BKD-004 | Registries (declarative, import-time validated): `ModeRegistry`, `IntentRegistry`, `ResultKindRegistry`, `ToolRegistry`, `ReportTemplateRegistry`, `ExportRendererRegistry`. | P0 |
| BKD-005 | The run executor is an in-process async task manager with a persisted event log; it must tolerate process restart by marking orphaned runs `failed(recoverable)` at startup. | P0 |
| BKD-006 | Structured logging with `request_id` and `run_id`; no secrets or prompt bodies in logs. | P0 |
| BKD-007 | Dependency injection for providers, clock, and ID generation (testability). | P0 |
| BKD-008 | Typed settings via environment variables; fail fast on missing required config for the active profile. | P0 |

## 9.2 Limits and configuration (defaults, all overridable by env)

| Variable | Default | Purpose |
|---|---|---|
| `DISCOVER_PROFILE` | `mock` | Master profile: `mock`, `record`, `replay`, `live` (§11) |
| `QLOO_MODE`, `LLM_MODE`, `SEARCH_MODE`, `STT_MODE` | inherit profile | Per-provider override |
| `QLOO_API_KEY`, `QLOO_BASE_URL` | — | Qloo access |
| `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` | — | OpenAI-compatible endpoint (ADR-008) |
| `SEARCH_PROVIDER`, `SEARCH_API_KEY` | — | Current-information source (ADR-013) |
| `STT_PROVIDER`, `STT_API_KEY` | — | Optional fallback transcription |
| `DATABASE_URL` | — | Postgres |
| `AUTH_JWKS_URL`, `AUTH_ISSUER`, `AUTH_AUDIENCE` | — | Account token verification (ADR-007) |
| `GUEST_JWT_SECRET` | — | Signing of guest tokens |
| `CORS_ALLOWED_ORIGINS` | — | Frontend origins |
| `AGENT_MAX_STEPS` | 8 | AGT-002 |
| `AGENT_MAX_AUTO_REFINEMENTS` | 2 | AGT-007 |
| `RUN_TOTAL_TIMEOUT_SECONDS` | 90 | Whole-run budget |
| `TOOL_TIMEOUT_SECONDS` | 20 | Per-tool cap |
| `LLM_TIMEOUT_SECONDS` | 30 | Per-LLM-call cap |
| `RUN_SYNC_WAIT_SECONDS` | 25 | STR-004 |
| `SSE_HEARTBEAT_SECONDS` | 15 | STR-006 |
| `RUN_EVENT_RETENTION_DAYS` | 30 | STR-010 |
| `GUEST_RETENTION_DAYS` | 30 | ACC-007 |
| `SOFT_DELETE_PURGE_DAYS` | 14 | DAT-003 |
| `RATE_LIMIT_MESSAGES_PER_HOUR` | 60 | Per identity |
| `RATE_LIMIT_PUBLIC_PER_MINUTE` | 30 | Public share/invite endpoints |
| `MAX_MESSAGE_CHARS` | 4000 | Input bound |
| `MAX_PARTICIPANTS` | 12 | Group size |
| `EXPORT_MAX_SECONDS` / `EXPORT_MAX_MB` | 30 / 25 | RPT-009 |
| `QLOO_CACHE_TTL_SECONDS` | 3600 | QLO-006 |
| `FEATURE_FLAGS` | — | Comma list to toggle P2 features per deployment |

**BKD-010 (P0)** A committed `.env.example` documents every variable; `mock` profile runs with **no** external keys.

---

# 10. Non-Functional Requirements

## 10.1 Performance

| ID | Target | Pri |
|---|---|---|
| NFR-001 | First SSE event within 1s of request receipt (excluding cold start). | P0 |
| NFR-002 | First visible progress within 2s; first partial result within 15s typical; total typical run ≤ 30s; hard cap per §9.2. | P1 |
| NFR-003 | Non-agent endpoints p95 < 300ms excluding provider calls. | P1 |
| NFR-004 | Frontend initial JS ≤ 250KB gzipped for Home; workspace code-split. | P1 |
| NFR-005 | Cold-start mitigation: a lightweight keep-warm ping and a "waking up the server" UI state. | P1 |

## 10.2 Security and privacy

| ID | Requirement | Pri |
|---|---|---|
| SEC-001 | Provider keys server-side only; never in the frontend bundle, logs, events, or reports. | P0 |
| SEC-002 | Input validation on every endpoint (Pydantic) with size limits. | P0 |
| SEC-003 | CORS restricted to configured origins; HTTPS only in production. | P0 |
| SEC-004 | Rate limiting and per-identity quotas (including public endpoints). | P0 |
| SEC-005 | Prompt-injection defenses (AGT-011): provider/user-contributed text is delimited and never granted instruction authority; tool arguments are validated against schemas. | P0 |
| SEC-006 | Share/invite tokens: ≥128-bit random, stored hashed, constant-time comparison. | P0 |
| SEC-007 | Public pages send `noindex`, `Referrer-Policy: no-referrer`, and strict CSP. | P0 |
| SEC-008 | Output rendering escapes all provider/LLM text (no raw HTML from providers). | P0 |
| SEC-009 | Dependency and secret scanning in CI. | P1 |
| PRIV-001 | Privacy notice and clear disclosure that inputs are sent to Qloo, the LLM provider, and the search provider. | P0 |
| PRIV-002 | Users can delete sessions, saved items, shares, and their account; data export available (ACC-006). | P1 |
| PRIV-003 | Shares never include the conversation; names and prompts hidden by default (SHR-005). | P0 |
| PRIV-004 | Voice audio not stored (VOI-004). | P0 |
| PRIV-005 | The product does not request, infer, or store sensitive personal attributes (health, religion, sexual orientation, precise home address, government IDs). If a user volunteers them, they are used transiently for the run only if relevant and not persisted in state beyond the session. | P0 |
| PRIV-006 | Group participants are described by display names the user chooses; invitee data is deleted with the session. | P1 |

## 10.3 Reliability and observability

| ID | Requirement | Pri |
|---|---|---|
| REL-001 | Provider failures degrade gracefully with partial results and clear messaging. | P0 |
| REL-002 | Every run ends in a terminal state; startup recovery handles orphaned runs (BKD-005). | P0 |
| REL-003 | Health/readiness endpoints; structured logs; request and run IDs. | P0 |
| REL-004 | Metrics (counts, latency, provider errors, token usage) exposed to logs at minimum; dashboard optional. | P1 |
| REL-005 | Idempotent submission prevents duplicate runs on retries. | P1 |

## 10.3a Error handling

| ID | Requirement | Pri |
|---|---|---|
| ERR-001 | Gracefully handle: invalid input, missing information, LLM failures, Qloo failures, search failures, database failures, timeouts, rate limits, invalid tool arguments, tool execution failures, and no-result situations. | P0 |
| ERR-002 | Users receive a useful, plain-language explanation and a next step (retry, adjust, continue with partial results), never a stack trace or internal identifier beyond a support `request_id`. | P0 |
| ERR-003 | Error classes map to the API vocabulary in §7.2 and to `run.failed` events with a `recoverable` flag. | P0 |

## 10.3b Containers

| ID | Requirement | Pri |
|---|---|---|
| CNT-001 | Backend is containerized from `python:3.12-slim` (not Alpine, to avoid dependency compatibility problems). | P0 |
| CNT-002 | Production image installs only required dependencies, runs as a non-root user where practical, serves via Uvicorn, and takes configuration only from environment variables. | P0 |

## 10.4 Accessibility, i18n, compatibility

See UX-100..105. Supported browsers: latest two versions of Chrome, Edge, Safari, Firefox; mobile Safari/Chrome.

---

# 11. Test and Delivery Profiles

The project has **no Qloo API key at this stage**. Development must proceed fully without it, then switch to real calls with minimal rework.

## 11.1 Profiles

| Profile | Providers | Use |
|---|---|---|
| `mock` | Scripted LLM, fake Qloo, fake search, fake STT, local Postgres | Day-to-day development of all features; frontend work; demos of flow only (marked synthetic, UX-105) |
| `record` | Real providers; every call written (sanitized) to `fixtures/recorded/` | First session after keys arrive: capture real Qloo/LLM/search behavior |
| `replay` | Recorded fixtures served by adapters | CI and regression tests with real-shaped data |
| `live` | Real providers | Staging and production |

**TST-001 (P0)** The profile is chosen by `DISCOVER_PROFILE`; provider-level overrides are allowed (e.g., real LLM with mock Qloo).  
**TST-002 (P0)** In `mock`, the backend exposes the **same HTTP/SSE contract** as `live`; the frontend cannot tell the difference except via `/meta` and the mock banner.  
**TST-003 (P0)** `GET /meta` and every export/shared page flag synthetic content when the profile is not `live`.  
**TST-004 (P0)** Production startup refuses `mock` unless `ALLOW_DEMO_MODE=true`, in which case all output is labelled demo data.

## 11.2 Mock content packs

**TST-010 (P0)** A **scenario pack** per mode/intent provides deterministic scripted runs (events + results + explanations): at minimum `self`, `someone_else` (gift with budget), `group`, `community`, `business`, `compare`, `trend`, an ambiguous-entity clarification, a thin-results case, a provider failure, and a timeout.  
**TST-011 (P0)** Scenario selection is deterministic from the user message keywords or an explicit `X-Mock-Scenario` header (non-production).  
**TST-012 (P0)** Mock Qloo operates at the **normalized-model level** (output of the adapter), because the real Qloo wire shapes are unverified until `record`. Mock data must never be presented as Qloo output.

## 11.3 Keys-arrive plan

When the Qloo (and LLM/search) keys become available:

1. Set keys; run `DISCOVER_PROFILE=record` with the **spike checklist** (TST-020).
2. Review sanitized fixtures; commit them under `fixtures/recorded/`.
3. Write/adjust `normalizers` against the fixtures; adapter contract tests go green in `replay`.
4. Reconcile the Qloo doc with observed behavior; note deviations in an ADR.
5. Switch staging to `live`.

**TST-020 (P0) Spike checklist (record mode):** entity lookup for each supported kind; insights with explainability; location-filtered insights for the target demo locations (including Lagos and one control city); audience/demographic insight; compare; trends; error and empty-result behavior; rate-limit headers; supported entity-type list.  
**TST-021 (P0)** Fixtures are sanitized: keys, tokens, and personal identifiers stripped; fixture files are versioned with the date and API version recorded.

## 11.4 Test layers

| Layer | Scope | Profile |
|---|---|---|
| Unit | Pure logic: state reducers, normalizers, budget filters, registries, report renderers | none |
| Contract | Adapter interfaces against fixtures; API request/response schemas; SSE event schema | `mock`, `replay` |
| Agent | Scripted-LLM loop tests: asking, refining, limits, failure paths | `mock` |
| Integration | API + Postgres (+ SSE) | `mock` |
| E2E | Browser flows for each mode, streaming, share, report export | `mock` (CI), `live` (smoke) |
| Quality evals | A golden prompt set (≥ 15) with behavioral assertions (asks when it should, doesn't when it shouldn't, labels evidence correctly, respects budget/exclusions) | `live`/`replay` |
| Security | Access-control tests for every endpoint (ACC-008); share/invite token tests; injection tests | `mock` |
| Accessibility | Automated axe checks on key pages | `mock` |

**TST-030 (P0)** CI runs unit, contract, agent, integration, and security tests on every push in `mock`/`replay`; no external network is required.  
**TST-031 (P1)** A nightly or manual `live` smoke job runs when keys are configured.

---

# 12. Deployment Requirements

| ID | Requirement | Pri |
|---|---|---|
| DEP-001 | Frontend on a static/edge host (e.g., Vercel); backend as a container on a managed host (e.g., Render); managed Postgres. Exact vendors per ADR-016. | P0 |
| DEP-002 | Backend works as a single instance with persisted events; design must not preclude horizontal scale (event replay via DB). | P0 |
| DEP-003 | SSE works through the chosen host: buffering disabled, heartbeats on, idle timeouts verified in staging before demo. | P0 |
| DEP-004 | Docker Compose provides local Postgres + backend + frontend in `mock` with one command. | P0 |
| DEP-005 | CI/CD: lint, type-check, tests, build, and migration check on every PR; deploy from `main`. | P1 |
| DEP-006 | Environment separation: `local`, `staging`, `production` with distinct secrets. | P1 |
| DEP-007 | A README Quick Start: clone, `cp .env.example .env`, one command, working app in `mock`. | P0 |
| DEP-008 | Shared-page link previews require a server-rendered metadata route on the frontend host (ADR-011). | P2 |

---

# 13. Hackathon Compliance

| ID | Requirement | Pri |
|---|---|---|
| HCK-001 | Public repository, open-source license (MIT) visible. | P0 |
| HCK-002 | Meaningful Qloo integration; Qloo visible in the UI and in the demo narrative (timeline badges, evidence). | P0 |
| HCK-003 | Working hosted demo and a short demo video built from `live` data (not mock). | P0 |
| HCK-004 | Documentation of how Discover uses Qloo (links into `docs/07-qloo`). | P0 |
| HCK-005 | Qloo and any required third-party attributions/logos present. | P0 |
| HCK-006 | Submission artifacts prepared per the official rules; rules re-verified before submission. | P0 |

---

# 14. Delivery Plan (29 days: 1–30 Oct 2026)

Scope is fixed. The plan shows how all of it fits by working in parallel tracks, using the `mock` profile so no track waits on API keys.

## 14.1 Tracks

| Track | Content |
|---|---|
| **A. Platform & agent** | Config, DB, auth/guest, run executor, event log, agent loop, tool registry, state |
| **B. Integrations** | Adapter interfaces + mocks → real Qloo/LLM/search adapters on key arrival |
| **C. Streaming & API** | SSE, run/replay/cancel, REST endpoints, error model, rate limits |
| **D. Frontend core** | Design system, Home, Workspace, Timeline, results, history, saved, settings |
| **E. Modes & analysis** | Mode-specific UIs, group, community, business, compare/trends |
| **F. Reports & sharing** | ReportDocument, renderers, exports, share snapshots, public page |
| **G. Quality & submission** | Tests, accessibility, security review, deploy, demo video, submission |

## 14.2 Milestones

| Window | Milestone | Exit criteria |
|---|---|---|
| Days 1–3 | **M0 Foundations** | Repo scaffold, CI, Docker Compose, `.env.example`, `mock` profile boots, `/health`, `/meta`, DB migrations, guest auth |
| Days 3–8 | **M1 Walking skeleton** | Message → SSE run with scripted agent → results rendered with timeline, in `mock`; replay/resume works |
| Days 8–14 | **M2 Core journey** | Real agent loop with scripted/real LLM, state, questions, refinement, feedback, history, saved; `self` and `someone_else` UIs |
| Days 10–16 | **M3 Real providers** | Keys arrive → `record` spike → fixtures → normalizers → `replay` tests green → `live` smoke |
| Days 14–21 | **M4 All modes** | `group`, `community`, `business` UIs and flows; audience/location insights; current-info search; accounts + claim |
| Days 19–25 | **M5 Reports, share, analysis** | Reports + exports, share snapshots + public page, compare/trends, invite contributions |
| Days 24–28 | **M6 Hardening** | Security/access tests, accessibility pass, performance, SSE behavior on production host, copy and empty states |
| Days 28–30 | **M7 Submission** | Demo video from `live`, README, attribution, final rules check, submit with buffer |

If keys arrive late, M3 slides but M0–M2 and the P1/P2 UI tracks continue unaffected because they run on `mock`. **Lateness of keys is the single largest schedule risk (RSK-001).**

## 14.3 Definition of Ready / Done

**Ready (to start a feature):** requirement IDs identified; API/event contract exists in §7; mock scenario defined for it.  
**Done:** acceptance for each requirement ID verified by a test or a demo script; docs updated; accessibility check passed for UI; works in `mock` and (when keys exist) `live`; no TODOs referencing missing decisions.

---

# 15. Risks and Assumptions

| ID | Risk / assumption | Mitigation |
|---|---|---|
| RSK-001 | Qloo key unavailable until late. | `mock` profile; adapters isolated; spike checklist prepared (TST-020). |
| RSK-002 | Qloo coverage for Nigerian locations may be thin. | Location configurable (QLO-007); validate in `record`; choose demo locations with strong coverage; always state limitations (RES-009). Scope unaffected. |
| RSK-003 | Real Qloo wire formats differ from documented assumptions. | Normalizer layer + recorded fixtures (QLO-003, TST-012). |
| RSK-004 | LLM structured-decision reliability. | Native tool/JSON schema mode, one retry, safe failure (AGT-003); golden evals. |
| RSK-005 | SSE through hosting proxies / cold starts. | Heartbeats, resume (STR-003/006), staging verification (DEP-003), warm-up UI. |
| RSK-006 | Breadth of scope vs schedule. | Parallel tracks, registries and shared components (BKD-004, UX-083), priority tiers inside a fixed scope, feature flags for P2 in production. |
| RSK-007 | Report PDF generation memory/time. | Bounded export (RPT-009); print-stylesheet fallback (UX-094). |
| RSK-008 | Search provider cost/quota. | Cache; per-run caps; graceful degradation (INF-006). |
| RSK-009 | Abuse of public share/invite endpoints. | Rate limits, hashing, size caps, accept-before-influence (GRP-003). |
| ASM-001 | Hosting free tiers suffice for demo load. | Monitor; upgrade plan if needed. |
| ASM-002 | OpenAI-compatible LLM endpoint is available with tool-calling. | Adapter abstraction (ADR-008). |

---

# 16. Decision Register

Full rationale in `docs/01-decisions/decision-records.md`.

| ADR | Decision | Status |
|---|---|---|
| 001 | Custom, bounded agent orchestration (no heavy framework) | Accepted |
| 002 | Single Qloo adapter with normalization layer | Accepted |
| 003 | FastAPI + async Python backend | Accepted |
| 004 | PostgreSQL with JSONB for evolving structures | Accepted |
| 005 | Voice is input only; speech → editable text | Accepted |
| 006 | Streaming via SSE over `fetch`, detached runs, persisted events | Accepted |
| 007 | Guest-first identity; bearer JWTs; external IdP for accounts | Accepted (IdP vendor revisitable) |
| 008 | OpenAI-compatible LLM adapter with native tool-calling; model by env | Accepted |
| 009 | Mock/record/replay/live profiles | Accepted |
| 010 | Mode and intent taxonomy (5 modes × intents) | Accepted |
| 011 | Shareable pages as immutable snapshots with hashed tokens | Accepted |
| 012 | Reports as `ReportDocument` rendered to multiple formats | Accepted |
| 013 | Pluggable `SearchProvider` for current information | Accepted (provider pending) |
| 014 | Documentation governance: REQUIREMENTS.md is canonical | Accepted |
| 015 | Frontend: React + TypeScript + Vite, shared component system | Accepted |
| 016 | Hosting: static frontend host + container backend + managed Postgres | Accepted (vendors pending) |

## 16.1 Open items with defaults (proceed unless changed)

| Item | Default to proceed | Resolve by |
|---|---|---|
| LLM provider and model | Any OpenAI-compatible endpoint with tool-calling, set by env | Before M2 completes |
| Search provider | Tavily-class LLM-oriented search API behind `SearchProvider` | Before M4 |
| Identity provider | Managed IdP with JWKS (e.g., Supabase Auth) | Before M4 |
| STT fallback provider | Skip until VOI-003 is scheduled; browser STT first | M5 |
| Demo locations | Lagos plus one globally well-covered control city | After TST-020 |
| Hosting vendors | Vercel + Render + managed Postgres | M0 |

---

# 16a. Engineering Principles

1. **Qloo must matter.** It materially influences outcomes (PRD-001).
2. **Natural language first.** Users never learn APIs or filters (PRD-002).
3. **Agent, not chatbot.** Reason about missing information, use tools, iterate, finish multi-step tasks (PRD-003).
4. **Lightweight infrastructure.** Prefer hosted services and simple Python orchestration over heavyweight local infrastructure.
5. **Explicit state.** Maintain structured discovery state instead of relying on raw conversation history.
6. **Explainable discovery.** Explain results without inventing evidence (TAX-007).
7. **Cross-domain intelligence.** Use relationships between areas of taste and context (MOD-003).
8. **User control.** Users can refine, reject, save, share, or restart discoveries.
9. **Iterative development.** Requirements and architecture are living documents; implementation follows the current specification (§0.4).
10. **Don't over-engineer.** Introduce classes, services, abstractions, and dependencies only when they solve a real problem. Registries (BKD-004) exist for extensibility the scope already demands, not speculation.

---

# 17. Non-Goals

Discover does not: act as a general-purpose chatbot; store voice audio; make purchases, bookings, or payments; provide medical, legal, or financial advice; claim deterministic predictions of taste or markets; scrape sources contrary to their terms; or expose raw Qloo access to end users.

---

# 18. Requirements Status

| Area | Status |
|---|---|
| Product vision, taxonomy, modes | **Defined** |
| Functional requirements (§5) | **Defined** |
| UX and pages (§6) | **Defined**; visual designs to be produced during M0–M2 |
| API and streaming (§7) | **Defined**; schemas in `docs/08-api` |
| Data model (§8) | **Defined**; table detail in `docs/04-database` |
| Agent state and tools | **Defined** in `docs/06-discovery-modes` |
| Qloo adapter | **Defined as interface**; wire details pending `record` (TST-020) |
| Test profiles (§11) | **Defined** |
| Deployment (§12) | **Defined**; vendors per ADR-016 |
| Implementation | **Not started** — ready to begin at M0 |

---

# 19. Extension Rules (how this document stays extensible)

To add… | Do this
---|---
**A mode** | Add a row to §4.1; register in `ModeRegistry` (subject type, required context, prompt module, UI view); add scenario pack (TST-010); add UI view composed from shared components (UX-083); add ADR only if it changes taxonomy rules.
**An intent** | Add to §4.2; register in `IntentRegistry` with tool bindings; add `meta` capability flag; add scenarios.
**A result kind** | Add to §4.4a; register in `ResultKindRegistry` (Qloo URN mapping, payload schema, card variant); no table change (DAT-001).
**A tool** | Register in `ToolRegistry` (schema, timeout, user-safe label, tests) per AGT-012; list in §5.4.
**A provider** | Implement the adapter interface with all four profiles; add env vars in §9.2.
**A report template / export format** | Register in `ReportTemplateRegistry` / `ExportRendererRegistry` (RPT-020/021).
**An SSE event type** | Add to §7.6 (additive only); clients must ignore unknown types (STR-005).
**A requirement** | Use the next free ID in its area; mark priority; reference from affected docs.
**A breaking API change** | Requires a new `/api/v2`; never within `v1`.

Every change follows the Iteration Rule in §0.4.

---

*End of canonical requirements v1.0.*
