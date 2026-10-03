# Frontend Architecture

> **Alignment:** This is a detail document. The canonical requirements, enums (modes, intents, statuses, result kinds), API surface, and SSE protocol are in [`REQUIREMENTS.md`](../../REQUIREMENTS.md). If anything here conflicts with it, `REQUIREMENTS.md` wins and this document must be corrected. Decisions: [`docs/01-decisions/decision-records.md`](../01-decisions/decision-records.md). Routes, workspace layout, timeline, result presentation, and per-mode UI: REQUIREMENTS §6.

## 1. Purpose

This document defines the frontend architecture and user experience for Discover.

The frontend is not a generic chatbot shell. It is a discovery workspace designed around the complete agentic journey:

    intent
      ↓
    conversation
      ↓
    clarification
      ↓
    cultural discovery
      ↓
    results
      ↓
    explanation
      ↓
    refinement
      ↓
    save / continue / discover again

The frontend must make this process understandable without exposing Qloo syntax, API mechanics, agent internals, or hidden reasoning.

## 2. Frontend Goals

The frontend should:

- make natural-language discovery feel effortless
- support text and voice input
- show when Discover needs clarification
- make recommendations visually scannable
- explain why results were selected
- allow users to refine results without restarting
- support the five discovery modes
- preserve session context
- make saved discoveries and history easy to revisit
- work well on mobile and desktop
- remain lightweight enough for inexpensive deployment

## 3. Product Experience

The central experience is the Discovery Workspace.

A user should be able to start with something as broad as:

    I want to find a movie for tonight. I like intelligent thrillers,
    but I don't want anything too depressing.

Discover may respond with one useful question:

    Do you want something more psychological or more action-driven?

After the user answers, the interface should transition naturally into results.

The user should never need to manually construct a Qloo query.

## 4. Application Structure

Initial frontend structure:

    App
    ├── Landing / Home
    ├── Discovery Workspace
    │   ├── Conversation
    │   ├── Context Summary
    │   ├── Follow-up Question
    │   ├── Progress / Activity
    │   ├── Results
    │   └── Refinement
    ├── History
    ├── Saved
    └── Settings

Authentication UI may wrap these views when accounts are enabled.

## 5. Primary Navigation

The navigation should remain simple.

Desktop:

    Discover
    ├── Home
    ├── History
    ├── Saved
    └── Settings

Mobile:

    Home     History     Saved     Settings

The active discovery session should not disappear when the user navigates away accidentally. The frontend should preserve the session ID and restore the workspace when appropriate.

## 6. Home

The home screen is the starting point for discovery.

Primary elements:

1. product identity
2. concise value proposition
3. discovery input
4. optional mode selection
5. example prompts
6. recent discoveries when available

Example:

    Discover what you'll love next.

    Tell me what you're looking for.

    [ What should I discover for you?            🎙 ]

    Try:
    • Find a movie based on my taste in music
    • Help me choose a birthday gift for my sister
    • What should our community experience this weekend?
    • Help me explore a new market for this product

The interface should encourage natural language rather than forcing a form.

## 7. Discovery Modes

The five modes should be visible but should not make the product feel like five unrelated applications.

Modes:

- Discover for Me
- Discover for Someone Else
- Discover for Community
- Discover for Business

A mode can be selected explicitly, but the agent should also be able to infer the intended mode from natural language and confirm it when ambiguity matters.

Example:

    Help me find a birthday gift for my brother.

The frontend may infer:

    Discover for Someone Else

without forcing the user to select a mode first.

## 8. Discovery Workspace

The workspace is the most important screen.

Conceptual layout:

    ┌──────────────────────────────────────────────────────────────┐
    │ Discover                                      Session menu  │
    ├───────────────────────┬──────────────────────────────────────┤
    │                       │                                      │
    │ Conversation          │ Context / Discovery                  │
    │                       │                                      │
    │ User message          │ What I know                          │
    │ Assistant question    │ • interests                          │
    │ User answer           │ • constraints                        │
    │                       │ • location                            │
    │                       │                                      │
    │                       │ Results                               │
    │                       │ [card] [card] [card]                 │
    │                       │ [card] [card] [card]                 │
    │                       │                                      │
    ├───────────────────────┴──────────────────────────────────────┤
    │ Message...                                  🎙       Send    │
    └──────────────────────────────────────────────────────────────┘

On mobile, the layout becomes a single vertical flow:

    Conversation
    ↓
    Context
    ↓
    Results
    ↓
    Refine
    ↓
    Input

The result section should become prominent after discovery begins.

## 9. Conversation Interface

Messages should visually distinguish:

- user messages
- Discover responses
- follow-up questions
- status/activity messages

Discover should avoid exposing internal tool execution.

Instead of:

    Calling Qloo /search...

show:

    Understanding your taste...

