# Discover — Requirements Specification

**Project:** Discover  
**Repository:** `Inialpha/Discover`  
**Status:** Living specification — Version 0.1  
**License:** MIT  
**Primary integration:** Qloo Cultural Intelligence API

---

## 1. Purpose

Discover is an agentic cultural intelligence and discovery platform. It allows people and businesses to describe what they want in natural language, including through voice, without requiring them to understand recommendation systems or Qloo API syntax.

The Discover agent interprets the user's goal, extracts relevant preferences and context, determines what information is missing, asks targeted follow-up questions when necessary, resolves relevant entities through Qloo, queries Qloo's cultural intelligence capabilities, evaluates the results, and presents useful discoveries with understandable explanations.

Discover is intended to support discovery across domains rather than restricting a user to a single category such as movies, restaurants, or music.

---

## 2. Product Vision

Discover should answer a broader question than:

> "What is similar to this?"

Its goal is:

> **"Given what matters to me, this person, this community, or this business, what should I discover next?"**

The product should connect preferences across domains and contexts so that a user's interests in one area can contribute to discoveries in another.

Examples:

- A person's movie and music tastes can contribute to restaurant or experience recommendations.
- A description of a friend can be transformed into gift discoveries.
- A business can explore cultural relevance within a target location or audience.
- A community can be explored through its cultural interests and context.

---

## 3. Target Users

### 3.1 Individuals

People looking for personalized discoveries such as:

- Movies and television
- Music
- Restaurants and food
- Places
- Experiences
- Products
- Brands
- Events
- Activities

### 3.2 People discovering for someone else

Users who want to discover:

- Gifts
- Experiences
- Places
- Products
- Entertainment
- Activities

for another person.

### 3.3 Communities and groups

Users exploring what may be culturally relevant to:

- A local community
- A university/community group
- A demographic or audience
- A specific geographic market

### 3.4 Businesses

Organizations seeking:

- Market discovery
- Audience discovery
- Product opportunities
- Cultural relevance
- Market-entry insights
- Location intelligence
- Brand/taste analysis

---

# 4. Discovery Modes

## 4.1 Discover for Me

The user describes their own tastes, interests, context, or goal.

Example:

> "I love Suits, The Blacklist, and Korean dramas. I also listen to alternative R&B. What else might I enjoy?"

The agent should identify the relevant cross-domain signals rather than treating this as a simple title-similarity search.

### Requirements

- Accept natural-language descriptions.
- Accept multiple interests in one request.
- Extract explicit and relevant implicit context.
- Resolve relevant entities through Qloo.
- Use Qloo insights to discover related entities.
- Explain why results were selected.
- Allow the user to refine the discovery.

---

## 4.2 Discover for Someone Else

The user describes another person and what they want to discover for that person.

Example:

> "I need a birthday gift for my girlfriend. She loves Taylor Swift, Korean dramas, minimalist fashion, and coffee. My budget is ₦100,000."

### Requirements

- Identify the subject as someone other than the current user.
- Capture the purpose or occasion.
- Extract known preferences.
- Identify missing information.
- Ask targeted follow-up questions when additional information materially improves the discovery.
- Maintain the subject's information separately from the user's own profile.
- Support constraints such as budget, location, timing, and gift type.
- Produce discoveries appropriate to the stated goal.

---

## 4.3 Discover for Community

The user describes a group, audience, or location and asks what may be culturally relevant.

### Requirements

- Capture the intended community/audience.
- Distinguish geographic context from personal taste.
- Avoid assuming that nationality, ethnicity, or location determines an individual's taste.
- Use Qloo's appropriate audience/location capabilities.
- Present results as cultural intelligence and discovery rather than demographic certainty.
- Clearly communicate meaningful uncertainty where appropriate.

---

## 4.4 Discover for Business

Businesses can use Discover to explore audiences, markets, products, locations, and cultural opportunities.

Potential use cases:

- "What kinds of experiences might resonate with this audience?"
- "What cultural categories should we investigate before entering this market?"
- "What products or brands are culturally adjacent to our target audience?"
- "What other interests are associated with people who like this brand?"

### Requirements

- Capture business goal.
- Capture target audience.
- Capture target location/market where applicable.
- Capture existing product, brand, or category.
- Identify relevant constraints.
- Use Qloo capabilities appropriate to the business question.
- Distinguish Qloo-derived observations from agent-generated interpretation.
- Avoid presenting cultural intelligence as guaranteed market success.
- Allow iterative refinement.

---

# 5. Core User Experience

## 5.1 Natural-language interaction

Users must not need to understand:

- Qloo API syntax
- Entity IDs
- Tags
- Query parameters
- Recommendation algorithms

The agent is responsible for translating natural language into structured discovery operations.

---

## 5.2 Voice input

The interface should support voice input where supported by the selected speech-to-text service.

Flow:

