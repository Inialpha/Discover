# Discover

> **Discover what you'll love next.**

Discover is an agentic cultural intelligence platform that turns natural-language conversations into personalized discovery.

Instead of asking only "What is similar to this?", Discover explores a broader question:

> **Given what matters to me, this person, this community, or this business, what should I discover next?**

Discover uses a lightweight custom agent to understand intent, identify meaningful preferences and constraints, ask follow-up questions when necessary, resolve relevant entities, use **Qloo's cultural intelligence** to generate cross-domain recommendations, evaluate the results, and explain why each discovery fits.

## Why Discover?

Most recommendation experiences begin with a narrow request: a product, movie, restaurant, song, or place.

Discover starts with **context**.

A conversation can contain several signals at once:

- favorite movies and TV shows
- music and artists
- fashion and brands
- food and restaurants
- places and travel interests
- lifestyle preferences
- budget and practical constraints
- the intended audience or recipient
- geographic context
- business or market goals

The agent turns those signals into a structured discovery problem and uses Qloo to connect preferences across cultural categories.

## Discovery Modes

### Discover for Me

Personalized discovery based on the user's own tastes and context.

Examples:
- "I like *Suits*, *Normal People*, and Taylor Swift. What else might I enjoy?"
- "I want somewhere in Lagos that fits my taste in music, food, and atmosphere."
- "Based on the things I usually like, what brands or experiences should I explore?"

### Discover for Someone Else

Discovery for another person or a specific occasion.

Examples:
- birthday gifts
- experiences for a partner or friend
- products for a family member
- recommendations for someone described through natural language

The agent can ask targeted questions such as budget, location, interests, or whether the user wants a physical product or an experience.

### Discover for a Group

Blended discovery for two or more specific people planning something together.

Examples:
- a Friday outing that works for four friends with different tastes
- a team dinner that fits everyone's preferences
- invite friends by link so they can add their own tastes

Discover shows who each result fits best, and which tastes are shared versus unique.

### Discover for Community

Discovery for groups and local audiences.

Examples:
- culturally relevant experiences for a community
- places or activities for a group with shared interests
- understanding what kinds of cultural experiences may resonate with a particular audience

Discover treats location and community as context, not as a substitute for individual taste.

### Discover for Business

Cultural intelligence for businesses.

Examples:
- exploring a new market
- identifying culturally relevant audiences
- discovering products, experiences, or categories that may fit a market
- exploring relationships between a brand's existing audience and adjacent cultural categories

This mode is particularly important for demonstrating Qloo's value beyond consumer recommendations.

## How It Works

At a high level:

```text
User
  |
  v
Text / Voice
  |
  v
Discovery Agent
  |
  +--> Understand intent and mode
  +--> Extract preferences, goals and constraints
  +--> Identify missing information
  +--> Ask targeted follow-up questions
  +--> Resolve entities
  +--> Build a Qloo discovery request
  +--> Query Qloo
  +--> Evaluate and refine results
  +--> Explain the discoveries
  |
  v
Personalized Discovery
```

The agent is intentionally implemented as a **lightweight custom orchestration loop**, rather than depending on LangChain or LangGraph. This keeps the runtime small and gives the application direct control over state, tool execution, limits, retries, and Qloo-specific behavior.

## Qloo Integration

Qloo is a core part of Discover's discovery engine, not an optional enrichment step.

Discover is designed around Qloo's ability to connect cultural preferences across domains and provide recommendations based on signals that may not belong to the same category as the requested result.

Discover will use a Qloo adapter so that the agent works with a stable internal interface rather than raw Qloo HTTP syntax.

The intended flow is:

1. Understand the user's discovery goal.
2. Extract relevant cultural signals and constraints.
3. Resolve natural-language entities where necessary.
4. Construct a Qloo request from the structured discovery state.
5. Retrieve Qloo insights.
6. Evaluate whether the results answer the user's actual goal.
7. Refine the discovery when additional Qloo queries can materially improve the result.
8. Present results with clear explanations.

