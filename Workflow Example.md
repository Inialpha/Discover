# Workflow Example

## Purpose

This document preserves the useful workflow examples and API reasoning from the Qloo documentation AI conversation stored in `workflow_example.txt`.

The original TXT file is intentionally left unchanged. This Markdown version is the working reference for the **Discover Market** product.

---

## 1. Product Direction

Discover is being narrowed from a general-purpose discovery application into a focused **market-discovery agent for businesses and marketers**.

The core problem:

> A business has a product, service, product idea, or campaign and wants to understand whether a culturally relevant market exists, who is likely to be interested, where that audience is concentrated, what else they care about, and how those signals can inform targeting and messaging.

The application should turn a natural-language business question into a structured research process using Qloo's cultural intelligence.

### Example business question

> "I want to sell handmade beaded bags in Nigeria. Who should I target, where are they, what other things do they care about, and how should I think about reaching them?"

The user should not need to know Qloo entity IDs, tag URNs, filter syntax, or signal syntax.

---

# 2. High-Level Workflow

~~~text
Business/Product Input
        |
        v
Understand Business Objective
        |
        v
Extract Product + Market Signals
        |
        v
Search / Resolve Entities
        |
        v
Search / Resolve Tags
        |
        v
Build Cultural Signal Set
        |
        v
Taste Analysis
        |
        v
Cross-Domain Affinity
        |
        +------------------+
        |                  |
        v                  v
Demographic Analysis    Geographic Heatmap
        |                  |
        +--------+---------+
                 |
                 v
        Audience Segmentation
                 |
                 v
        Audience Comparison
                 |
                 v
        Additional Qloo Research
                 |
                 v
        Evidence Aggregation
                 |
                 v
          LLM Synthesis
                 |
                 v
       Market Recommendation
~~~

The sequence is not necessarily rigid. The agent should decide which research steps are necessary and may return to an earlier step when the evidence is insufficient.

---

# 3. Step 1 — Understand the Business Input

The user can provide a product, existing business, brand, campaign, or product idea.

Examples:

- "I want to launch a premium African fashion brand."
- "I want to advertise a new skincare product in Lagos."
- "I am considering building a subscription service for African documentaries."
- "I already sell handmade beaded bags and want to find new customers in Nigeria."

The agent extracts:

| Information | Purpose |
|---|---|
| Product/service | What is being researched |
| Product attributes | Cultural and functional characteristics |
| Brand | Existing entity when available |
| Product category | Helps establish the market context |
| Competitors/comparable products | Provides additional cultural signals |
| Target market | Country, city, region, or broader market |
| Existing customer information | Optional starting signals |
| Existing persona | Hypothesis to validate or challenge |
| Business objective | Validation, advertising, expansion, positioning, etc. |
| Constraints | Price, location, audience restrictions, campaign goals |

The agent should distinguish between:

1. **Facts supplied by the user**
2. **Hypotheses supplied by the user**
3. **Signals discovered through Qloo**
4. **Recommendations inferred by the AI**

These must not be presented as the same thing.

---

# 4. Step 2 — Resolve the Product and Cultural Signals

The natural-language product description is not necessarily a valid Qloo signal.

For example:

> "handmade beaded bags"

may need to be represented through several Qloo entities and tags.

The agent should investigate the cultural representation of the product.

~~~text
Natural-language product
        |
        +--> Search entities
        |
        +--> Search tags
        |
        +--> Search tag types
        |
        +--> Search comparable brands/entities
        |
        v
Cultural Signal Set
~~~

Possible signals may include concepts such as:

- Fashion accessories
- Artisan
- Cultural heritage
- Premium
- Expressive
- Relevant fashion categories
- Comparable brands
- Related cultural interests

These are examples of possible signals, not hard-coded values. The actual Qloo API response should determine which entities and tags are valid.

---

# 5. Search / Entity Resolution

Use Qloo Search to resolve natural-language references into Qloo entities.

Potential entity types include:

