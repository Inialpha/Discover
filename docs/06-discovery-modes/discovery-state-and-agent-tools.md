# Discovery State and Agent Tools

> **Alignment:** This is a detail document. The canonical requirements, enums (modes, intents, statuses, result kinds), API surface, and SSE protocol are in [`REQUIREMENTS.md`](../../REQUIREMENTS.md). If anything here conflicts with it, `REQUIREMENTS.md` wins and this document must be corrected. Decisions: [`docs/01-decisions/decision-records.md`](../01-decisions/decision-records.md). Mode/intent enums: REQUIREMENTS §4. Tool list: §5.4. Group, compare, and trend state additions are in the *Alignment addendum* at the end of this file.

## 1. Purpose

This document turns Discover's product requirements and Qloo integration design into an implementable agent contract.

The design has four goals:

1. Let users describe discovery goals naturally.
2. Let the agent decide when enough information exists.
3. Give the agent controlled tools for entity resolution, Qloo discovery, and current information.
4. Keep execution bounded, observable, testable, and lightweight.

Core principle:

> The agent decides what should happen next; deterministic services perform the actual work.

The LLM must not directly construct arbitrary HTTP requests, access secrets, or control infrastructure.

---

## 2. Scope

This document defines:

- DiscoveryState
- discovery modes
- preferences and constraints
- missing-information tracking
- Qloo entity resolution state
- agent decisions
- tool contracts
- tool execution rules
- follow-up question policy
- Qloo query construction
- result evaluation
- bounded refinement
- agent execution limits
- testing requirements

Database schema, frontend design, authentication, deployment, and exact model selection remain separate concerns.

---

## 3. Design Principles

### Natural language first

Users should be able to describe what they want without knowing Qloo syntax.

### Structured state over prompt-only memory

Important facts should be extracted into typed state rather than repeatedly reconstructed from conversation history.

### Qloo behind an adapter

The agent does not know Qloo HTTP paths, authentication headers, pagination mechanics, or raw response schemas.

### Deterministic execution where possible

Entity lookup, validation, request construction, retries, timeouts, normalization, and persistence should be application code.

### Ask only useful questions

A follow-up question is justified only when the missing information is likely to materially improve the discovery.

### Bounded execution

Every run has limits on steps, tool calls, retries, refinement iterations, time, and response size.

---

# 4. Discovery Modes

The initial modes are:

| Mode | Purpose |
|---|---|
| self | Discover for the current user |
| someone_else | Discover for another person (gift, outing, experience are goals within it) |
| group | Discover for two or more specific people with blended tastes |
| community | Discover for an audience or local community (context, not individual taste) |
| business | Discover markets, audiences, products, places, or opportunities for a business |

Mode changes the discovery objective, useful context, questions, and result interpretation.

---

# 5. Core Discovery State

The application should maintain one structured DiscoveryState for an active discovery run.

Conceptually:

~~~text
DiscoveryState
├── request
├── subject
├── preferences
├── constraints
├── location
├── audience
├── missing_information
├── questions
├── resolved_entities
├── qloo_request
├── results
├── refinement
└── execution
~~~

A first implementation should use Pydantic models and avoid unnecessary class hierarchies.

---

# 6. Request State

Suggested model:

~~~python
class DiscoveryRequest(BaseModel):
    mode: DiscoveryMode | None = None
    goal: str | None = None
    original_message: str
    language: str = "en"
~~~

The original message should be retained because structured extraction can lose nuance.

---

# 7. Subject State

The subject is the person, group, audience, or business for whom discovery is performed.

~~~python
class DiscoverySubject(BaseModel):
    type: Literal["self", "person", "group", "community", "business"] | None = None
    description: str | None = None
    relationship: str | None = None
~~~

Examples include the current user, a girlfriend, a community audience, or a business.

Relationship is conversational context and should not be sent to Qloo unless it has a meaningful downstream use.

---

# 8. Preference Model

Preferences represent things the subject likes, dislikes, follows, uses, watches, listens to, visits, or otherwise identifies with.

~~~python
class Preference(BaseModel):
    raw: str
    category: str | None = None
    sentiment: Literal["like", "dislike", "neutral", "unknown"] = "unknown"
    strength: float | None = None
    confidence: float = 0.0
    resolved_entity_ids: list[str] = []
    resolved_tag_ids: list[str] = []
