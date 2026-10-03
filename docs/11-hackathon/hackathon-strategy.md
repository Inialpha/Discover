# Hackathon Strategy

> **Alignment:** This is a detail document. The canonical requirements, enums (modes, intents, statuses, result kinds), API surface, and SSE protocol are in [`REQUIREMENTS.md`](../../REQUIREMENTS.md). If anything here conflicts with it, `REQUIREMENTS.md` wins and this document must be corrected. Decisions: [`docs/01-decisions/decision-records.md`](../01-decisions/decision-records.md). Scope is fixed by REQUIREMENTS; the delivery plan is §14.

## 1. Purpose

This document translates the current Qloo Agentic Hackathon requirements into implementation and submission priorities for Discover.

The goal is not to optimize the project around speculative judging behavior. The goal is to ensure that the product demonstrably satisfies the published requirements and clearly communicates why Qloo is essential to the product.

The current official rules state that the submission deadline is October 30, 2026 at 11:45 PM EDT. Stage One is a pass/fail viability and theme/API-fit review. Eligible projects then enter Stage Two, which evaluates Technological Implementation, Design, Potential Impact, and Quality of the Idea with equal weighting. 

## 2. Official Requirements Relevant to Discover

The published rules require a working software application that integrates the Qloo API and either functions as an agentic tool, uses an agent framework, or integrates Qloo into an existing agent.

The submission must provide:

- a functional demo application
- a public source repository
- source code, assets, and instructions needed to run the project
- an open-source license visible on the repository
- a text description explaining the project
- external hosting / a fully published application
- access sufficient for judging and testing

The project must also be original work and comply with third-party API, SDK, data, and license requirements. 

## 3. Discover's Core Hackathon Thesis

Discover should communicate one central idea:

> **Generic AI can reason about what you say you want. Discover uses cultural intelligence to understand what you are likely to discover next.**

The product is not simply:

    User → LLM → recommendation

It is:

    User conversation
        ↓
    Intent + context
        ↓
    Agent identifies meaningful gaps
        ↓
    Entity/tag/location grounding
        ↓
    Qloo cultural intelligence
        ↓
    Cross-domain discovery
        ↓
    Explanation + refinement

Qloo therefore sits inside the core decision path rather than being a decorative API integration.

## 4. Why Qloo Must Be Essential

A reviewer should be able to remove Qloo from the architecture and immediately see a meaningful loss of functionality.

Without Qloo, Discover should lose capabilities such as:

- culturally grounded cross-domain discovery
- Qloo entity and tag grounding
- affinity-based recommendation signals
- Qloo location intelligence
- Qloo explainability metadata
- cross-domain connections between interests and discovery targets

The LLM remains responsible for language understanding, planning, clarification, and orchestration.

Qloo supplies cultural intelligence that the LLM should not be assumed to possess.

## 5. Product Scope for the Submission

The initial submission should focus on four coherent modes:

### Discover for Me

Personalized discovery across domains such as:

- movies and TV
- music
- dining
- places
- products
- brands
- experiences
- travel-related discovery

### Discover for Someone Else

Gift and experience discovery based on another person's tastes.

The agent should gather useful information rather than requiring the user to know a recommendation taxonomy.

### Discover for Community

Discovery for groups and communities.

The product should use provided cultural context without treating geography or demographic labels as deterministic proxies for individual taste.

### Discover for Business

Cultural and market discovery for businesses.

Potential flows include:

- target-market discovery
- cultural fit
- location-aware discovery
- brand/audience exploration
- product or experience discovery

## 6. Agentic Behavior

Discover must visibly behave like an agentic application.

The agent should:

1. interpret natural language
2. maintain structured state
3. identify missing information
4. ask targeted questions when useful
5. resolve entities/tags/locations
6. select appropriate tools
7. construct Qloo discovery requests
8. evaluate results
9. refine when necessary
10. explain results
11. stop when the request is sufficiently answered

The product should not merely make one LLM call followed by one Qloo call.

## 7. Agent Transparency

The interface should expose useful progress without exposing implementation noise.

Good user-facing states:

    Understanding your request
    Checking your preferences
    Finding cultural connections
    Exploring related discoveries
    Refining the results