- Brand
- Place
- Locality
- Artist
- Movie
- TV show
- Book
- Podcast
- Video game
- Person
- Other supported Qloo entity types

The important fields to retain include:

~~~yaml
entity:
  entity_id:
    type: string
    description: Qloo entity UUID used in downstream requests.
  name:
    type: string
    description: Human-readable entity name.
  types:
    type: array<string>
    description: Qloo entity types associated with the result.
  properties:
    type: object
    description: Entity-specific metadata.
  popularity:
    type: number
    description: Qloo popularity signal when returned.
  tags:
    type: array<object>
    description: Tags associated with the entity when available.
~~~

Search is primarily an **entity-resolution and lookup stage**. It should not be confused with the main cultural recommendation/insight stage.

---

# 6. Tag Resolution

Tags provide another way to represent a product or market.

The agent can search for tags that correspond to the product category or cultural concepts.

~~~text
Product description
       |
       v
Tag search
       |
       v
Relevant Qloo tag URNs
       |
       v
Validate / rank signals
       |
       v
Use selected tags in Insights
~~~

Important information:

- Tag ID / URN
- Tag name
- Tag type
- Relevance to the current business question

The application should not invent tag URNs.

---

# 7. Taste Analysis

Taste Analysis reverses the normal recommendation direction.

Instead of asking:

> "What entities are related to this tag?"

the workflow can investigate:

> "What cultural/taste signals characterize the audience associated with this entity?"

A common pattern is:

~~~text
Known entity
     |
     v
Insights with filter.type = urn:tag
     |
     v
Taste / psychographic tags
     |
     v
Audience cultural fingerprint
~~~

The resulting tags can become additional signals for later research.

Useful fields to retain include:

~~~yaml
taste_signal:
  tag_id:
    type: string
    description: Qloo tag identifier.
  name:
    type: string
    description: Human-readable tag name.
  affinity:
    type: number
    description: Strength of the relationship when returned by the response.
~~~

These signals can help answer:

> "What kind of cultural world surrounds this product or brand?"

---

# 8. Cross-Domain Affinity

Once the product or audience has been represented by Qloo entities and tags, the agent can investigate related entities across domains.

Examples:

~~~text
Product / Brand
      |
      +--> Movies
      +--> TV Shows
      +--> Artists
      +--> Brands
      +--> Places
      +--> Books
      +--> Podcasts
      +--> Other supported domains
~~~

This is important because a marketing audience is not defined by one product category.

A fashion audience may also have strong relationships with:

- Music
- Entertainment
- Places
- Other brands
- Lifestyle concepts

Those cross-domain relationships can provide evidence for positioning, creative direction, partnerships, and potential media environments.

Important response fields include:

~~~yaml
affinity_result:
  entity_id:
    type: string
  name:
    type: string
  subtype:
    type: string
  popularity:
    type: number
  query:
    type: object
    description: Qloo relationship metrics and explainability when returned.
  properties:
    type: object
    description: Entity-specific information.
~~~

The exact response structure must always be validated against the current Qloo API response.

---

# 9. Demographic Analysis

Demographics answer:

> "Who is associated with these cultural interests?"

Potential dimensions include:

- Age
- Gender
- Audience segments
- Audience-conditioned relationships

The workflow can compare multiple signals.

For example:

~~~text
Product signal
      +
Category signal
      +
Comparable entity
      |
      v
Demographic Insights
      |
      +--> Age distribution
      +--> Gender distribution
      +--> Audience relationships
~~~

The application should be able to distinguish:

- The demographic profile of the product/brand
- The demographic profile of the broader category
- The profile of a specific audience segment

This allows the AI to identify potential over-indexing rather than simply repeating a demographic number.

---

# 10. Audience Segmentation

Audience signals can be layered into Insights requests where supported.

The important architectural point is:

> Audience information should be used as a signal within the current Insights workflow rather than making the deprecated audience endpoints the foundation of the application.

An audience-conditioned query can investigate questions such as:

> "What brands resonate with sustainability-minded Nigerian consumers?"

or:

> "What cultural interests are associated with this product among a particular audience segment?"