~~~

Important distinction:

- raw = what the user actually said
- resolved_entity_ids = Qloo entity identifiers
- resolved_tag_ids = Qloo tag identifiers
- confidence = confidence in the interpretation
- strength = apparent strength of the preference

These concepts must not be conflated.

---

# 9. Constraints

Constraints narrow the discovery without necessarily describing taste.

~~~python
class DiscoveryConstraints(BaseModel):
    budget_min: float | None = None
    budget_max: float | None = None
    currency: str | None = None
    physical_or_experience: Literal["physical", "experience", "either"] | None = None
    time_window: str | None = None
    target_type: str | None = None
    exclusions: list[str] = []
    other: dict[str, Any] = {}
~~~

Examples:

- "Under ₦100,000" → budget.
- "An experience" → output constraint.
- "Near Lagos" → location.
- "Not horror" → exclusion.
- "Restaurants" → target type.

The agent should not treat every noun as a preference.

---

# 10. Location

Location is represented separately.

~~~python
class LocationContext(BaseModel):
    raw: str | None = None
    query: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    radius_km: float | None = None
    qloo_locality_id: str | None = None
    confidence: float = 0.0
~~~

The backend should resolve locality information through the appropriate lookup path rather than inventing identifiers.

---

# 11. Audience

Community and business discovery may require audience information.

~~~python
class AudienceContext(BaseModel):
    description: str | None = None
    characteristics: list[str] = []
    qloo_audience_ids: list[str] = []
    confidence: float = 0.0
~~~

Geography alone must not be treated as a complete representation of an audience.

---

# 12. Missing Information

The agent needs an explicit representation of uncertainty.

~~~python
class MissingInformation(BaseModel):
    field: str
    reason: str
    importance: Literal["low", "medium", "high"]
    expected_value: float = 0.0
    question: str | None = None
~~~

Expected value represents the estimated usefulness of obtaining the information.

Example:

~~~json
{
  "field": "budget",
  "reason": "Gift recommendations may be unusable without a spending range.",
  "importance": "high",
  "expected_value": 0.86
}
~~~

Low-value questions should normally be skipped.

---

# 13. Asked Questions

Questions must be tracked so the agent does not repeatedly ask the same thing.

~~~python
class AskedQuestion(BaseModel):
    field: str
    question: str
    answer: str | None = None
    answered: bool = False
~~~

---

# 14. Qloo Entity Resolution

Natural-language preferences often need to be resolved before they become Qloo signals.

~~~python
class ResolvedEntity(BaseModel):
    raw_input: str
    qloo_entity_id: str
    name: str
    type: str | None = None
    confidence: float
    source: Literal["search", "previous_state"]
~~~

The original text remains important because a resolved entity is an interpretation, not an immutable fact.

---

# 15. Internal Qloo Request

The agent should create an application-level request model, not raw Qloo JSON.

~~~python
class QlooDiscoveryRequest(BaseModel):
    target_type: str
    interest_entities: list[str] = []
    interest_tags: list[str] = []
    location: LocationContext | None = None
    audience_ids: list[str] = []
    filters: dict[str, Any] = {}
    exclusions: list[str] = []
    take: int = 15
    explainability: bool = True
~~~

The Qloo adapter translates this model into the actual API request.

---

# 16. Normalized Discovery Result

Raw Qloo responses should be normalized before reaching the rest of the application.

~~~python
class DiscoveryResult(BaseModel):
    id: str
    name: str
    type: str
    description: str | None = None
    image_url: str | None = None
    location: dict[str, Any] | None = None
    score: float | None = None
    explanation: list[str] = []
    metadata: dict[str, Any] = {}
~~~

Raw provider responses may be retained for debugging, but normal application logic should operate on normalized results.

---

# 17. Refinement State

~~~python
class RefinementState(BaseModel):
    iteration: int = 0
    max_iterations: int = 3
    last_evaluation: str | None = None
    issues: list[str] = []
    changes: list[str] = []
~~~

Every refinement must make a concrete change. Repeating the same request is not refinement.

---

# 18. Execution State