`Voice → Transcription → Discovery Agent → Tools/Qloo → Response`

The agent should receive the transcription as normal user input.

Voice transcription is an input mechanism, not a separate discovery mode.

---

## 5.3 Intelligent follow-up questions

The agent must not ask unnecessary questions.

It should ask a follow-up question when:

1. Important information is missing.
2. The missing information can materially change the result.
3. The user has not already supplied the information.
4. The question is understandable and useful.

Example:

> "I want a birthday gift for my sister."

Possible response:

> "I'd be happy to help. What are a few things she genuinely enjoys, and roughly how much would you like to spend?"

The agent should prefer questions that reduce uncertainty efficiently.

---

## 5.4 Conversation state

The system must maintain structured discovery state independently from the raw conversation.

Conceptual state:

- Mode
- Goal
- Subject
- Preferences
- Entities
- Constraints
- Location
- Audience
- Missing information
- Resolved Qloo entities
- Qloo query context
- Results
- Refinement history

The exact persistence model will be defined in the database specification.

---

# 6. Agent Requirements

Discover will implement its own lightweight agent orchestration system rather than depending on LangChain or LangGraph.

## 6.1 Agent loop

The runtime should support:

1. Receive user input.
2. Load/update discovery state.
3. Call the selected hosted LLM.
4. Detect tool calls.
5. Execute tools.
6. Append tool results to the model context.
7. Continue the loop.
8. Ask the user for missing information when required.
9. Return a final response when the discovery is complete.

Conceptually:

`User → LLM → Tool → LLM → Tool → LLM → Response`

---

## 6.2 Agent safety limits

The agent runtime must have bounded execution.

Requirements:

- Maximum agent steps per request.
- Tool execution timeout.
- External API timeout.
- Retry limits.
- Error handling.
- Protection against infinite tool-call loops.
- Clear user-facing failure states.

---

## 6.3 Agent state

The state model should separate:

### Conversation data

What the user and agent said.

### Discovery data

What the system currently knows about the discovery request.

### External data

Information returned from Qloo or other services.

### Execution data

Tool calls, errors, retries, and execution status.

This separation should prevent uncontrolled conversation growth and simplify debugging.

---

# 7. Agent Tools

The initial tool architecture should support tools conceptually equivalent to:

### Entity resolution

Resolve natural-language entities into Qloo-supported entities/IDs.

### Tag/category lookup

Find relevant Qloo tags or categories.

### Audience/context lookup

Resolve relevant audience or contextual information where supported.

### Qloo insights

Submit a structured request to Qloo's Insights API.

### Current-information search

Use an external search capability only when current information is necessary and appropriate.

### Result evaluation

Evaluate whether retrieved results satisfy the user's stated goal and constraints.

The final tool list and schemas must be based on the official Qloo API documentation and validated against the hackathon API environment.

---

# 8. Qloo Integration Requirements

Qloo must be a meaningful part of Discover's functionality, not a decorative API call.

The application should use Qloo to provide cultural intelligence that materially influences discoveries.

## 8.1 Lookup

The application should use Qloo lookup capabilities to resolve relevant entities/tags/audiences before constructing appropriate insights requests.

## 8.2 Insights

The application should use appropriate Qloo Insights capabilities for the discovery objective.

Potential capabilities include:

- Recommendations
- Demographic insights
- Location-based insights
- Taste analysis
- Heatmaps
- Analysis/compare
- Trending information

The exact supported parameters and endpoints must be derived from the official Qloo documentation and kept in the Qloo integration documentation.

## 8.3 Qloo adapter

The agent must not contain raw Qloo HTTP implementation details.

Instead:

`Agent → Qloo service/adapter → Qloo API`

This keeps the agent independent of Qloo-specific request syntax.

---

# 9. Recommendation and Explanation Requirements

Discover must provide more than a list of results.

Each result should, where sufficient evidence exists, communicate:

- What was discovered.
- What category it belongs to.
- Why it is relevant.
- Which user-provided interests/context contributed to the discovery.
- Relevant location or constraints.
- Any important uncertainty.

The system must not fabricate an explanation for a result.

If an explanation is inferred by the LLM rather than directly provided by Qloo, the architecture should preserve that distinction internally.

---

# 10. User Accounts and Personalization

The first implementation should support an account model that can eventually maintain:

- Basic profile information.
- User preferences.
- Discovery history.
- Saved discoveries.
- Conversation history.
- Optional personalization signals.

Personalization should be based on information the user provides or explicitly allows the system to retain.

The system should not require sensitive personal information merely to provide ordinary discovery.

---

# 11. Saved Discoveries

Users should be able to save useful discoveries.

A saved discovery should preserve enough context to understand:

- What was discovered.
- When it was discovered.
- The discovery mode.
- The original goal.
- Relevant recommendation metadata.
- The source/service where applicable.