This allows the system to test audience hypotheses rather than blindly accepting the user's assumed persona.

---

# 11. Geographic Heatmap

Heatmap analysis answers:

> "Where is affinity for this signal concentrated?"

The heatmap workflow can use:

- A natural-language location
- A locality/entity UUID
- A WKT boundary where supported
- An entity signal
- A tag signal

Example:

~~~text
Product / cultural signal
          +
       Nigeria
          |
          v
       Heatmap
          |
          +--> Latitude
          +--> Longitude
          +--> Geohash
          +--> Affinity
          +--> Affinity rank
          +--> Popularity
~~~

This allows the application to move from:

> **Who?**

to:

> **Where?**

The system should be able to compare markets such as:

- Lagos
- Abuja
- Other Nigerian locations
- Accra
- Other African markets
- International markets

The goal is to test whether cultural affinity changes by location.

---

# 12. Audience Comparison

Multiple audience hypotheses can be compared rather than choosing one automatically.

For example:

~~~text
Product
  |
  +--> Audience A
  |
  +--> Audience B
  |
  +--> Audience C
       |
       v
Compare evidence
       |
       +--> Affinity
       +--> Demographics
       +--> Geographic concentration
       +--> Cross-domain interests
       +--> Popularity
       +--> Explainability
       |
       v
Rank / characterize hypotheses
~~~

The output should distinguish:

- Strong evidence
- Moderate evidence
- Weak evidence
- Unexpected opportunity
- Insufficient evidence

---

# 13. Additional Qloo Research

The agent should not stop after one query.

If an important question remains unresolved, it can perform additional research.

Examples:

- Search for another comparable brand.
- Resolve another product concept.
- Search for a more specific tag.
- Compare another city.
- Compare another audience segment.
- Run Insights against another entity type.
- Run demographic analysis on another signal.
- Run a heatmap for another location.

This creates the agentic loop:

~~~text
Research
   |
   v
Evaluate evidence
   |
   +---- sufficient ----> Synthesize
   |
   +---- insufficient --> Refine research
                              |
                              v
                           Research
~~~

The application should impose a bounded number of refinement cycles to prevent uncontrolled API usage.

---

# 14. Evidence Aggregation

Raw Qloo responses should not be sent directly to the final LLM.

Instead:

~~~text
Qloo responses
     |
     v
Normalize
     |
     v
Remove duplicate information
     |
     v
Connect related signals
     |
     v
Rank / preserve evidence
     |
     v
Compact evidence package
     |
     v
LLM
~~~

The evidence package should preserve:

- Entity IDs
- Entity names
- Entity types
- Tags
- Affinity
- Popularity
- Demographic signals
- Geographic signals
- Audience signals
- Explainability
- Source query/context

The system should avoid passing unnecessary raw HTTP metadata.

---

# 15. LLM Synthesis

The LLM is responsible for interpreting Qloo evidence, not replacing Qloo's cultural intelligence.

The LLM should answer questions such as:

### Who?

> Which demographic/audience groups appear most relevant?

### Where?

> Which locations show stronger cultural affinity?

### What?

> What interests, brands, media, places, or cultural entities are associated with the audience?

### Why?

> What evidence supports the recommendation?

### What was unexpected?

> Did the research reveal an audience or cultural association that differs from the user's original assumption?

### How?

> What marketing approaches could reasonably be tested based on the cultural evidence?

The LLM should clearly separate:

~~~text
Qloo evidence
      |
      v
Interpretation
      |
      v
Marketing hypothesis
      |
      v
Recommendation
~~~

A recommendation must not be presented as a guaranteed prediction.

---

# 16. Final Market Recommendation

The final report should be actionable.

Possible structure:

~~~text
MARKET OPPORTUNITY
------------------
What the research suggests about the market.

RECOMMENDED AUDIENCE
--------------------
Primary audience hypothesis.

DEMOGRAPHIC SIGNALS
--------------------
Age / gender / audience signals supported by Qloo.