~~~python
class ExecutionState(BaseModel):
    step: int = 0
    max_steps: int = 8
    tool_calls: int = 0
    max_tool_calls: int = 12
    started_at: datetime | None = None
    status: Literal["running", "needs_input", "complete", "failed", "timeout"] = "running"
    errors: list[str] = []
~~~

Execution metadata is operational state, not user preference.

---

# 19. Complete State

Conceptually:

~~~python
class DiscoveryState(BaseModel):
    request: DiscoveryRequest
    subject: DiscoverySubject
    preferences: list[Preference]
    constraints: DiscoveryConstraints
    location: LocationContext | None
    audience: AudienceContext | None
    missing_information: list[MissingInformation]
    questions: list[AskedQuestion]
    resolved_entities: list[ResolvedEntity]
    qloo_request: QlooDiscoveryRequest | None
    results: list[DiscoveryResult]
    refinement: RefinementState
    execution: ExecutionState
~~~

The implementation should use Pydantic default factories for mutable lists and nested defaults.

---

# 20. Four Categories of State

### Conversation state

What the user and agent said.

### Discovery state

What the system currently believes about the objective.

### External state

What Qloo, search, or other providers returned.

### Execution state

How the current run is progressing.

This separation makes debugging and persistence easier.

---

# 21. Agent Decision Model

The initial decision types are:

~~~text
ASK_USER
CALL_TOOL
COMPLETE
~~~

Conceptually:

~~~python
class AgentDecision(BaseModel):
    action: Literal["ask_user", "call_tool", "complete"]
    question: str | None = None
    tool_name: str | None = None
    tool_arguments: dict[str, Any] = {}
    response: str | None = None
~~~

Validation rules:

- ask_user requires question
- call_tool requires a registered tool
- complete requires a user-facing response

Refinement is normally another call_tool decision.

---

# 22. Initial Agent Tools

Keep the initial tool surface small:

1. resolve_entity
2. search_tags
3. resolve_location
4. qloo_discover
5. current_search

The agent should not receive a generic HTTP tool.

---

# 23. resolve_entity

Purpose: resolve natural-language entities such as artists, movies, brands, restaurants, places, and products.

Example input:

~~~json
{
  "query": "Taylor Swift",
  "expected_type": "music"
}
~~~

Example output:

~~~json
{
  "matches": [
    {
      "id": "qloo-entity-id",
      "name": "Taylor Swift",
      "type": "artist",
      "confidence": 0.99
    }
  ]
}
~~~

The agent must never invent Qloo IDs.

---

# 24. search_tags

Purpose: resolve concepts better represented as tags than individual entities.

Examples include minimalist, luxury, indie, outdoor, romantic, and family-friendly.

Example input:

~~~json
{
  "query": "minimalist luxury"
}
~~~

The tool returns candidate Qloo tags with confidence values.

---

# 25. resolve_location

Purpose: convert natural-language location into structured location context.

Example:

~~~json
{
  "query": "Lagos"
}
~~~

The tool returns normalized locality information and, when available, a Qloo locality identifier.

---

# 26. qloo_discover

Purpose: execute a validated cultural-intelligence query.

Example input:

~~~json
{
  "target_type": "place",
  "interest_entities": ["..."],
  "interest_tags": ["..."],
  "location": {
    "query": "Lagos"
  },
  "filters": {},
  "take": 15,
  "explainability": true
}
~~~

The tool returns normalized recommendations and enough explainability metadata for the application to explain why results appeared.

---

# 27. current_search

Qloo provides cultural intelligence, not every current operational fact.

Use current search when the user needs information such as:

- current opening hours
- current event dates
- current prices
- current availability
- recent announcements

It should not replace Qloo for cultural recommendation ranking.

---

# 28. Tool Registry

Tools should be explicitly registered.

~~~python
TOOLS = {
    "resolve_entity": resolve_entity,
    "search_tags": search_tags,
    "resolve_location": resolve_location,
    "qloo_discover": qloo_discover,
    "current_search": current_search,
}
~~~

The LLM receives only schemas for registered tools.

The executor verifies every requested tool before execution.

---

# 29. Tool Execution

Every call passes through a common executor:

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
    ↓
Return to agent
~~~

The executor handles timeouts, retries, rate limits, provider errors, and malformed responses.

The LLM receives concise structured errors rather than stack traces.

---

# 30. Follow-Up Question Policy

Ask when all are true:

