# Discover — Qloo Integration Specification

> **Alignment:** This is a detail document. The canonical requirements, enums (modes, intents, statuses, result kinds), API surface, and SSE protocol are in [`REQUIREMENTS.md`](../../REQUIREMENTS.md). If anything here conflicts with it, `REQUIREMENTS.md` wins and this document must be corrected. Decisions: [`docs/01-decisions/decision-records.md`](../01-decisions/decision-records.md). Qloo requirements: REQUIREMENTS §5.5; wire details are **unverified until the `record` spike** (TST-020, ADR-002, ADR-009).

**Status:** Draft — Version 0.1  
**Source of truth:** Qloo official API documentation  
**Primary endpoint:** GET https://api.qloo.com/v2/insights

## 1. Purpose

This document defines how Discover will use Qloo's APIs as a core cultural-intelligence layer.

Qloo's current API documentation describes the Insights API as supporting taste-driven recommendations, audience insights, analysis, and location-aware results. Its supporting Lookup APIs help Discover find valid entity IDs, audiences, and tags before those values are passed into Insights.

Architecture:

~~~text
Discovery Agent
      |
      v
Qloo Tools
      |
      v
Qloo Services
      |
      v
Qloo Adapter
      |
      +---- Lookup APIs
      |
      +---- Insights API
      |
      v
Qloo
~~~

## 2. Qloo API Surface Relevant to Discover

The official API overview currently groups Qloo functionality into:

### Insights API

Used for:
- Recommendation insights
- Demographic/audience insights
- Heatmaps
- Location-based insights
- Taste analysis

### Lookup APIs

Used for:
- Searching entities by name
- Searching entities by ID
- Searching audiences
- Listing audience types
- Searching tags
- Getting tag types

### Analysis & Trends APIs

Used for:
- Comparing groups of entities
- Trending data over time

The initial Discover MVP should prioritize **Lookup + Insights**. Analysis/Trends can be added when a product requirement justifies them.

## 3. Authentication

Qloo's API documentation shows the API key supplied through the X-Api-Key header.

The Qloo key must:
- Exist only on the backend.
- Be loaded from an environment variable.
- Never be sent to the browser.
- Never be committed to Git.
- Never be written into normal application logs.

Initial configuration:

~~~text
QLOO_API_KEY=<server-side secret>
QLOO_BASE_URL=https://api.qloo.com
~~~

## 4. Insights Endpoint

The current documented endpoint is:

~~~text
GET https://api.qloo.com/v2/insights
~~~

The endpoint requires filter.type, which determines the entity category returned. Qloo's documentation states that parameters must be selected according to the target entity type.

## 5. Core Qloo Concepts for Discover

### 5.1 Target entity type

The agent must determine what kind of thing it wants to discover.

Examples include:
- Place
- Movie
- TV show
- Music/artist-related entities
- Brand
- Destination
- Other Qloo-supported entity categories

The final supported entity-type enum must be taken from the current Qloo entity-type guide rather than hard-coded from old examples.

### 5.2 Interest signals

Qloo supports signal.interests.entities for entity IDs that influence affinity scoring. It also supports interest tags through signal.interests.tags. Entity signals can be weighted, and tag signals can also carry relative weights.

This is central to Discover's cross-domain concept.

Example conceptual request:

~~~text
Target:
    places

Signals:
    Taylor Swift
    Korean drama
    minimalist fashion
    coffee

Constraint:
    Lagos

Result:
    places whose Qloo affinity is influenced by those cultural signals
~~~

The agent does not send those natural-language strings directly unless the supported Qloo endpoint explicitly accepts them. It first resolves or transforms them into the appropriate Qloo parameters.

## 6. Entity Resolution

Qloo provides a Search Entities endpoint:

~~~text
GET https://api.qloo.com/search
~~~

The documented endpoint accepts a query and supports category/type, location, tags, rating, popularity, pagination, and sorting controls. Results can be used to obtain Qloo entity identifiers.

Discover should expose this through an internal tool:

~~~text
resolve_entity(
    name,
    entity_type?,
    location?
)
~~~