GEOGRAPHIC OPPORTUNITIES
-------------------------
Locations showing stronger affinity.

CULTURAL INTERESTS
-------------------
Important interests and related entities.

RELATED BRANDS / MEDIA
----------------------
Entities associated with the audience.

MESSAGING / POSITIONING
-----------------------
Potential themes suggested by the cultural evidence.

TARGETING HYPOTHESES
--------------------
Audience and location combinations worth testing.

UNEXPECTED OPPORTUNITIES
------------------------
Audience or cultural relationships the business may not have considered.

EVIDENCE
--------
The Qloo signals supporting the conclusions.

LIMITATIONS
-----------
What the data does not prove.
~~~

The application should avoid claiming that Qloo directly proves that a particular person will buy a product.

The output should instead use language such as:

- "strong cultural affinity"
- "audience signal"
- "worth testing"
- "potential opportunity"
- "supported by the observed Qloo signals"
- "hypothesis"

---

# 17. Example End-to-End Scenario

## User

> "I want to launch a premium handmade beaded bag brand in Nigeria. I don't know who my customers should be or which city I should focus on."

## Agent interpretation

~~~yaml
business_objective:
  type: market_discovery
  goal: identify_potential_market

product:
  description: premium handmade beaded bags

market:
  country: Nigeria

unknowns:
  - audience
  - demographics
  - geographic concentration
  - cultural interests
  - positioning
~~~

## Research

~~~text
1. Resolve relevant product/category entities.
2. Search relevant Qloo tags.
3. Identify comparable brands/entities.
4. Build cultural signal set.
5. Run Taste Analysis.
6. Discover cross-domain affinities.
7. Run demographic analysis.
8. Run Nigerian geographic analysis.
9. Compare relevant Nigerian locations.
10. Test audience hypotheses.
11. Aggregate evidence.
12. Synthesize recommendation.
~~~

## Result

The application could produce a recommendation such as:

~~~text
The strongest audience hypothesis is [audience], based on
the combination of cultural affinity, demographic signals,
and geographic concentration.

The strongest geographic opportunity appears to be [location].

The audience also shows strong relationships with [cultural
signals/entities], suggesting that these may be useful
contexts for positioning or campaign creative.

Your initial target of [user's assumed audience] appears
[well supported / partially supported / weakly supported].

A secondary audience worth testing is [segment] because
Qloo shows [evidence].

These findings are market hypotheses rather than guarantees
of purchase behavior.
~~~

---

# 18. Core Architectural Principle

The application should **not** be a fixed collection of API calls.

It should be an agentic research system:

~~~text
User Question
     |
     v
Understand
     |
     v
Plan Research
     |
     v
Resolve Signals
     |
     v
Query Qloo
     |
     v
Evaluate Evidence
     |
     +------ insufficient ------+
     |                          |
     |                          v
     |                    Refine Research
     |                          |
     +<-------------------------+
     |
     v
Synthesize Market Intelligence
     |
     v
Recommendation
~~~

The LLM decides **what needs to be learned next**.

Deterministic application services decide **how to execute valid Qloo requests**.

Qloo provides the **cultural intelligence and evidence layer**.

The LLM turns that evidence into a **business-facing market hypothesis and recommendation**.

---

# 19. Deprecated Audience Endpoints

The Qloo documentation conversation indicated that legacy audience/recommendation endpoints should not be the foundation of the application.

The current workflow should center on the **Insights API**, with audience information used through supported demographic/audience signals where appropriate.

This should be verified against the current official Qloo documentation before implementation because API capabilities can change.

---

# 20. Design Principle for Discover Market

The application should answer:

> **Given this product, business, market, and objective, what can Qloo's cultural intelligence tell us about the people, places, interests, and cultural relationships that are worth investigating?**

It should not simply answer:

> "Who should I advertise to?"

Instead, it should perform the research required to construct and explain a defensible **market hypothesis**.

---

## Source

This document is derived from the Qloo documentation AI conversation captured in:

`workflow_example.txt`

The original file is retained unchanged for historical/reference purposes.