1. Missing information materially affects discovery quality.
2. It cannot reasonably be inferred.
3. It has not already been answered.
4. The question is understandable.
5. Asking is better than proceeding with a clearly poor query.

Proceed without asking when:

- missing information is low impact
- reasonable defaults exist
- Qloo can still produce useful results
- the user requested exploratory discovery
- another question would add unnecessary friction

---

# 31. Question Selection

When several fields are missing, prioritize the one with the greatest expected value.

A practical heuristic is:

~~~text
question_value =
    expected_improvement
    × confidence_missing
    × relevance_to_goal
~~~

This is an engineering heuristic, not a claim about human preference.

For gift discovery, budget and physical-versus-experience often have greater immediate impact than favorite color.

---

# 32. Ambiguity

Ambiguity does not automatically require a question.

Example:

> "I want something like Suits."

The system can first resolve Suits and use it as an interest signal.

If ambiguity changes the target materially, ask.

Example:

> "Find something for my sister."

This lacks enough context for a useful personalized gift recommendation, so the agent should ask a focused question.

---

# 33. Entity Resolution Policy

Initial engineering thresholds:

~~~text
>= 0.90   use automatically
0.70-0.89 use cautiously or consider alternatives
< 0.70   ask or perform another resolution step
~~~

These thresholds should be validated with tests and adjusted from real usage.

---

# 34. Discovery Readiness

Readiness should be partly deterministic.

~~~python
def is_ready(state: DiscoveryState) -> bool:
    return (
        state.request.goal is not None
        and target_type_is_known(state)
        and has_sufficient_signals(state)
        and not has_high_value_missing_information(state)
    )
~~~

The LLM can propose the interpretation, while deterministic validation checks whether the state is actually usable.

---

# 35. Target Type

Target type describes what the user wants discovered.

Examples:

- movie
- TV
- music
- place
- restaurant
- brand
- product
- experience

The LLM may propose a target type, but backend validation must ensure it is compatible with the current Qloo configuration.

If multiple target types are genuinely useful, use separate bounded discovery operations rather than an invalid combined request.

---

# 36. Qloo Query Construction

The flow is:

~~~text
Natural language
    ↓
DiscoveryState
    ↓
QlooQueryBuilder
    ↓
QlooDiscoveryRequest
    ↓
QlooAdapter
    ↓
Qloo API
~~~

The query builder maps state into:

- target type
- entity signals
- tag signals
- location
- filters
- exclusions
- result count
- explainability

Qloo-specific HTTP details stay inside the adapter.

---

# 37. Signals vs Filters

Signals describe what the subject is interested in.

Examples:

- favorite artists
- favorite movies
- preferred brands
- style tags

Filters constrain returned entities.

Examples:

- entity type
- location
- price level
- applicable content restrictions
- applicable release-year filters

A preference should not automatically become a hard filter.

"I love Taylor Swift" should normally influence ranking rather than require the result itself to be Taylor Swift.

---

# 38. Cross-Domain Discovery

Cross-domain relationships are central to Discover.

Example:

~~~text
Interests:
- Taylor Swift
- Korean dramas
- minimalist luxury

Target:
- product
- place
- experience
~~~

The system can use the interests as cultural signals while requesting a different target type.

This is a core reason Qloo is materially important to the product.

---

# 39. Explainability

Initial recommendations should request Qloo explainability where supported.

Discover should translate machine-readable contribution metadata into user-facing explanations.

Example:

> This was recommended because it aligns strongly with your interest in Taylor Swift and minimalist fashion.

The application must distinguish:

- evidence supplied by Qloo
- interpretation generated by the LLM

The LLM must not invent unsupported reasons.

---

# 40. Result Evaluation

After Qloo returns results, evaluate:

1. target type
2. explicit constraints
3. location
4. major preferences
5. exclusions
6. usefulness
7. diversity
8. result count

Example evaluation:

~~~json
{
  "acceptable": true,
  "issues": [],
  "missing_coverage": []
}
~~~

If weak:

~~~json
{
  "acceptable": false,
  "issues": [
    "Results do not sufficiently reflect the location constraint."
  ],
  "missing_coverage": [
    "minimalist fashion"
  ]
}
~~~

---

# 41. Refinement

A refinement must make a concrete change.

Examples:

- add a missing high-strength interest
- adjust target type
- apply a valid location filter
- apply an explicit price constraint
- remove an incorrectly resolved entity
- broaden or narrow the request

Maximum initial Qloo refinement iterations: 3.

The agent must not repeatedly execute an unchanged request.

---

# 42. Agent Loop

The main loop should remain small:

~~~python
async def run_agent_loop(state: DiscoveryState) -> AgentResult:
    for _ in range(state.execution.max_steps):
        decision = await decide_next_action(state)

        if decision.action == "ask_user":
            return needs_input(decision.question)

        if decision.action == "complete":
            return complete(decision.response)

        if decision.action == "call_tool":
            result = await execute_tool(
                decision.tool_name,
                decision.tool_arguments
            )
            update_state(state, decision, result)

    return max_steps_result()
~~~

The frontend should see a stable API result rather than the internal loop.

---

# 43. Agent Context

Each decision should receive only the context needed for that step:

1. system instructions
2. discovery objective
3. structured state
4. recent conversation
5. available tool schemas
6. relevant external results
7. execution limits

Do not repeatedly append huge raw provider responses.

Normalize or summarize large results before passing them back to the model.

---

# 44. Agent vs Service Responsibilities

| Responsibility | Agent | Backend |
|---|---:|---:|
| Understand intent | Yes | Validate |
| Extract preferences | Yes | Validate/store |
| Decide whether to ask | Yes | Enforce limits |
| Resolve entity | Decide | Execute |
| Build raw Qloo request | No | Yes |
| Call Qloo | No | Yes |
| Interpret results | Yes | Normalize |
| Enforce constraints | Decide | Validate |
| Retry HTTP | No | Yes |
| Protect Qloo key | No | Yes |
| Persist state | No | Yes |
| Produce final response | Yes | Format/validate |

The agent is a decision-maker, not an unrestricted backend operator.

---

# 45. Personal Discovery Example

User:

> I love Suits, Normal People and The Blacklist. I also listen to a lot of R&B. What should I watch next?

State should identify:

- mode = self
- target = TV/movie
- preferences = the named shows plus R&B
- no unnecessary follow-up

Flow:

1. resolve important entities
2. resolve R&B as an appropriate signal/tag
3. build a cross-domain Qloo request
4. request explainability
5. evaluate results
6. return discoveries with reasons

---

# 46. Gift Discovery Example

User:

> I need a birthday gift for my girlfriend. She loves Korean dramas and Taylor Swift.

Initial state:

- mode = someone_else (goal_type = gift)
- subject = person
- goal = birthday gift
- interests = Korean dramas, Taylor Swift
- missing = budget and gift type

A useful follow-up:

> What is your approximate budget, and would you prefer a physical gift, an experience, or either?

After the answer, resolve interests and discover appropriate target types.

If the user says "Surprise me", the agent can use reasonable defaults rather than asking more questions.

---

# 47. Community Discovery Example

User:

> What kinds of weekend experiences could work for a group of young professionals interested in independent music and fashion in Lagos?

State:

- mode = community
- target = experiences/places
- audience description
- music interest
- fashion interest
- location = Lagos

The system must not assume that all people in a geographic or demographic group share one taste profile.

---

# 48. Business Discovery Example

User:

> I run a premium skincare brand. I want to understand what kinds of adjacent experiences or markets could fit our brand in Lagos.

State:

- mode = business
- subject = business
- goal = market discovery
- category = premium skincare
- location = Lagos

Flow:

1. resolve relevant concepts
2. identify useful cultural or audience signals
3. query Qloo
4. evaluate relationships
5. present opportunities as discoveries rather than certainties

Strategic interpretation must be clearly distinguished from observed recommendation relationships.

---

# 49. Current Information Boundary

For:

> Which of these recommended restaurants is open tonight?

the flow should be:

~~~text
Qloo
 ↓
Cultural shortlist
 ↓
Current-information search
 ↓
Final response
~~~

Qloo handles cultural relevance. A current source handles operational facts.

---

# 50. Error Model

Suggested categories:

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

Example structured error:

~~~json
{
  "success": false,
  "error_type": "RATE_LIMITED",
  "retryable": true,
  "message": "The recommendation service is temporarily rate limited."
}
~~~

The LLM should not receive raw stack traces.

---