or, when useful:

    Exploring connections across movies, music, and places...

Activity text should communicate useful progress without pretending the model has human-like internal experiences.

## 10. Follow-up Questions

When the agent needs more information, the UI should make the question the focal interaction.

Example:

    What kind of experience are you looking for?

    [ Relaxing ] [ Adventurous ] [ Social ] [ Something new ]

    You can also type your own answer.

Structured answer chips are optional.

The user must always be able to provide a natural-language answer.

Follow-up questions should not feel like a questionnaire. The backend decides whether clarification is materially useful; the frontend simply makes the question easy to answer.

## 11. Context Summary

The workspace should expose a compact representation of what Discover currently understands.

Example:

    Your discovery
    ────────────────
    Looking for: weekend experience
    Mood: adventurous
    Interested in: live music, food
    Location: Calabar
    Budget: moderate

Users should be able to correct important context.

For example:

    Location   Calabar        Edit
    Budget     Moderate       Edit
    Mood       Adventurous    Edit

Edits should produce a new user-visible state change rather than silently modifying hidden agent state.

## 12. Agent Activity

Agent activity should be concise and state-based.

Possible states:

    Understanding your request
    Finding relevant connections
    Exploring cultural matches
    Comparing discoveries
    Preparing recommendations

The frontend should not expose:

- hidden reasoning
- raw prompts
- raw tool calls
- API keys
- provider transport details
- internal confidence calculations

If an operation fails, the UI should present a user-relevant explanation and recovery action.

## 13. Results Interface

Results are the main product output.

Each result should contain enough information to decide whether to explore it.

Conceptual result card:

    ┌──────────────────────────────────┐
    │ [image]                          │
    │                                  │
    │ Title                            │
    │ Type / category                  │
    │                                  │
    │ Why this fits                    │
    │ A concise explanation connecting │
    │ the result to the user's taste.  │
    │                                  │
    │ [ Explore ]   [ Save ]           │
    └──────────────────────────────────┘

Result cards should prioritize:

1. identity
2. visual recognition
3. relevance explanation
4. useful metadata
5. next action

The interface should avoid displaying provider-specific scores unless they have a clear user-facing meaning.

## 14. Explainability

Discover should make recommendations feel grounded rather than arbitrary.

Each recommendation can expose a concise explanation such as:

    Why this fits

    You mentioned psychological thrillers and
    stories with morally complex characters.
    This recommendation connects both preferences.

If Qloo provides explainability metadata, the backend converts it into a product-facing explanation.

The frontend does not interpret raw Qloo explainability structures directly.

## 15. Result Detail

Selecting a result opens a detail view or expanded card.

Potential information:

- name
- image
- category
- description
- why it fits
- location
- rating when available and meaningful
- external link
- related discoveries
- save action

The result detail should remain focused on helping the user decide what to discover next.

## 16. Refinement

After results appear, the user should be able to continue naturally.

Examples:

    Show me something less expensive.

    Give me options with a more relaxed atmosphere.

    I like these. What else connects to this style?

The frontend sends these as additional messages against the same session.

A refinement should preserve the previous context unless the user explicitly changes it.

The UI may provide quick refinement controls:

    Refine:
    [ More like this ] [ More affordable ] [ More unusual ]
    [ Different mood ] [ Different location ]

These controls are optional shortcuts, not replacements for natural conversation.

## 17. Empty Results

An empty-result state should not simply say "No results."

Example:

    I couldn't find a strong match with those constraints.

    We can try:
    [ Broaden the budget ]
    [ Try a nearby location ]
    [ Relax one preference ]
    [ Start a different search ]

The backend may also return a clarification request when the constraints are too restrictive.

## 18. Errors

Errors should be classified into user-relevant categories.

### Temporary service failure

    Something went wrong while searching.

    [ Try again ]

### Invalid request

    I couldn't understand part of that request.

    [ Rephrase ]

### Provider unavailable

Do not expose Qloo implementation details unless necessary.

    The discovery service is temporarily unavailable.

    [ Try again ]

### Session unavailable

    This discovery session is no longer available.

    [ Start a new discovery ]

Technical details belong in logs, not normal user-facing messages.

## 19. Voice Input

Voice is an input channel, not a separate discovery workflow.

Conceptual interaction:

    Idle
      ↓
    Tap microphone
      ↓
    Recording
      ↓
    Transcribing
      ↓
    Text appears in composer
      ↓
    User reviews
      ↓
    Send

The user should be able to edit the transcript before sending.

The initial version does not require continuous voice conversation.

Voice output is not required for the initial MVP.

## 20. Composer

The message composer should support:

- multiline text
- microphone button
- send button
- disabled/loading state
- keyboard-friendly submission
- transcript editing

While Discover is processing:

    [ Understanding...                         ]

The user should not accidentally submit duplicate requests.

## 21. Loading and Streaming