### Resolution flow

~~~text
Natural language
      |
      v
Entity Resolver
      |
      v
Qloo Search
      |
      v
Candidate entities
      |
      v
Confidence / ambiguity evaluation
      |
      +---- confident ----> resolved Qloo ID
      |
      +---- ambiguous ----> ask user
~~~

The agent should not silently choose a low-confidence entity when multiple candidates could materially change the discovery.

## 7. Entity Resolution Strategy

Resolution should consider:
1. Exact or near-exact name match.
2. Entity category.
3. Location when relevant.
4. Returned metadata.
5. User-provided context.
6. Ambiguity between multiple candidates.

Example:

> "I like The Office."

The agent should determine whether the user means the relevant TV entity before using it as an interest signal.

For place names, location context becomes particularly important.

## 8. Location Intelligence

Qloo supports location-aware Insights parameters.

The current documentation describes:
- filter.location
- filter.location.query
- filter.location.radius
- signal.location
- signal.location.query
- signal.location.radius

Location can be represented using coordinates, WKT geometry, or a Qloo locality entity depending on the parameter. The documentation also describes fuzzy locality-name resolution through filter.location.query and signal.location.query.

Discover should prefer a named locality query when the user supplies a normal place name and a Qloo-supported locality resolution is sufficient.

Example:

~~~text
User:
"Find restaurants in Lagos that fit my taste."

↓
filter.type = urn:entity:place
filter.location.query = Lagos
~~~

## 9. Filters vs Signals

Discover must distinguish between:

### Signals

Signals influence **affinity**.

Examples:
- User's favorite entities
- User's taste tags
- Audience signals
- Location signals

### Filters

Filters constrain **which results are eligible**.

Examples:
- Target entity type
- Location
- Price level
- Release year
- Content rating
- Exclusions

This distinction is important.

For example:

> "I like Taylor Swift and Korean dramas, and I want restaurants in Lagos under my budget."

The cultural interests should generally be represented as **signals**, while location and applicable price constraints should generally be represented as **filters**.

## 10. Explainability

Discover should enable Qloo's explainability feature whenever supported by the selected request.

Qloo documents:

~~~text
feature.explainability=true
~~~

When enabled, Qloo can return explainability metadata showing which input entities contributed to recommendations, including normalized influence information. It also provides aggregate explainability information for the result set.

This is especially valuable for Discover because the product promise includes:

> "Why did Discover recommend this?"

The application should prefer Qloo-provided explanation evidence over an LLM-generated explanation.

## 11. Result Count

Qloo documents take as the number of results returned, with a current maximum of 50 and a default of 20. Pagination is available through page.

Discover should not request the maximum by default.

Initial recommendation:

~~~text
Qloo request:
    take = 10–20

Application:
    evaluate returned results
    display a smaller curated set
~~~

The exact default should be established after performance testing.

## 12. Cross-Domain Discovery

Cross-domain discovery is a core Discover requirement.

Qloo's current documentation describes entity interest signals as influencing affinity for recommendations and explicitly supports cross-domain relevance through entity signals. It also documents cross-domain backfill controls.

Example:

~~~text
Input interests:
    Movie A
    Artist B
    Brand C

Target:
    Place

Qloo:
    target places influenced by those interests

Discover:
    evaluates and explains the resulting places
~~~

This is materially different from a simple same-category similarity search.

## 13. Tags

Qloo supports signal.interests.tags as another way to influence affinity. Tags may be supplied as IDs and, in POST requests, can include relative weights.

Discover should use tags when:
- The user expresses a broad taste that is better represented as a category.
- Entity resolution is too specific or unavailable.
- The Qloo tag provides useful cultural context.
- Multiple related interests need to be represented compactly.

The agent should not invent Qloo tag IDs. Tags must be resolved through supported Qloo lookup capabilities.

## 14. Query Construction Pipeline

The Qloo query builder should receive structured state rather than raw conversation.

Conceptually:

~~~text
DiscoveryState
      |
      v