# 51. Retry Policy

Initial defaults:

- short configurable HTTP timeout
- at most 2 transient retries
- exponential backoff
- no retry for invalid requests
- no retry for authentication failures
- stop retrying when execution limits are reached

Configuration should live in one place.

---

# 52. Loop Prevention

Stop execution when:

- the same tool is called repeatedly with identical arguments
- the same Qloo request repeats without a state change
- refinement count is exceeded
- a tool produces no new information repeatedly
- an entity remains unresolved after allowed attempts
- the same question is repeated
- execution times out
- the provider is unavailable

Request fingerprints can detect repeated Qloo calls.

---

# 53. Persistence

Persist enough state to support:

- active discovery sessions
- discovery history
- saved discoveries
- explicit user preferences

Do not permanently store every internal LLM thought or every raw provider payload.

Persist structured state and useful result metadata.

---

# 54. Privacy

Use data minimization.

Gift discovery may need:

- relationship
- interests
- budget
- gift type

It generally does not need a person's full legal name, phone number, or exact home address unless another requirement explicitly requires it.

---

# 55. Prompt Injection Boundary

User text and external results are untrusted data.

The agent must not follow instructions embedded inside:

- entity descriptions
- search results
- recommendation metadata
- web content

Tool results are data, not instructions.

---

# 56. Lightweight Module Direction

A practical backend structure is:

~~~text
backend/
└── app/
    ├── agent/
    │   ├── orchestrator.py
    │   ├── decisions.py
    │   ├── prompts.py
    │   └── state.py
    │
    ├── discovery/
    │   ├── service.py
    │   ├── evaluator.py
    │   └── query_builder.py
    │
    ├── qloo/
    │   ├── client.py
    │   ├── entities.py
    │   ├── tags.py
    │   ├── insights.py
    │   └── models.py
    │
    ├── tools/
    │   ├── registry.py
    │   ├── executor.py
    │   └── definitions.py
    │
    └── search/
        └── current.py
~~~

This is a direction, not a requirement to create every file immediately.

Prefer functions and Pydantic models when they are sufficient.

---

# 57. Testing Strategy

## Unit tests

Test:

- state validation
- preference normalization
- missing-information prioritization
- query construction
- Qloo request validation
- result normalization
- refinement detection
- execution limits
- duplicate-call detection

## Tool contract tests

Mock providers and verify:

- valid arguments
- invalid arguments
- timeout handling
- retry behavior
- response normalization
- error mapping

## Agent behavior tests

Use fixed LLM responses to test:

- useful follow-up questions
- no unnecessary questions
- entity resolution
- Qloo call after sufficient information
- refinement of poor results
- correct termination
- rejection of unsupported tools

## End-to-end tests

At least one controlled test should cover each of the five discovery modes.

---

# 58. Example Agent Trace

~~~text
USER
"I need a birthday gift for my girlfriend.
She loves Korean dramas and Taylor Swift."

        ↓

AGENT
Extract state

        ↓

STATE
mode = someone_else (goal_type = gift)
goal = birthday gift
subject = girlfriend
preferences = Korean dramas, Taylor Swift
missing = budget, gift type

        ↓

AGENT
ASK_USER

        ↓

USER
"About ₦100,000. Either physical or experience."

        ↓

AGENT
Resolve entities

        ↓

TOOL
resolve_entity("Taylor Swift")

        ↓

TOOL
resolve_entity("Korean dramas")

        ↓

AGENT
Build discovery

        ↓

TOOL
qloo_discover(...)

        ↓

QLOO
Recommendations + explainability

        ↓

AGENT
Evaluate

        ↓

COMPLETE
or bounded refinement

        ↓

USER
Personalized discoveries + explanations
~~~

---

# 59. Definition of Done

The agent layer is ready for the first implementation milestone when it can:

- accept natural-language discovery requests
- identify one of the five modes
- maintain structured discovery state
- identify high-value missing information
- ask a focused follow-up
- resolve important Qloo entities
- construct a validated internal Qloo request
- call Qloo through the adapter
- receive normalized recommendations
- use Qloo explainability
- evaluate results against explicit constraints
- perform bounded refinement
- produce a user-facing answer
- terminate within configured limits
- expose useful errors without leaking secrets

---

# 60. Implementation Sequence