---

# 12. Discovery History

Users should be able to review previous discovery sessions.

The system should distinguish:

- Conversation history
- Discovery sessions
- Saved results

These should not automatically be treated as the same object.

---

# 13. Frontend Requirements

The frontend should provide a coherent discovery-oriented experience rather than presenting itself as a generic chatbot.

Initial page candidates:

1. Landing page
2. Authentication
3. Onboarding
4. Home
5. Discovery workspace
6. Results
7. Result details
8. Saved discoveries
9. Discovery history
10. Settings

The exact navigation structure will be finalized in the frontend specification.

---

# 14. Discovery Workspace

The primary discovery interface must support:

- Mode selection or automatic mode detection.
- Text input.
- Voice input.
- Conversation history for the active session.
- Follow-up questions.
- Agent activity/loading states.
- Tool/external-data activity where appropriate.
- Results.
- Refinement.
- Save/share actions where implemented.

The interface should make the transition from conversation to discovery results feel continuous.

---

# 15. Results Interface

Results should support multiple content types.

Potential result categories:

- Movies
- TV
- Music
- Restaurants
- Places
- Products
- Brands
- Experiences
- Events
- Market/audience opportunities

The UI should adapt to the result type rather than forcing every result into an identical card.

---

# 16. Settings

The settings area should eventually support:

- Profile
- Preferences
- Location/context
- Privacy
- Account
- Notifications
- Connected services where applicable

Only settings that are actually implemented should appear in the production UI.

---

# 17. Backend Requirements

The backend will use a lightweight Python architecture.

Initial technology direction:

- Python 3.12
- FastAPI
- OpenAI-compatible hosted LLM client
- Qloo API
- PostgreSQL
- HTTP client for external APIs
- Docker

The backend should avoid unnecessary heavyweight dependencies.

The backend should not run local LLMs, local embedding models, or other compute-heavy AI infrastructure in the initial deployment.

---

# 18. Backend Responsibilities

The backend is responsible for:

- Authentication/session handling.
- Conversation management.
- Discovery state.
- Agent orchestration.
- Tool execution.
- Qloo integration.
- External service integration.
- Persistence.
- Validation.
- Error handling.
- Rate limiting where appropriate.
- Observability/logging.
- API responses.

---

# 19. Conceptual Backend Components

The implementation should be organized around clear responsibilities.

Potential components:

- `AgentOrchestrator`
- `AgentState`
- `ToolRegistry`
- `ToolExecutor`
- `QlooClient`
- `QlooLookupService`
- `QlooInsightsService`
- `DiscoveryService`
- `ConversationService`
- `ResultService`
- `AuthenticationService`

These are design candidates, not mandatory classes. The final implementation should prefer simple functions/modules where a class provides no meaningful benefit.

---

# 20. Database Requirements

PostgreSQL is the intended relational database.

The database design must support, as required by the final product scope:

- Users
- Conversations
- Messages
- Discovery sessions
- Discovery state
- Preferences
- Results
- Saved discoveries
- Feedback

Additional entities should only be introduced when justified by a product requirement.

The database specification must define:

- Tables
- Primary keys
- Foreign keys
- Relationships
- Constraints
- Indexes
- Timestamps
- Deletion behavior
- Migration strategy

---

# 21. API Requirements

The backend API should be versioned.

Initial conceptual API areas:

`/api/v1/auth`  
`/api/v1/conversations`  
`/api/v1/discoveries`  
`/api/v1/results`  
`/api/v1/saved`  
`/api/v1/settings`

Exact endpoints, request schemas, response schemas, and error formats will be specified separately in the API documentation.

---

# 22. Security and Privacy

Requirements:

- Secrets must never be committed to Git.
- API keys must remain server-side.
- Environment variables must be used for secrets.
- Authentication tokens must be handled securely.
- User data must be isolated between accounts.
- External API failures must not expose credentials or internal implementation details.
- Logs must not unnecessarily contain private user content or credentials.
- The application must minimize stored personal information.

Qloo-related data handling must comply with Qloo's applicable API terms and documentation.

---

# 23. Error Handling

The system must gracefully handle:

- Invalid user input.
- Missing information.
- LLM failures.
- Qloo failures.
- External search failures.
- Database failures.
- Timeouts.
- Rate limits.
- Invalid tool arguments.
- Tool execution failures.
- No-result situations.

The user should receive a useful explanation rather than an internal stack trace.

---

# 24. Performance Requirements

The first version should prioritize efficient external API orchestration.

Requirements:

- Avoid unnecessary model calls.
- Avoid unnecessary Qloo calls.
- Ask follow-up questions only when useful.
- Bound agent execution.
- Avoid loading large local models/data.
- Keep backend memory requirements low.
- Use asynchronous I/O where beneficial.
- Avoid unnecessary persistent conversation history in every model request.

---