Target Resolver
      |
      +--> target entity type
      |
      +--> resolved interests
      |
      +--> tags
      |
      +--> location
      |
      +--> hard constraints
      |
      v
Qloo Query Builder
      |
      v
Validated Qloo Request
      |
      v
Qloo Adapter
~~~

The query builder must validate that parameters are compatible with the selected target entity type.

## 15. Internal Query Representation

The agent should not directly construct arbitrary query strings.

Use an internal representation similar to:

~~~text
QlooDiscoveryRequest
├── target_type
├── interest_entities[]
├── interest_tags[]
├── audience[]
├── location
├── filters
├── exclusions
├── ranking
├── explainability
└── pagination
~~~

The adapter converts this representation into the actual Qloo HTTP request.

## 16. Initial Internal Tool Contracts

These are conceptual contracts and will be converted into concrete Pydantic schemas during backend implementation.

### resolve_entity

Input:

~~~json
{
  "name": "Taylor Swift",
  "entity_type": "artist",
  "location": null
}
~~~

Output:

~~~json
{
  "status": "resolved",
  "entity_id": "...",
  "entity_type": "...",
  "name": "Taylor Swift",
  "confidence": 0.97
}
~~~

### search_tags

Input:

~~~json
{
  "query": "minimalist fashion",
  "entity_type": "brand"
}
~~~

Output:

~~~json
{
  "status": "resolved",
  "tags": []
}
~~~

### qloo_insights

Input:

~~~json
{
  "target_type": "urn:entity:place",
  "interest_entities": [],
  "interest_tags": [],
  "location": null,
  "filters": {},
  "explainability": true,
  "take": 15
}
~~~

Output:

~~~json
{
  "status": "success",
  "results": [],
  "explainability": {},
  "metadata": {}
}
~~~

The final schemas must reflect the actual API responses observed during integration testing.

## 17. Example: Discover for Me

User:

> "I love Suits, The Blacklist, Korean dramas, and alternative R&B. What restaurants in Lagos might I enjoy?"

Agent state:

~~~text
mode = self
goal = restaurant discovery
target = place

signals:
    Suits
    The Blacklist
    Korean drama
    alternative R&B

location:
    Lagos
~~~

Execution:
1. Resolve the relevant entities/tags.
2. Determine the target type.
3. Construct place Insights request.
4. Apply Lagos location context.
5. Enable explainability.
6. Request a bounded result set.
7. Evaluate returned places.
8. Present discoveries and evidence.

The important architectural property is that the target is **places**, while the input signals can originate from entertainment and music.

## 18. Example: Discover for Someone Else

User:

> "I need a birthday gift for someone who loves Taylor Swift, Korean dramas, coffee and minimalist fashion."

The agent should first identify whether the available information is sufficient.

Possible missing information:
- Budget
- Location
- Physical product vs experience

Only after the missing information materially affects the discovery should the agent ask for it.

After receiving enough context:

~~~text
Person preferences
      ↓
Entity/tag resolution
      ↓
Target category selection
      ↓
Qloo insights
      ↓
Result evaluation
      ↓
Gift discoveries
~~~

Qloo provides the cultural-affinity layer; budget, delivery, availability, and current purchase details may require other services.

## 19. Example: Discover for Business

Business input:

> "We are considering Lagos for a new lifestyle concept. What cultural categories should we investigate?"

The agent should identify:
- Business objective
- Target audience
- Existing concept/category
- Location
- Important constraints

Possible Qloo operations:
- Resolve the relevant brand/category entities.
- Use audience signals where appropriate.
- Use location context.
- Query relevant cultural affinities.
- Compare or explore adjacent categories where supported.

The result should be presented as **cultural intelligence and areas to investigate**, not as a guarantee of market success.

## 20. Query Refinement

A Qloo query can be refined when results fail a meaningful requirement.

~~~text
Initial query
     ↓
Results
     ↓
Evaluation
     |
     +--> sufficient → final
     |
     +--> missing user information → ask user
     |
     +--> query too broad → refine
     |
     +--> wrong target → rebuild
~~~