See the [Qloo API documentation](https://docs.qloo.com/reference/api-overview) for the API reference.

## Architecture Direction

The planned application is split into a frontend and a lightweight backend:

```text
+-------------------+
|     Frontend      |
| Web discovery UI  |
| Voice / Text      |
+---------+---------+
          |
          | HTTPS
          v
+-------------------+
|   FastAPI API     |
|                   |
| Auth / Sessions   |
| Discovery API     |
| Agent Orchestrator|
| Qloo Adapter      |
| LLM Adapter       |
+----+---------+----+
     |         |
     v         v
  Qloo API   Hosted LLM
     |
     v
External discovery data

          +
          |
          v
      PostgreSQL
```

The backend should remain thin. Heavy AI inference, Qloo intelligence, and speech processing should be delegated to external services rather than running local models.

## Technology Direction

| Layer | Initial direction |
|---|---|
| Frontend | React + TypeScript |
| Backend | Python + FastAPI |
| Agent | Custom bounded orchestration loop |
| Cultural intelligence | Qloo API |
| LLM | OpenAI-compatible hosted model |
| Database | PostgreSQL |
| HTTP client | httpx |
| Container | Docker |
| Runtime | Python 3.12 |
| Initial Docker base | python:3.12-slim |

The exact implementation can evolve as the detailed architecture is documented.

## Core Engineering Principles

- **Qloo must materially influence discovery outcomes.**
- **Natural language first:** users should not need to understand Qloo's API.
- **Stateful discovery:** conversation context is separated from structured discovery state.
- **Bounded agents:** every agent run has explicit step and timeout limits.
- **Explainable results:** users should understand why a discovery was returned.
- **Minimal data:** collect only what is needed for the discovery experience.
- **Lightweight runtime:** avoid unnecessary framework and dependency overhead.
- **Documentation before implementation:** architectural decisions are recorded before major coding begins.
- **Iterative design:** requirements and architecture are living documents.

## Beyond Recommendations

- **Live agent timeline:** watch the agent work (understanding, looking up, querying Qloo, evaluating) as it happens, over streaming responses.
- **Evidence you can trust:** every explanation separates what a data source returned from what the agent interpreted.
- **Compare and trends:** compare audiences, markets, or tastes, and explore change over time.
- **Business reports:** structured reports exportable as PDF, Markdown, CSV, JSON, or HTML.
- **Shareable pages:** revocable, read-only snapshots of results or reports, with privacy controls.
- **Guest-first:** start instantly; sign in to keep history and saved discoveries.

## Project Status

**Requirements v1.0 are baselined and the project is ready to begin implementation (milestone M0).**

[REQUIREMENTS.md](./REQUIREMENTS.md) is the canonical specification: taxonomy, functional requirements, UX, API and streaming protocol, data model, test profiles, delivery plan, and decision register. Detail documents under [`docs/`](./docs) elaborate it and defer to it. Architectural decisions are recorded in [`docs/01-decisions/decision-records.md`](./docs/01-decisions/decision-records.md).

No Qloo API key is required to start: the `mock` profile runs the whole product against scripted, clearly labelled synthetic data. When keys are available, the `record` profile captures real responses for regression tests (see REQUIREMENTS §11).

## Repository

- GitHub: https://github.com/Inialpha/Discover
- License: MIT

## Hackathon

Discover is being developed for the **Qloo Agentic Hackathon 2026**.

The implementation is intended to satisfy the hackathon's core expectations:

- meaningful Qloo API integration
- genuine agentic behavior
- publicly accessible source code
- open-source licensing
- externally hosted demonstration
- a clear, usable product experience

## Documentation

Start with [REQUIREMENTS.md](./REQUIREMENTS.md), then see the [documentation index](./docs/README.md).

---

**Discover what you'll love next.**