The frontend should support normal request/response behavior first.

If backend streaming is later introduced, the UI can progressively update:

    message accepted
    → activity state
    → question or result

The architecture should not require streaming for correctness.

This keeps the initial implementation simple and compatible with inexpensive hosting.

## 22. History

History should show completed or previously active discovery sessions.

Example:

    History

    Today
    • Weekend experiences in Calabar
    • Movie for tonight

    Yesterday
    • Birthday gift for my brother
    • New restaurant ideas

    [ Search history ]

Each entry should show:

- title
- mode
- date
- optional short summary

Selecting an entry restores the discovery workspace.

History search should be added only if the number of sessions makes it useful.

## 23. Saved Discoveries

Saved is different from history.

History answers:

    What did I explore?

Saved answers:

    What do I want to keep?

Saved cards should contain:

- result identity
- image
- short reason
- saved date
- note when available
- link back to the original discovery

Users should be able to remove saved items directly.

## 24. Settings

Initial settings should remain minimal.

Potential settings:

- account
- default result count
- preferred discovery domains
- default location
- response style
- privacy/data controls
- sign out

Settings should not expose technical configuration such as Qloo API settings or model provider selection.

## 25. Authentication

Authentication should not dominate the first-use experience.

If anonymous discovery is enabled, users can begin discovering immediately.

Account authentication becomes valuable for:

- history synchronization
- saved discoveries
- persistent preferences
- multi-device access

The frontend should treat authentication as a product capability rather than a prerequisite for understanding Discover.

## 26. Responsive Design

The primary target is responsive web.

### Mobile

Priorities:

- single-column layout
- large touch targets
- bottom navigation
- sticky composer
- compact context summary
- vertically stacked result cards

### Desktop

Priorities:

- wider discovery workspace
- conversation/context split
- multi-column results
- keyboard navigation
- persistent refinement controls

The same product concepts should work at both sizes.

## 27. Accessibility

The frontend should provide:

- semantic HTML
- keyboard navigation
- visible focus states
- accessible labels for icon buttons
- sufficient text contrast
- screen-reader-friendly result cards
- reduced-motion support
- error messages associated with the relevant controls
- buttons that communicate their current state

Voice controls must always have a non-voice alternative.

## 28. Visual Direction

Discover should feel like a modern cultural discovery product rather than a developer tool.

Visual priorities:

- strong typography
- generous spacing
- clear hierarchy
- high-quality imagery
- restrained use of color
- subtle motion
- readable cards
- clear conversational states

Avoid:

- generic AI purple gradients
- excessive glassmorphism
- dense dashboards
- terminal-like UI
- unnecessary animated effects
- visually dominant technical status information

The visual system should be established as reusable design tokens before building individual pages.

## 29. Frontend State

Frontend state should be separated into:

### Server state

- session
- messages
- discovery state
- results
- history
- saved discoveries

### UI state

- selected result
- open/closed panels
- composer contents
- microphone state
- loading state
- transient error state

The frontend should not duplicate the backend's agent state machine.

The backend remains the source of truth for discovery state.

## 30. Session Synchronization

The frontend should track:

    session_id
    last_known_state_version
    last_message_sequence

When a request succeeds, the response should update the local session representation.

If the backend reports a state conflict, the frontend should refresh the session and avoid blindly overwriting newer state.

## 31. API Boundary

The frontend communicates only with the Discover backend.

It should not call Qloo directly.

Conceptual flow:

    Frontend
       ↓
    Discover API
       ↓
    Agent / Discovery Services
       ↓
    Qloo

This keeps:

- Qloo credentials private
- Qloo request construction centralized
- business rules on the backend
- provider changes isolated from the frontend

## 32. API Client

The frontend should have one typed API client boundary.

Conceptual methods:

    createDiscovery()
    sendDiscoveryMessage(sessionId, message)
    getDiscovery(sessionId)
    deleteDiscovery(sessionId)

    getHistory()
    getHistoryItem(id)

    saveDiscovery(resultId, snapshot)
    getSavedDiscoveries()
    deleteSavedDiscovery(id)

Components should not construct raw fetch requests independently.

## 33. Frontend Data Contracts

The frontend should consume product-level contracts such as:

    DiscoverySession
    DiscoveryMessage
    DiscoveryStateSummary
    DiscoveryQuestion
    DiscoveryResult
    DiscoveryExplanation
    SavedDiscovery
    HistoryItem

These should correspond to backend response schemas but should not expose database models directly.

## 34. Result Rendering

Result rendering should be domain-aware but generic.

A result may represent:

- movie
- music
- restaurant
- place
- product
- brand
- event
- experience

The card should render the common structure first and use optional domain metadata when available.

This avoids creating separate applications for every cultural category.

## 35. Security

The frontend must:

- never contain Qloo API keys
- never contain database credentials
- never expose server secrets
- validate user-controlled route parameters before use
- avoid rendering untrusted HTML
- safely handle external URLs
- use HTTPS in production
- respect authentication state
- avoid storing sensitive session information unnecessarily in local storage

Authentication tokens should follow the selected authentication architecture rather than being improvised inside UI components.

## 36. Performance

Initial performance priorities:

1. fast first render
2. small JavaScript payload
3. optimized result images
4. lazy loading for non-visible results
5. minimal client-side dependencies
6. avoid unnecessary global state
7. avoid loading history/saved data before it is needed

The frontend should not ship large AI or data-processing libraries to the browser.

## 37. Deployment

The frontend should be deployable as a lightweight web application.

Requirements:

- production build
- environment-based API base URL
- no secrets embedded in client code
- HTTPS
- configurable CORS origin on backend
- predictable build command
- preview deployment support

Vercel or an equivalent static/frontend hosting platform is suitable for the initial architecture.

## 38. Testing Architecture

Frontend tests should be organized around user behavior.

### Component tests

Test:

- composer
- result card
- explanation
- follow-up question
- context summary
- navigation

### Integration tests

Test:

- creating a discovery
- sending a message
- receiving a follow-up question
- receiving results
- refining results
- saving a result
- restoring history

### End-to-end tests

At least one complete flow:

    Home
    → enter discovery request
    → answer clarification
    → receive results
    → open result
    → save result
    → reopen from saved

Voice should have a separate integration test using a mocked transcription boundary.

## 39. Error and Offline Behavior

The frontend should distinguish:

- network unavailable
- backend unavailable
- request timeout
- authentication expired
- invalid session
- empty results

For a temporary network failure, preserve unsent composer text so the user does not lose their request.

The frontend should never claim that a discovery completed unless the backend confirms it.

## 40. Frontend Implementation Structure

The exact framework can be finalized during implementation, but the code should preserve these boundaries:

    frontend/
    ├── app/
    ├── components/
    │   ├── discovery/
    │   ├── results/
    │   ├── history/
    │   ├── saved/
    │   └── shared/
    ├── lib/
    │   ├── api/
    │   ├── types/
    │   └── utils/
    ├── hooks/
    ├── state/
    ├── styles/
    └── tests/

Framework-specific conventions may adapt this structure.

## 41. Implementation Order

Frontend implementation should proceed in this order:

1. application shell and design tokens
2. API client and typed contracts
3. Home
4. Discovery Workspace
5. composer
6. conversation messages
7. follow-up questions
8. context summary
9. result cards
10. explanation UI
11. refinement
12. loading/error states
13. history
14. saved discoveries
15. settings
16. authentication integration
17. voice input
18. responsive refinement
19. accessibility pass
20. integration and end-to-end tests

This order ensures the core discovery loop works before secondary screens are polished.

## 42. Definition of Done

The frontend architecture is ready for implementation when:

- the Discovery Workspace is clearly defined
- the five discovery modes are represented
- text and voice input boundaries are defined
- follow-up questions have a dedicated interaction
- results and explanations have a common model
- refinement is supported without restarting a session
- history and saved discoveries are distinct
- frontend state is separated from backend agent state
- Qloo is never called directly by the browser
- responsive behavior is defined
- accessibility requirements are explicit
- testing covers the complete discovery loop
- deployment does not require client-side secrets

## 43. Architectural Summary

Discover's frontend should make a sophisticated agent feel simple.

The user speaks naturally. Discover asks only useful questions, explores cultural connections, presents understandable recommendations, explains why they fit, and lets the user continue refining.

The core design principle is:

> **The interface should expose the discovery journey, not the machinery behind it.**


---

# Alignment addendum (REQUIREMENTS v1.0)

- **Routes and pages:** REQUIREMENTS §6.1 (adds `/reports`, `/reports/:id`, `/compare`, `/s/:token`, `/join/:token`).
- **Modes:** five modes (`self`, `someone_else`, `group`, `community`, `business`); the earlier "four initial modes" is superseded.
- **Streaming:** a `useRun` hook built on `fetch` + SSE parsing (not `EventSource`), with automatic resume using `Last-Event-ID`, event validation against the exported JSON Schema, and an `AgentTimeline` component fed by the same event stream (UX-020..025). Progress is event-driven; there is no fake progress.
- **Results:** `ResultCard`, `EvidenceList`, detail drawer, influence view, lenses, map view, compare tray (UX-040..050).
- **Mode views:** Taste Canvas, Gift Brief, Group Board, Community Landscape, Business Workspace, all composed from shared components (UX-060..083).
- **Reports and sharing:** report viewer/editor, export menu, share dialog, public share page, print stylesheet (UX-090..094).
- **Demo data banner:** shown whenever `/meta` reports a non-`live` profile (UX-105).
- **Stack:** ADR-015.