# 25. Deployment Requirements

The application must be externally accessible for the Qloo hackathon.

Initial deployment architecture:

`Frontend → Hosted web platform`

`Backend → Dockerized FastAPI service`

`Database → Managed PostgreSQL`

`LLM → Hosted API`

`Cultural intelligence → Qloo API`

No local AI model should be required for the production deployment.

---

# 26. Docker Requirements

The backend should be containerized.

Initial base image:

`python:3.12-slim`

The Docker image should:

- Install only required dependencies.
- Avoid development-only packages in production.
- Use a non-root runtime where practical.
- Expose the API through Uvicorn.
- Receive configuration through environment variables.

Alpine should not be selected merely for image-size reasons if it creates dependency compatibility problems.

---

# 27. Testing Requirements

Testing should cover:

### Unit tests

- State handling
- Tool routing
- Query construction
- Validation
- Services

### Agent tests

- Intent recognition
- Missing-information detection
- Tool selection
- Tool-call loops
- Maximum-step behavior
- Final response generation

### Qloo integration tests

- Entity lookup
- Tag lookup
- Insights requests
- Error handling
- Response normalization

### API tests

- Authentication
- Conversation endpoints
- Discovery endpoints
- Saved results
- Error responses

### Frontend tests

- Navigation
- Discovery interaction
- Voice interaction where testable
- Results
- Saving
- Settings

---

# 28. Observability

The backend should provide sufficient logging to diagnose:

- Request lifecycle
- Agent step count
- Tool selected
- Tool success/failure
- Qloo request status
- External API latency
- Agent completion/failure

Logs must avoid exposing:

- API keys
- Authentication tokens
- Unnecessary private user information

Verbose development diagnostics should be removable or disabled in production.

---

# 29. Hackathon Requirements

Discover must satisfy the Qloo Agentic Hackathon requirements applicable to the final submission.

The project must maintain:

- Public GitHub repository.
- Open-source license.
- Live externally hosted application/demo.
- Meaningful Qloo API integration.
- Agentic behavior.
- Publicly accessible source code.
- Required attribution/documentation where applicable.
- Compliance with Qloo API and hackathon rules.

The final submission documentation must map the implemented product to the hackathon requirements.

---

# 30. Non-Goals for the Initial Qloo MVP

The following should not become core requirements unless the product scope is deliberately expanded:

- Clinical diagnosis.
- Medical treatment recommendations.
- Running local LLMs.
- Building a general-purpose search engine.
- Building a general-purpose social network.
- Building a full enterprise CRM.
- Building a large recommendation model from scratch.
- Maintaining a proprietary cultural knowledge graph.
- Supporting every possible external service from the first release.

A future healthcare-oriented "Discover Care" concept may be considered separately, but Qloo must not be treated as a clinical knowledge source.

---

# 31. Engineering Principles

### Principle 1 — Qloo must matter

Qloo should materially influence discovery outcomes.

### Principle 2 — Natural language first

Users should describe goals naturally rather than learn APIs or filters.

### Principle 3 — Agent, not chatbot

The system must be able to reason about missing information, use tools, iterate, and complete multi-step discovery tasks.

### Principle 4 — Lightweight infrastructure

Prefer hosted services and simple Python orchestration over heavyweight local infrastructure.

### Principle 5 — Explicit state

Maintain structured discovery state instead of relying entirely on raw conversation history.

### Principle 6 — Explainable discovery

The system should explain relevant discoveries without inventing evidence.

### Principle 7 — Cross-domain intelligence

Discover should be able to use relationships between different areas of taste and context.

### Principle 8 — User control

Users should be able to refine, reject, save, or restart discoveries.

### Principle 9 — Iterative development

Requirements and architecture are living documents. Implementation should follow the current documented specification.

### Principle 10 — Don't over-engineer

Use classes, services, abstractions, and dependencies only when they solve a real problem.

---

# 32. Requirements Status

| Area | Status |
|---|---|
| Product concept | Defined |
| Discovery modes | Initial definition |
| Agent architecture | Initial definition |
| Custom agent loop | Chosen |
| LangChain | Excluded from initial architecture |
| LangGraph | Excluded from initial architecture |
| Qloo integration | Requires detailed API specification |
| Database schema | Pending |
| Backend API | Pending |
| Frontend pages | Pending detailed specification |
| Design system | Pending |
| Voice architecture | Pending |
| Authentication | Pending |
| Deployment | Initial direction defined |
| Docker | Initial direction defined |
| Testing strategy | Initial definition |
| Hackathon compliance | Pending final verification |

---

## 33. Iteration Rule

This document is the current product and engineering requirements baseline.

When a significant architectural or product decision changes:

1. Update this document.
2. Update the affected detailed documentation.
3. Record the decision where appropriate.
4. Only then implement the change.

Implementation should not silently diverge from the documented requirements.