Avoid exposing:

- raw API URLs
- API keys
- internal prompt text
- provider-specific request syntax
- internal stack traces

The goal is to demonstrate agency while preserving a coherent product experience.

## 8. Technological Implementation Focus

The published criterion asks how thoroughly and skillfully the project uses Qloo and whether the implementation is genuine and non-trivial. 

Discover should therefore demonstrate several meaningful Qloo capabilities rather than one simple recommendation request.

Target integration areas:

- entity resolution
- tag-based interests
- entity-based interests
- weighted signals
- location intelligence
- filters
- cross-domain discovery
- explainability
- iterative refinement

The exact set used in production should follow the current Qloo API capabilities and supported entity types.

## 9. Qloo Integration Demonstration

A strong primary demo should show the complete path:

    User:
    "I want something my friend would love for her birthday.
     She loves slow-burn dramas, jazz, and intimate restaurants."

    ↓

    Agent:
    Identifies recipient + interests + occasion

    ↓

    Entity/Tag Resolution:
    Maps natural language into Qloo-compatible signals

    ↓

    Qloo:
    Cross-domain cultural discovery

    ↓

    Agent:
    Interprets results

    ↓

    UI:
    Presents discoveries with explanations

    ↓

    User:
    "Make it less expensive and more relaxed."

    ↓

    Agent:
    Updates constraints and refines discovery

This demonstrates that Qloo is part of an iterative agent loop.

## 10. Design Strategy

The published Design criterion asks whether the project delivers a complete and coherent product experience rather than a technical proof of concept. 

The frontend should therefore feel like a real discovery product.

The primary screen should make three things obvious:

1. what the user can discover
2. how they can describe what they want
3. what the agent is currently doing

The interface should not require the user to understand Qloo.

## 11. Discovery Workspace

The main discovery workspace should contain:

- conversation/input area
- optional voice input
- current context summary
- follow-up questions
- agent activity state
- recommendation results
- explanation
- refinement input

The user should be able to continue naturally instead of restarting the search for every refinement.

## 12. Result Quality Presentation

Each recommendation should communicate:

- what it is
- why it appeared
- relevant cultural connections
- useful metadata
- source/provider context where appropriate
- actionable details when available

Avoid claiming certainty where the underlying data does not support it.

## 13. Potential Impact

The published Potential Impact criterion asks whether the project makes a credible and specific case for a real audience and whether the demonstrated solution addresses that problem. 

Discover should communicate a concrete problem:

> People often know what they like, but discovering what they might like next across unrelated cultural categories is difficult.

The problem becomes more difficult when:

- the recommendation is for another person
- the request spans multiple cultural categories
- the user cannot express their preferences in recommendation-system terminology
- location changes the cultural context
- the user wants discovery rather than a simple keyword search

Discover addresses this through conversational preference extraction plus cultural intelligence.

## 14. Quality of the Idea

The published Quality of the Idea criterion asks whether the use of Qloo is creative and non-obvious and whether the team demonstrates genuine understanding of the problem space. 

The product concept should therefore emphasize the broader discovery problem rather than presenting itself as another generic recommendation chatbot.

The distinctive idea is:

> **Discovery is an agentic process that starts with human context and uses cultural intelligence to traverse domains.**

This allows one conversation to connect:

    person
      ↓
    tastes
      ↓
    cultural signals
      ↓
    entities/tags
      ↓
    places/products/experiences/content
      ↓
    new discovery

## 15. Cross-Domain Story

Cross-domain discovery should be central to the demo.

For example:

    "I like the atmosphere of Succession,
     modern jazz,
     minimalist design,
     and quiet restaurants."

The agent should be able to treat these as connected cultural signals rather than independent search terms.

The exact resulting recommendations must come from the actual Qloo response and current supported API behavior.

## 16. Personalization Without PII Dependence

Discover should not require extensive personal data.

The product can demonstrate personalization from:

- stated preferences
- conversation context
- selected entities
- selected tags
- location supplied for the request
- explicit constraints

This keeps the product aligned with the principle that cultural discovery does not require building an identity profile.