### Phase 1 — Models

Create discovery enums, Pydantic state models, decision models, and tool input/output models.

### Phase 2 — Tool infrastructure

Create tool definitions, registry, executor, validation, timeout, and retry handling.

### Phase 3 — Qloo adapter

Implement entity search, tag search, location resolution, insights, response normalization, and explainability mapping.

### Phase 4 — Query builder

Implement deterministic mapping from DiscoveryState to QlooDiscoveryRequest.

### Phase 5 — Agent loop

Implement the LLM adapter, decision parsing, bounded orchestration, and state updates.

### Phase 6 — Evaluation and refinement

Implement result evaluation, refinement rules, and duplicate-call prevention.

### Phase 7 — API

Expose discovery-session endpoints to the frontend.

### Phase 8 — Persistence

Add PostgreSQL-backed sessions, history, and saved discoveries.

---

# 61. Architectural Summary

Discover is not:

~~~text
User → LLM → Qloo → answer
~~~

It is:

~~~text
User
 ↓
Structured Discovery State
 ↓
Bounded Agent
 ├── Ask for missing information
 ├── Resolve entities
 ├── Resolve location/tags
 ├── Build validated discovery request
 ├── Call Qloo
 ├── Evaluate results
 ├── Refine when justified
 └── Explain results
 ↓
User
~~~

The key engineering boundary is:

> The LLM decides; deterministic application services execute.

The key product boundary is:

> Discover uses cultural intelligence to answer what someone should discover next, not merely what is similar to what they already know.


---

# Alignment addendum (REQUIREMENTS v1.0)

These additions bring this document in line with `REQUIREMENTS.md`; where earlier sections differ, this addendum and the requirements win.

## A1. Taxonomy
- Modes: `self`, `someone_else`, `group`, `community`, `business` (REQUIREMENTS §4.1). Earlier uses of `personal` and `gift` mean `self` and `someone_else` with `goal_type = gift`.
- A separate `intent` field (`recommend`, `taste_profile`, `audience_insight`, `location_insight`, `compare`, `trend`, `market_scan`) lives in `DiscoveryRequest` (§4.2).

## A2. State additions
~~~python
class DiscoveryRequest(BaseModel):
    mode: DiscoveryMode | None = None
    intent: DiscoveryIntent = "recommend"
    goal: str | None = None
    goal_type: Literal["gift","outing","experience","media","general"] | None = None
    original_message: str
    language: str = "en"

class Participant(BaseModel):
    id: str
    role: Literal["self","recipient","member"]
    display_name: str
    source: Literal["user","invite"] = "user"
    likes: list[str] = []
    dislikes: list[str] = []
    constraints: dict = {}
    resolved_entities: list[ResolvedEntity] = []

class BlendConfig(BaseModel):                 # group mode (MOD-021)
    strategy: Literal["consensus","balanced","variety"] = "balanced"

class Assumption(BaseModel):                  # AGT-005
    key: str
    text: str
~~~
`DiscoveryState` gains `participants`, `intent`, `blend`, `assumptions`, `feedback_adjustments`, and `schema_version` (REQUIREMENTS §8.4).

## A3. Tool additions
`query_audience_insights`, `query_trends`, `compare_subjects`, `search_current_info` join the tool set (REQUIREMENTS §5.4). Every tool registers a **user-safe label** used in `tool.started` / `tool.completed` events, plus a timeout and an argument schema. Tool results never include raw provider payloads in events.

## A4. Group blending
Build one query per blend strategy from per-participant signals; `consensus` weights shared signals, `balanced` equalizes participant influence, `variety` produces sections biased to each participant. Per-participant fit statements must be tagged `evidence` or `interpretation`.

## A5. Gift with budget
Qloo selects candidate brands/categories/entities; `search_current_info` supplies current items and prices. Only items with verified prices satisfy a strict budget (INF-003). Without a search provider, return experiences, places, brands, and media and state the limitation (INF-006).

## A6. Evidence vs interpretation
Every explanation fragment is tagged `evidence`, `user_context`, or `interpretation` (TAX-007); `compose_response` must populate these tags.

## A7. Streaming
The agent loop emits user-safe events through an `EventSink` (REQUIREMENTS §7.6). Prompts, raw decisions, and provider payloads are never emitted (STR-009).