The agent should have a maximum refinement count.

Initial target:
- Maximum Qloo refinement iterations: 2–3 per discovery request.

## 21. Current Information vs Cultural Intelligence

Qloo should answer the cultural-affinity question.

Other services may be required for facts that change frequently.

~~~text
Qloo:
"Would this type of place fit the user's taste?"

Current search / external provider:
"Is the place open tonight?"
"Is the event currently available?"
"What is today's price?"
~~~

The agent must not use stale Qloo data as a substitute for current operational facts when freshness matters.

## 22. Caching

Caching should be introduced only after the basic integration works.

Potential cache candidates:
- Entity resolution results
- Tag resolution results
- Stable Qloo metadata
- Repeated identical discovery requests

Do not cache personalized results without considering:
- User context
- Request parameters
- Location
- Freshness
- Qloo terms/limits

The first implementation should prioritize correctness over aggressive caching.

## 23. Error Mapping

Qloo errors should be translated into internal application errors.

~~~text
Qloo 400
   ↓
InvalidDiscoveryQuery

Qloo 404
   ↓
NoDiscoveryResult / EntityNotFound

Qloo 429
   ↓
QlooRateLimited

Qloo 500
   ↓
ExternalDiscoveryUnavailable

Network timeout
   ↓
QlooTimeout
~~~

The user should receive a useful recovery message, while logs retain the technical diagnostic.

Qloo's Search Entities documentation currently documents 200, 404, and 429 responses, while the Insights documentation documents 200, 400, and 500 responses.

## 24. Qloo Response Normalization

The application should normalize Qloo responses into an internal result model.

Conceptual model:

~~~text
DiscoveryResult
├── id
├── name
├── entity_type
├── description?
├── image?
├── location?
├── affinity?
├── explanation
├── qloo_evidence
└── source_metadata
~~~

The normalizer should preserve Qloo evidence needed for explanations while avoiding unnecessary storage of the entire raw response.

## 25. Security

The Qloo API key is a backend secret.

Never:
- Include it in frontend JavaScript.
- Return it through an API response.
- Log it.
- Commit it.
- Put it in screenshots or demo configuration.

For the public repository, provide only:

~~~text
QLOO_API_KEY=
~~~

through a documented .env.example.

## 26. Implementation Sequence

The recommended implementation order is:

1. Create Qloo configuration.
2. Implement a minimal QlooClient.
3. Implement entity search.
4. Inspect and normalize real Qloo responses.
5. Implement Insights requests.
6. Add explainability.
7. Build internal Qloo request models.
8. Build tool wrappers.
9. Connect tools to the custom agent.
10. Add query evaluation/refinement.
11. Add persistent discovery results.
12. Add integration tests using controlled fixtures/mocks.
13. Validate against the live hackathon API environment.

## 27. Official Documentation References

Primary sources:
- Qloo API Overview: https://docs.qloo.com/reference/api-overview
- Insights API Deep Dive: https://docs.qloo.com/reference/insights-api-deep-dive
- Parameter Overview: https://docs.qloo.com/reference/parameter-overview
- Parameter Reference: https://docs.qloo.com/reference/parameters
- Search Entities: https://docs.qloo.com/reference/get-search

The implementation should re-check these official references when API behavior or schemas change.


---

# Alignment addendum (REQUIREMENTS v1.0)

- Everything in this document that describes Qloo wire formats, parameters, entity-type lists, or response shapes is **provisional** until the `record` spike (TST-020) produces sanitized fixtures; the adapter's normalization layer is the only place that may change as a result (QLO-003).
- The adapter exposes intent-level methods: `resolve`, `recommend`, `audience`, `compare`, `trends` (QLO-002), plus a capability probe feeding `/meta` (QLO-008).
- Location coverage for Nigerian cities is **unverified** (RSK-002); location is a request parameter, never a constant (QLO-007).
- Qloo does not supply prices or product availability; current specifics come from `SearchProvider` (INF-001..006).
- Mock Qloo returns **normalized models** with synthetic data; it must never be presented as Qloo output (TST-012).