## 17. Business Mode Demonstration

Business discovery provides a second important product story.

Example:

    "I run a premium coffee brand.
     We are exploring a new city and want to understand
     what cultural signals and experiences align with our brand."

The agent can clarify:

- target market
- brand identity
- price positioning
- category
- location

Then use Qloo to investigate cultural relationships and discovery opportunities.

This demonstrates that Qloo can support discovery beyond consumer recommendations.

## 18. Demo Strategy

The live demo should show one primary journey deeply rather than rapidly clicking through every feature.

Recommended primary journey:

    Discover for Someone Else
          ↓
    Natural-language request
          ↓
    Agent asks one useful question
          ↓
    Entity/tag resolution
          ↓
    Qloo discovery
          ↓
    Results + explanations
          ↓
    Natural-language refinement
          ↓
    Updated results

Secondary demonstrations can show:

- Discover for Me
- Discover for Business
- location-aware discovery
- voice input

## 19. Demo Reliability

The live demo must be treated as a production system.

Before submission:

- verify the deployment
- verify Qloo credentials
- verify LLM credentials
- verify database connectivity
- test the primary journey repeatedly
- test provider failures
- test empty results
- test refinement
- test authentication where applicable
- test from a clean browser session

The official rules require a functional application available for judging/testing, and judges may choose to evaluate based on the submission materials if they do not test the project themselves. 

## 20. Submission Repository

The repository should contain:

    README.md
    REQUIREMENTS.md
    LICENSE
    backend/
    frontend/
    docs/
    tests/
    .env.example

The README should quickly explain:

- what Discover is
- why it exists
- how Qloo is used
- architecture
- setup
- environment variables
- running locally
- testing
- live demo
- major discovery modes

The official rules require the public repository to contain the necessary source code, assets, and instructions and to include an open-source license. 

## 21. Devpost Submission Content

The final submission should clearly communicate:

### What is Discover?

One concise product description.

### The problem

Why generic recommendation/search experiences are insufficient for this problem.

### The solution

How the agent converts natural conversation into culturally grounded discovery.

### Why Qloo?

Exactly which parts depend on Qloo.

### How the agent works

A short workflow diagram.

### Key features

The five discovery modes and refinement.

### Technical implementation

The architecture and major components.

### Demo

The public URL and testing instructions.

## 22. Avoiding the "LLM Wrapper" Perception

The project should avoid an architecture where:

    LLM
      ↓
    generic recommendation text
      ↓
    Qloo API call added afterward

Instead:

    LLM
      ↕
    structured state
      ↕
    tools
      ↕
    Qloo

Qloo results should influence what the agent presents and how it refines discovery.

## 23. Avoiding the "Qloo Demo Only" Perception

The opposite problem should also be avoided.

Discover should not become:

    form
      ↓
    Qloo API
      ↓
    grid of results

The agent must add meaningful value through:

- conversational interpretation
- missing-information detection
- entity resolution
- cross-domain reasoning
- refinement
- explanation

## 24. Evidence of Genuine Qloo Use

The final demo and documentation should make Qloo usage inspectable.

Useful evidence includes:

- Qloo adapter code
- internal request model
- entity-resolution flow
- Qloo-backed result metadata
- explainability data where available
- documented Qloo calls
- architecture diagram
- live Qloo-powered behavior

Do not expose credentials or private provider responses.

## 25. Requirement Traceability

Each official requirement should map to an implementation artifact.

| Requirement | Discover artifact |
|---|---|
| Working application | Production deployment |
| Qloo integration | Qloo adapter + discovery flow |
| Agentic behavior | Agent orchestrator + tools |
| Functional demo | Public deployment |
| Public repository | GitHub repository |
| Open-source license | LICENSE |
| Source/instructions | README + docs |
| Text description | README + Devpost submission |
| External hosting | Frontend/backend deployment |
| Test access | Public demo/testing instructions |

The rules and submission page should be checked again immediately before submission because official terms can change. 

## 26. Judging-Criteria Traceability

| Published criterion | What Discover should visibly demonstrate |
|---|---|
| Technological Implementation | Non-trivial Qloo integration, agent tools, entity/tag/location grounding, iterative discovery |
| Design | Complete discovery workspace and coherent user journey |
| Potential Impact | Concrete discovery problems for individuals, gift-givers, communities, and businesses |
| Quality of the Idea | Cultural intelligence as the foundation for agentic cross-domain discovery |

The criteria are equally weighted in Stage Two. 

## 27. Implementation Priorities

The implementation order should prioritize the capabilities that prove the product thesis.

### Priority 1 — Core Agent

- DiscoveryState
- agent loop
- structured decisions
- tool registry
- bounded execution

### Priority 2 — Qloo Core

- entity resolution
- tags
- Insights
- cross-domain interests
- explainability
- normalized results

### Priority 3 — Primary UX

- discovery workspace
- follow-up questions
- results
- explanations
- refinement

### Priority 4 — Persistence

- users
- sessions
- history
- saved discoveries

### Priority 5 — Additional Modes

- gift
- community
- business

### Priority 6 — Voice and Current Information

- voice input
- current-information boundary

### Priority 7 — Hardening

- testing
- rate limits
- logging
- deployment
- security
- performance

## 28. Scope Control

The project should not expand simply because a feature is technically interesting.

A feature belongs in the initial submission when it strengthens at least one of:

- Qloo integration
- agentic behavior
- discovery quality
- user experience
- demonstrated impact

Otherwise it should be considered for post-hackathon work.

## 29. Submission Timeline

The official submission deadline is October 30, 2026 at 11:45 PM EDT. 

Recommended internal milestones:

### Phase 1 — Architecture

Complete:

- requirements
- architecture
- Qloo contract
- deployment
- testing strategy

### Phase 2 — Vertical Slice

Build one complete journey:

    conversation
      ↓
    agent
      ↓
    Qloo
      ↓
    result
      ↓
    refinement

Do not wait until every mode is implemented before testing the core loop.

### Phase 3 — Product Expansion

Add:

- additional discovery modes
- persistence
- history
- saved discoveries
- voice
- current-information integration

### Phase 4 — Hardening

Complete:

- automated tests
- deployment
- error handling
- performance checks
- security checks
- UI polish

### Phase 5 — Submission

Before the deadline:

- freeze a stable demo
- verify public repository
- verify license
- verify documentation
- verify live demo
- prepare Devpost description
- verify testing instructions
- perform a final rules check

## 30. Demo Narrative

The demo should tell one coherent story:

> "Tell Discover what matters to you. It asks only what it needs to know, understands the cultural signals behind your request, explores connections across domains, and helps you discover something you might not have searched for directly."

Then demonstrate:

    Natural request
        ↓
    Clarification
        ↓
    Cultural grounding
        ↓
    Discovery
        ↓
    Explanation
        ↓
    Refinement

This narrative should remain consistent across the UI, README, architecture documentation, and Devpost submission.

## 31. What Success Means for the Project

The project should be considered submission-ready when a new user can:

1. open the public application
2. understand what Discover does without reading technical documentation
3. describe a discovery goal naturally
4. receive useful clarification when necessary
5. see evidence of agentic processing
6. receive Qloo-grounded discoveries
7. understand why results were surfaced
8. refine the request naturally
9. receive updated results
10. complete the primary journey without developer intervention

## 32. Final Strategic Principle

The project should not try to demonstrate every capability Qloo provides.

It should demonstrate a coherent product where Qloo changes what the agent can do.

The central principle is:

> **Do not build a chatbot that happens to call Qloo. Build a discovery agent whose intelligence depends on Qloo's cultural grounding.**


---

# Alignment addendum (REQUIREMENTS v1.0)

- **Scope is fixed.** Earlier "scope control" language that suggested deferring features is superseded: all features in REQUIREMENTS stay in scope; priority tiers (P0/P1/P2) only set build order (REQUIREMENTS §0.2).
- **Schedule:** use REQUIREMENTS §14 (29 days, tracks A–G, milestones M0–M7). Re-verify the deadline and rules before submission (HCK-006).
- **Demo data:** the demo video and hosted demo must use the `live` profile; `mock` data is for development only (HCK-003, UX-105).
