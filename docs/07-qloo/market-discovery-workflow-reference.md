# Qloo Marketing Audience Discovery — Workflow Reference

> **Alignment:** Detail document. Product scope, requirements, and enums are defined in [`REQUIREMENTS.md`](../../REQUIREMENTS.md); if this document conflicts with it, the requirements win. Conceptual workflow: [`Workflow Example.md`](../../Workflow%20Example.md). Real captured responses: [`entity_examples/`](../../entity_examples).

## What this is

A faithful Markdown conversion of the Qloo documentation "Ask AI" conversation saved in [`workflow_example.txt`](../../workflow_example.txt) (a browser MHTML snapshot of `docs.qloo.com/reference/api-onboarding`, saved 2026-10-05). The page's styling and navigation are dropped; all 15 messages of the conversation are kept in order, with code, tables and parameter explanations intact.

Where a status note appears it is an editor's annotation added during conversion, not part of the original conversation.

## Read this before using it as a spec

This is AI-generated documentation guidance, not verified API behavior.

1. **Wrong base URL in every example request.** The requests use `https://api.qloo.com`. Message 1 states hackathon keys only work against `https://hackathon.api.qloo.com`; using the other host is the usual cause of `401`. Use the hackathon base URL (the one in `entity_examples/experiment_summary.json`).
2. **Example responses are illustrative, not captured.** Check: the heatmap example gives geohashes `s17mp4` / `s17nm2` for coordinates (6.4531, 3.3958) / (6.5244, 3.3792); those coordinates actually encode to `s14ktq` / `s14mhg`. Entity IDs such as `A1B2C3D4-...` and brands such as "Lisa Folawiyo" are placeholders.
3. **Search response shape disagrees with real data.** The example shows `type` + `subtype` and tags as `{id, name}`. Real search responses (see `entity_examples/search/`) use `types[]` and tags as `{name, tag_id, type, value}`. Real insights entities use `type` + `subtype` and tags as `{id, name, type, weight}`.
4. **Audience endpoint advice flipped twice** (messages 7, 9, 11). Final position: `/v2/audiences` and `/v2/audiences/types` are deprecated with no documented replacement.
5. **Incomplete.** The corrected workflow ends mid-sentence in Step 6; the last user message ("Continue") has no recorded reply.
6. **Unverified parameters.** Heatmap location is passed as `filter.location.query` in message 3 but `signal.location.query` in message 13. Demographic layering uses `signal.demographics.age` / `signal.demographics.gender`, and compare uses `a.signal.…` / `b.signal.…`; none of these has been tested against the live API. Step 4 of the corrected workflow describes Nigerian demographics but sends no location parameter.
7. **No Nigerian data has been verified.** Every real sample captured so far is US-based.

## Conversation index

| # | Speaker | Topic | Status |
|---|---|---|---|
| 0 | You | Deprecated audience endpoints; hackathon key access | |
| 1 | AI | Answer: legacy endpoints; hackathon base URL | INFO |
| 2 | You | Full marketing audience-discovery workflow request | |
| 3 | AI | First workflow, Steps 1-7 | SUPERSEDED IN PART |
| 4 | You | "Cont6" | |
| 5 | AI | First workflow, Step 8 (LLM package and prompt) | SUPERSEDED IN PART |
| 6 | You | "You used the deprecated audience endpoints…" | |
| 7 | AI | Claims endpoints are current | INCORRECT |
| 8 | You | Pastes `Get Audience Types` marked deprecated | |
| 9 | AI | Corrects, still points to `/v2/audiences` | PARTIALLY SUPERSEDED |
| 10 | You | Pastes `Get Audiences` marked deprecated | |
| 11 | AI | Both deprecated; use known URNs | CURRENT GUIDANCE |
| 12 | You | Re-run the workflow for handmade beaded bags, Nigeria | |
| 13 | AI | Corrected workflow, Steps 1-6 (truncated) | CURRENT, INCOMPLETE |
| 14 | You | "Continue" (no reply recorded) | |

---

## Transcript

### Message 0 — You

> The audience endpoints are deprecated should I still use them or are there alternatives. Secondly can the hackathon API key access every endpoints

### Message 1 — Qloo Ask AI

> **Status: INFO.** Useful. Establishes the hackathon base URL and that `/recommendations` and `/recs` are legacy.

Here are answers to both of your questions:

------------------------------------------------------------------------

##### 1. Deprecated Audience Endpoints

The `/recommendations` and `/recs` endpoints are the **legacy/deprecated endpoints** you should avoid. According to the Hackathon Developer Guide, these are not supported and will not work.

**The alternative** is to use `/v2/insights`, which is the primary, fully supported endpoint for recommendations and insights. For audience-related signals, you can still pass audience values via `signal.demographics.audiences` in your Insights requests.

------------------------------------------------------------------------

##### 2. Hackathon API Key Access

Hackathon API keys give access to **all documented Qloo endpoints**, but with one important caveat — they **only work against the hackathon base URL**:

```text
https://hackathon.api.qloo.com
```

They will **not** work against:

- `https://staging.api.qloo.com`
- `https://api.qloo.com`

Using the wrong base URL is the most common cause of `401 Unauthorized` errors. Additionally, some entity types may return a `403` if they are not supported in the hackathon environment. See the full list of supported entity types in the guide.

*Sources cited by the assistant: Qloo Agentic Hackathon Developer Guide.*

---

### Message 2 — You

> I’m building an AI marketing audience-discovery workflow using Qloo.
>
> Use case: A business has a new product and wants to discover who to advertise to, where they are, what demographics/interest groups to target, and what messaging may resonate with each audience.
>
> I want to understand the correct Qloo API workflow:
>
> 1. Product/business inputs: What information should I extract from the product, brand, or business (e.g. category, brand, product attributes, target market, existing customers) and how should I represent these as Qloo entities, search queries, or signals?
> 2. Search: Which Qloo Search endpoints/types should I use to identify the relevant product/brand and related entities?
> 3. Insights/signals: Which signals should I provide to "/v2/insights" to discover relevant audiences and affinities?
> 4. Filters: How should I configure filters when I want:
>    - audience interests/affinities,
>    - demographics,
>    - geographic/heat-map information,
>    - combinations of demographics + geography + interests?
> 5. Response processing: Which fields from Qloo responses are most useful for an LLM to analyze?
> 6. AI synthesis: How should I structure the Qloo results so an LLM can produce recommendations such as:
>    - “Target this audience in this location with this message”
>    - “Target this demographic with this positioning”
>    - “This is an unexpected audience segment worth testing”
>    - “These audiences have the strongest evidence/affinity.”
>
> Please give me a concrete end-to-end API workflow, including example requests, the signals/filters used at each stage, and the important response fields to retain. Focus specifically on Qloo’s current API capabilities for marketing audience discovery, rather than a generic marketing workflow.

### Message 3 — Qloo Ask AI

> **Status: SUPERSEDED IN PART.** First workflow. Steps 3 (audience lookup via `/v2/audiences`, `/v2/audience-types`) were later shown to be deprecated. Steps 7-8 (compare, LLM package, prompt template) are NOT repeated in the corrected workflow, so they remain the only source for those steps.

Let me pull together the relevant documentation across search, insights, parameters, audiences, demographics, heatmaps, and tags.

Here is a complete end-to-end Qloo API workflow for AI-driven marketing audience discovery.

------------------------------------------------------------------------

#### Qloo Marketing Audience Discovery: End-to-End Workflow

------------------------------------------------------------------------

##### Overview of the Pipeline

```text
Product/Brand Input
      ↓
[Step 1] Search → Resolve brand/entity IDs + discover relevant tags
      ↓
[Step 2] Taste Analysis → Psychographic profile of the brand's audience
      ↓
[Step 3] Audience Discovery → Find audience segments that over-index
      ↓
[Step 4] Cross-Domain Affinity → What else does this audience love?
      ↓
[Step 5] Demographic Breakdown → Age & gender distribution per segment
      ↓
[Step 6] Geographic Heatmap → Where are these audiences concentrated?
      ↓
[Step 7] Audience Comparison → Rank segments by evidence strength
      ↓
[Step 8] LLM Synthesis → Generate targeting & messaging recommendations
```

------------------------------------------------------------------------

##### Step 1: Extract Inputs & Resolve Entity IDs

###### What to extract from the product/business

| Input type                  | What to capture                    | Qloo representation                                                                      |
|-----------------------------|------------------------------------|------------------------------------------------------------------------------------------|
| Brand name                  | "Nike", "Glossier"                 | Search → `urn:entity:brand`                                                              |
| Product category            | "athletic footwear", "skincare"    | Search tags via `/v2/tags`                                                               |
| Competitor brands           | "Adidas", "Fenty Beauty"           | Search → `urn:entity:brand` (use as comparative signal)                                  |
| Existing customer interests | genres, artists, shows they love   | Search → entity IDs for any type                                                         |
| Target market               | "women 25–34", "urban millennials" | `signal.demographics.age`, `signal.demographics.gender`, `signal.demographics.audiences` |
| Geography                   | "NYC", "West Coast"                | `filter.location.query` or WKT polygon                                                   |

###### Search for the brand entity ID

Use `/search` to resolve the brand name to a Qloo UUID:

```bash
curl --request GET \
  --url 'https://api.qloo.com/search?query=Nike&types=urn:entity:brand&take=5' \
  --header 'X-Api-Key: YOUR_API_KEY'
```

**Key response fields to retain:**

- `entity_id` — the UUID you'll use in all downstream calls
- `name` — confirm you matched the right entity
- `subtype` — confirms entity type (e.g., `urn:entity:brand`)
- `tags[]` — the brand's existing genre/category tags (e.g., `urn:tag:genre:brand:fashion:footwear`)
- `popularity` — baseline signal strength

###### Search for relevant tags

Use `/v2/tags` to find tag URNs representing the product's category:

```bash
curl --request GET \
  --url 'https://api.qloo.com/v2/tags?filter.query=athletic+footwear&take=10' \
  --header 'X-Api-Key: YOUR_API_KEY'
```

**Retain:** `id` (the URN like `urn:tag:genre:brand:fashion:footwear:sneakers`) — use in signal and filter parameters downstream.

------------------------------------------------------------------------

##### Step 2: Taste Analysis — Psychographic Profile

Use Taste Analysis to discover the psychographic tags that define the brand's audience. This is `filter.type=urn:tag`, which reverses the usual flow — instead of returning entities, it returns the taste vocabulary of the audience.

```bash
# Get lifestyle/ambience tags associated with the brand's audience
curl --request GET \
  --url 'https://api.qloo.com/v2/insights/?filter.type=urn:tag&signal.interests.entities=BRAND_ENTITY_ID&take=20' \
  --header 'X-Api-Key: YOUR_API_KEY'
```

You can scope to a specific tag namespace with `filter.tag.types` (e.g., lifestyle, ambience, genre):

```bash
curl --request GET \
  --url 'https://api.qloo.com/v2/insights/?filter.type=urn:tag&filter.tag.types=urn:tag:keyword:brand&signal.interests.entities=BRAND_ENTITY_ID&take=20' \
  --header 'X-Api-Key: YOUR_API_KEY'
```

**Key response fields to retain from `results.tags[]`:**

- `tag_id` — use in downstream signals
- `name` — human-readable label (e.g., "Streetwear", "Sustainability")
- `query.affinity` — how strongly the tag defines this audience (0–1); higher = stronger psychographic signal

> **LLM use:** Feed top tags to the LLM as the brand's psychographic fingerprint. These become the basis for messaging themes.

------------------------------------------------------------------------

##### Step 3: Audience Segment Discovery

Find which Qloo audience segments over-index for this brand. First, look up valid audience URNs via `/v2/audiences`:

```bash
# Discover audiences related to the brand's space
curl --request GET \
  --url 'https://api.qloo.com/v2/audiences?filter.query=sneakers&take=10' \
  --header 'X-Api-Key: YOUR_API_KEY'
```

**Retain from `results.audiences[]`:**

- `id` — the URN (e.g., `urn:audience:hobbies_and_interests:outdoors`) — pass this to `signal.demographics.audiences`
- `name` — human-readable label
- `type` — parent category (e.g., `urn:audience:spending_habits`)

You can also list all audience categories via `/v2/audience-types` to survey the full taxonomy:

```bash
curl --request GET \
  --url 'https://api.qloo.com/v2/audience-types' \
  --header 'X-Api-Key: YOUR_API_KEY'
```

Valid audience parent categories include:

- `urn:audience:hobbies_and_interests`
- `urn:audience:spending_habits`
- `urn:audience:lifestyle_preferences_beliefs`
- `urn:audience:life_stage`
- `urn:audience:communities`
- `urn:audience:professional_area`

------------------------------------------------------------------------

##### Step 4: Cross-Domain Affinity — What Does This Audience Love?

Use the brand entity as a signal and ask for correlated entities in other domains. This reveals adjacent interests that inform both media planning and messaging.

```bash
# What movies does this brand's audience love?
curl --request GET \
  --url 'https://api.qloo.com/v2/insights/?filter.type=urn:entity:movie&signal.interests.entities=BRAND_ENTITY_ID&take=15' \
  --header 'X-Api-Key: YOUR_API_KEY'

# What artists do they listen to?
curl --request GET \
  --url 'https://api.qloo.com/v2/insights/?filter.type=urn:entity:artist&signal.interests.entities=BRAND_ENTITY_ID&take=15' \
  --header 'X-Api-Key: YOUR_API_KEY'

# What other brands are they affine to? (useful for partnership/co-marketing)
curl --request GET \
  --url 'https://api.qloo.com/v2/insights/?filter.type=urn:entity:brand&signal.interests.entities=BRAND_ENTITY_ID&take=15' \
  --header 'X-Api-Key: YOUR_API_KEY'
```

**Key response fields to retain from `results.entities[]`:**

- `entity_id`, `name`, `subtype`
- `query.affinity` — correlation strength (0–1)
- `query.popularity` — entity's baseline signal density
- `tags[]` — entity's own genre/attribute tags (useful for messaging context)

> **LLM use:** Cross-domain affinity tells the LLM *what cultural world* this audience inhabits — essential for media channel selection and creative messaging.

------------------------------------------------------------------------

##### Step 5: Demographic Breakdown

Use `filter.type=urn:demographics` to get the age and gender distribution for the brand's audience, and compare it to category-level tags:

```bash
curl --request GET \
  --url 'https://api.qloo.com/v2/insights/?filter.type=urn:demographics&signal.interests.entities=BRAND_ENTITY_ID&signal.interests.tags=urn:tag:genre:brand:fashion:footwear' \
  --header 'X-Api-Key: YOUR_API_KEY'
```

**Key response fields to retain from `results.demographics[]`:**

- `entity_id` — which signal this demographic block is for
- `query.age.*` — affinity score per age bucket (positive = over-indexes, negative = under-indexes)
  - Buckets: `24_and_younger`, `25_to_29`, `30_to_34`, `35_to_44`, `45_to_54`, `55_and_older`
- `query.gender.male`, `query.gender.female` — gender skew

> **LLM use:** The LLM can compare the brand's demographic profile vs. the category average (by running both as signals) to identify where the brand over- or under-indexes relative to its competitive set. A positive age value like `30_to_34: 0.70` means strong over-indexing in that cohort.

###### Running demographics filtered by a specific audience segment

Once you know your target audience URN (Step 3), you can layer it in:

```bash
curl --request GET \
  --url 'https://api.qloo.com/v2/insights/?filter.type=urn:demographics&signal.interests.entities=BRAND_ENTITY_ID&signal.demographics.audiences=urn:audience:hobbies_and_interests:fitness' \
  --header 'X-Api-Key: YOUR_API_KEY'
```

------------------------------------------------------------------------

##### Step 6: Geographic Heatmap — Where Are These Audiences?

Use `filter.type=urn:heatmap` to identify geographic concentration of affinity for the brand. You can use a natural-language location query or a precise WKT polygon.

###### By city name

```bash
curl --request GET \
  --url 'https://api.qloo.com/v2/insights/?filter.type=urn:heatmap&filter.location.query=Los+Angeles&signal.interests.entities=BRAND_ENTITY_ID' \
  --header 'X-Api-Key: YOUR_API_KEY'
```

###### By precise geographic boundary (WKT polygon)

```bash
curl --request GET \
  --url 'https://api.qloo.com/v2/insights/?filter.type=urn:heatmap&filter.location=POLYGON((-74.0479+40.6829,-74.0479+40.7831,-73.9067+40.7831,-73.9067+40.6829,-74.0479+40.6829))&signal.interests.entities=BRAND_ENTITY_ID' \
  --header 'X-Api-Key: YOUR_API_KEY'
```

###### Heatmap with demographic layering

```bash
curl --request GET \
  --url 'https://api.qloo.com/v2/insights/?filter.type=urn:heatmap&filter.location.query=NYC&signal.interests.entities=BRAND_ENTITY_ID&signal.demographics.age=25_to_29,30_to_34&signal.demographics.gender=female' \
  --header 'X-Api-Key: YOUR_API_KEY'
```

**Key response fields to retain from `results.heatmap[]`:**

- `location.latitude`, `location.longitude`, `location.geohash` — the geographic cell
- `query.affinity` — relative interest at this location (0–1)
- `query.affinity_rank` — how this cell ranks vs. others in the set (0–1); use this to find hotspots
- `query.popularity` — overall signal density at this location

> **LLM use:** Sort cells by `affinity_rank` descending. The top cells represent the highest-concentration targeting zones. The LLM can translate geohash clusters into neighborhood-level descriptions.

------------------------------------------------------------------------

##### Step 7: Audience Segment Comparison

Use `/v2/analysis/compare` to identify the shared taste space between your brand and a competitor, or between two audience segments. This helps identify what both share (safe positioning) and where they diverge (differentiation opportunity).

```bash
curl --request GET \
  --url 'https://api.qloo.com/v2/analysis/compare?a.signal.interests.entities=BRAND_ENTITY_ID&b.signal.interests.entities=COMPETITOR_ENTITY_ID&take=15' \
  --header 'X-Api-Key: YOUR_API_KEY'
```

**Key response fields to retain from `results.tags[]`:**

- `tag_id`, `name` — the shared taste attribute
- `query.score` — strength of shared association (higher = stronger overlap)
- `popularity` — how broadly this tag is present

> **LLM use:** Tags with high `score` = shared audience messaging territory. Tags unique to your brand's taste profile (from Step 2 but absent here) = differentiation angles.

------------------------------------------------------------------------

##### Step 8: Structuring Results for LLM Synthesis

###### Recommended data package to pass to the LLM

Assemble a structured JSON object per audience segment:

```json
{
  "brand": {
    "name": "Nike Air Jordan",
    "entity_id": "E26BC58D-...",
    "psychographic_tags": [
      {"name": "Streetwear", "affinity": 0.98},
      {"name": "Collectible", "affinity": 0.95},
      {"name": "Performance", "affinity": 0.91}
    ],
    "cross_domain_affinities": {
      "artists": [{"name": "Drake", "affinity": 0.94}],
      "movies": [{"name": "Space Jam", "affinity": 0.89}],
      "brands": [{"name": "Adidas Originals", "affinity": 0.87}]
    }
  },
  "segments": [
    {
      "audience_id": "urn:audience:hobbies_and_interests:sneaker_culture",
      "audience_name": "Sneaker Enthusiasts",
      "demographic_skew": {
        "top_age_buc
```

*Sources cited by the assistant: Search Entities Get Tags Taste Analysis Get Audiences Get Audience Types Demographic Insights Heatmap Insights Analysis Compare.*

---

### Message 4 — You

> Cont6

### Message 5 — Qloo Ask AI

> **Status: SUPERSEDED IN PART.** Continuation of the first workflow. The LLM prompt template and signal-to-output mapping are still the only version available. The `evidence_strength` value in the JSON package is an invented composite score; do not reproduce it.

Continuing from the structured JSON package in Step 8:

```json
      "demographic_skew": {
        "top_age_buckets": {"25_to_29": 0.43, "30_to_34": 0.70},
        "gender": {"male": 0.16, "female": -0.16}
      },
      "geographic_hotspots": [
        {"geohash": "dr5ru2", "affinity_rank": 0.999, "lat": 40.74, "lon": -73.98},
        {"geohash": "dr72nj", "affinity_rank": 0.996, "lat": 40.81, "lon": -73.91}
      ],
      "evidence_strength": 0.94
    }
  ],
  "competitor_overlap": {
    "competitor": "Adidas",
    "shared_tags": [
      {"name": "Athletic", "score": 0.729},
      {"name": "Streetwear", "score": 0.681}
    ]
  }
}
```

------------------------------------------------------------------------

###### LLM Prompt Template

```text
You are a marketing strategist. Below is structured audience intelligence 
from Qloo's cultural AI. Analyze it and produce:

1. PRIMARY AUDIENCE: The segment with the strongest evidence (highest 
   affinity scores across taste, demographics, and geography). 
   Recommend targeting approach and 2-3 message angles grounded in 
   the psychographic tags.

2. GEOGRAPHIC TARGETING: Based on heatmap hotspots, name the top 
   zones to activate (translate geohash clusters into city/neighborhood 
   language where possible). Suggest channel format suited to each zone.

3. UNEXPECTED SEGMENT: Identify any audience, cross-domain affinity, 
   or geographic hotspot that is surprising given the brand's category. 
   Explain why it's worth testing.

4. COMPETITIVE DIFFERENTIATION: Using the competitor overlap tags, 
   identify what messaging territory is shared (avoid) vs. what the 
   brand owns uniquely (lean in).

5. EVIDENCE RANKING: Rank all segments by confidence, citing which 
   Qloo signals (affinity score, demographic skew, geographic 
   concentration) support each rank.

Qloo data:
{{ INSERT ASSEMBLED JSON }}
```

------------------------------------------------------------------------

###### Signal → LLM Output Mapping

| Qloo signal                       | LLM output it enables                                                               |
|-----------------------------------|-------------------------------------------------------------------------------------|
| `query.affinity` (taste/tag)      | Psychographic messaging themes                                                      |
| `query.age.*` (demographics)      | Age-targeted creative direction                                                     |
| `query.gender.*`                  | Gender-skewed channel/format decisions                                              |
| `query.affinity_rank` (heatmap)   | Geo-targeted media buy locations                                                    |
| `query.score` (compare)           | Competitive positioning & differentiation                                           |
| Cross-domain `results.entities[]` | Media channel selection (e.g., if top affinity = hip-hop artists → Spotify/YouTube) |
| `popularity`                      | Segment size proxy — higher popularity = broader reach potential                    |

------------------------------------------------------------------------

###### Key Reference Pages

- Insights API Deep Dive — live parameter testing
- Parameter Reference — all signals and filters
- Taste Analysis — psychographic tag extraction
- Demographic Insights — age/gender breakdown
- Heatmap Insights — geographic affinity
- Analysis Compare — competitive overlap
- Entity Type Parameter Guide — valid params per `filter.type`

*Sources cited by the assistant: Insights API Deep Dive Parameter Reference Taste Analysis Demographic Insights Heatmap Insights Analysis Compare Entity Type Parameter Guide.*

---

### Message 6 — You

> You used the deprecated audience endpoints. Is that a good thing to do

### Message 7 — Qloo Ask AI

> **Status: INCORRECT.** Claimed the audience endpoints were current. Contradicted by the Qloo docs pages pasted in the next prompts and by messages 9 and 11.

Good question — but actually, the endpoints used in the workflow are **not the deprecated ones**.

As clarified earlier in our conversation, the only deprecated/legacy endpoints to avoid are:

- `/recommendations`
- `/recs`

The audience-related endpoints used in the workflow are all **current, documented, and supported**:

| Endpoint used                   | Status     | Purpose                                         |
|---------------------------------|------------|-------------------------------------------------|
| `/v2/audiences`                 | ✅ Current | Look up valid audience URNs by keyword          |
| `/v2/audience-types`            | ✅ Current | List all audience category URNs                 |
| `signal.demographics.audiences` | ✅ Current | Pass audience URNs as signals to `/v2/insights` |

These are listed as active Lookup APIs in the API Overview. The correct replacement for the deprecated endpoints is `/v2/insights` — which is exactly what the workflow uses for all recommendations, demographics, heatmaps, and taste analysis.

So the workflow is fully aligned with Qloo's current API. No changes needed on that front.

*Sources cited by the assistant: Qloo Agentic Hackathon Developer Guide API Overview (Supporting Apis).*

---

### Message 8 — You

> This is what I saw Get Audience Types
> get
> deprecated
> https://api.qloo.com/v2/audiences/types
>
> The Get Audience Types API returns all available audience type IDs, representing different audience categories. You can use this API to explore audience classifications and refine searches in the Find Audiences API. Including filter.parents.types allows you to narrow results by relevant entity types.

### Message 9 — Qloo Ask AI

> **Status: PARTIALLY SUPERSEDED.** Correctly drops `/v2/audiences/types`, but still recommends `/v2/audiences`, which message 11 then also marks deprecated.

You are absolutely correct, and I apologize for the error. The page you're currently viewing confirms that `GET /v2/audiences/types` is explicitly marked **deprecated**. I should not have included it in the workflow.

Here's the corrected guidance:

###### ❌ Don't use (deprecated)

```bash
GET /v2/audiences/types
```

###### ✅ What to do instead

Rather than enumerating audience types, **search directly for audiences by keyword** using `/v2/audiences` with `filter.query`:

```bash
curl --request GET \
  --url 'https://api.qloo.com/v2/audiences?filter.query=fitness&take=10' \
  --header 'X-Api-Key: YOUR_API_KEY'
```

For the marketing workflow, you can run multiple keyword searches aligned to your product's space (e.g., "sneakers", "streetwear", "sustainability") to discover valid audience URNs — and the response already includes the `type` (parent category) on each result, so you don't need the types endpoint separately.

You can also reference the known valid audience parent URNs directly from the Hackathon Developer Guide without needing to call any endpoint:

- `urn:audience:hobbies_and_interests`
- `urn:audience:spending_habits`
- `urn:audience:lifestyle_preferences_beliefs`
- `urn:audience:life_stage`
- `urn:audience:communities`
- `urn:audience:professional_area`

Thanks for catching that.

*Sources cited by the assistant: Qloo Agentic Hackathon Developer Guide.*

---

### Message 10 — You

> This is also deprecated Get Audiences
> get
> deprecated
> https://api.qloo.com/v2/audiences
>
> The Find Audiences API retrieves a list of audience IDs that can be used for filtering results and refining targeting in

### Message 11 — Qloo Ask AI

> **Status: CURRENT GUIDANCE.** Both audience endpoints are deprecated; no replacement is documented. Use the known audience URNs directly in `signal.demographics.audiences`. Note: the listed URNs are parent categories, and it is unverified whether Insights accepts them.

You're right again, and I apologize. Let me search the documentation for the correct current alternatives.

You're right, and I apologize again. Both `/v2/audiences` and `/v2/audiences/types` are deprecated. Unfortunately, the documentation doesn't currently surface a clear non-deprecated replacement endpoint for audience discovery.

Here's what I can say honestly:

###### What is confirmed safe to use

- **`signal.demographics.audiences`** in `/v2/insights` — passing audience URNs as signals is fully supported
- The **known audience parent URNs** are documented in the Hackathon Developer Guide and can be used directly without any lookup endpoint:
  - `urn:audience:communities`
  - `urn:audience:hobbies_and_interests`
  - `urn:audience:spending_habits`
  - `urn:audience:lifestyle_preferences_beliefs`
  - `urn:audience:life_stage`
  - `urn:audience:professional_area`
  - `urn:audience:global_issues`
  - `urn:audience:investing_interests`
  - `urn:audience:leisure`
  - `urn:audience:political_preferences`

###### What I'd recommend

Rather than relying on deprecated endpoints to discover audience URNs, **hardcode the known URN taxonomy above** and pass them directly into `signal.demographics.audiences` in your Insights calls.

For anything beyond this, I'd suggest checking with Qloo directly via [support@qloo.com](mailto:support@qloo.com) or the Hackathon Discord to confirm the intended replacement.

*Sources cited by the assistant: Qloo Agentic Hackathon Developer Guide discord.gg/rF9PKsD5Q7.*

---

### Message 12 — You

> Present the workflow again using the new endpoints. For each step state the query parameters and their uses and Impacts on the response. Give an example response and the usage of each items and the key response field to retain. Use this user example: the user wants to sell handmade beats bags in Nigeria

### Message 13 — Qloo Ask AI

> **Status: CURRENT, INCOMPLETE.** The corrected workflow. The saved page cuts off mid-sentence in Step 6; Steps 6 (examples), 7 and 8 were never delivered in this version.

Here is the fully corrected workflow, using only non-deprecated endpoints, applied concretely to **selling handmade beaded bags in Nigeria**.

------------------------------------------------------------------------

#### Qloo Audience Discovery Workflow

##### Use Case: Handmade Beaded Bags — Nigeria

------------------------------------------------------------------------

##### Pipeline Overview

```text
[Step 1] /search          → Resolve brand/competitor entity IDs + tags
         /v2/tags         → Find relevant category tag URNs
         /v2/tags/types   → Discover available tag namespaces
      ↓
[Step 2] /v2/insights (filter.type=urn:tag)
                          → Psychographic taste profile of this space
      ↓
[Step 3] /v2/insights (filter.type=urn:entity:brand)
         + signal.location.query=Nigeria
                          → What brands does this audience love locally?
      ↓
[Step 4] /v2/insights (filter.type=urn:demographics)
                          → Age & gender breakdown
      ↓
[Step 5] /v2/insights (filter.type=urn:heatmap)
                          → Geographic concentration within Nigeria
      ↓
[Step 6] /v2/insights (filter.type=urn:entity:*)
         + signal.demographics.audiences (known URNs)
                          → Cross-domain affinities per audience segment
      ↓
[Step 7] /v2/analysis/compare
                          → Compare two audience segments or brands
      ↓
[Step 8] LLM Synthesis
```

------------------------------------------------------------------------

##### Step 1A: Resolve Category Tags via /v2/tags

Since handmade beaded bags are a niche product with no direct Qloo brand entity, start by finding relevant **tag URNs** that represent the product's space. These become your primary signals throughout the workflow.

###### Request

```bash
curl --request GET \
  --url 'https://api.qloo.com/v2/tags?filter.query=handmade&take=10' \
  --header 'X-Api-Key: YOUR_API_KEY'
```

**Parameters:**

| Parameter      | Value      | Purpose                                    | Impact on Response                                                      |
|----------------|------------|--------------------------------------------|-------------------------------------------------------------------------|
| `filter.query` | `handmade` | Keyword search across tag names            | Returns tags whose names match or are semantically close to the keyword |
| `take`         | `10`       | Max results to return (default 20, max 50) | Controls how many tags are returned                                     |

Run multiple searches: `handmade`, `fashion accessories`, `artisan`, `beaded`, `luxury bags`.

###### Example Response

```json
{
  "success": true,
  "results": {
    "tags": [
      {
        "id": "urn:tag:genre:brand:fashion:accessories",
        "name": "Fashion Accessories",
        "type": "urn:tag:genre:brand"
      },
      {
        "id": "urn:tag:style:qloo:artisan",
        "name": "Artisan",
        "type": "urn:tag:style:qloo"
      },
      {
        "id": "urn:tag:genre:brand:fashion:luxury",
        "name": "Luxury",
        "type": "urn:tag:genre:brand"
      }
    ]
  }
}
```

**Key fields to retain:**

| Field  | Usage                                                                                           |
|--------|-------------------------------------------------------------------------------------------------|
| `id`   | The URN — use as `signal.interests.tags` or `filter.tags` in all downstream Insights calls      |
| `name` | Human-readable label — pass to LLM for messaging context                                        |
| `type` | The tag namespace — tells you which `filter.tag.types` value to use when scoping taste analysis |

------------------------------------------------------------------------

##### Step 1B: Discover Tag Namespaces via /v2/tags/types

Use the Get Tag Types endpoint to understand what tag categories exist for brands, so you know which namespaces to query in taste analysis.

###### Request

```bash
curl --request GET \
  --url 'https://api.qloo.com/v2/tags/types?filter.parents.types=urn:entity:brand&take=20' \
  --header 'X-Api-Key: YOUR_API_KEY'
```

**Parameters:**

| Parameter              | Value              | Purpose                                        | Impact on Response                                     |
|------------------------|--------------------|------------------------------------------------|--------------------------------------------------------|
| `filter.parents.types` | `urn:entity:brand` | Scopes tag types to those applicable to brands | Returns only tag namespaces relevant to brand entities |
| `take`                 | `20`               | Max results                                    | Controls how many tag types are returned               |

###### Example Response

```json
{
  "success": true,
  "results": {
    "tag_types": [
      { "id": "urn:tag:genre:brand", "name": "Genre" },
      { "id": "urn:tag:style:qloo", "name": "Style" },
      { "id": "urn:tag:keyword:brand", "name": "Keyword" }
    ]
  }
}
```

**Key fields to retain:**

| Field  | Usage                                                                            |
|--------|----------------------------------------------------------------------------------|
| `id`   | Use as the value for `filter.tag.types` in Step 2 taste analysis calls           |
| `name` | Tells the LLM what dimension each tag set represents (style vs genre vs keyword) |

------------------------------------------------------------------------

##### Step 1C: Search for Comparable/Competitor Brands via /search

Find Qloo entity IDs for analogous brands (e.g., African fashion brands, artisan accessories brands) to use as signals. These act as proxies for your product's audience.

###### Request

```bash
curl --request GET \
  --url 'https://api.qloo.com/search?query=Ankara+fashion&types=urn:entity:brand&take=5' \
  --header 'X-Api-Key: YOUR_API_KEY'
```

**Parameters:**

| Parameter | Value              | Purpose                                  | Impact on Response                                         |
|-----------|--------------------|------------------------------------------|------------------------------------------------------------|
| `query`   | `Ankara fashion`   | Free-text brand name search              | Returns brands whose names or descriptions match the query |
| `types`   | `urn:entity:brand` | Restricts results to brand entities only | Filters out artists, movies, etc.                          |
| `take`    | `5`                | Number of results                        | Limits response size                                       |

Also search: `African accessories`, `Stella McCartney` (sustainable luxury proxy), `Bottega Veneta` (artisan leather proxy).

###### Example Response

```json
{
  "success": true,
  "results": [
    {
      "entity_id": "A1B2C3D4-...",
      "name": "Lisa Folawiyo",
      "type": "urn:entity",
      "subtype": "urn:entity:brand",
      "popularity": 0.72,
      "tags": [
        { "id": "urn:tag:genre:brand:fashion", "name": "Fashion" },
        { "id": "urn:tag:style:qloo:artisan", "name": "Artisan" }
      ]
    }
  ]
}
```

**Key fields to retain:**

| Field        | Usage                                                               |
|--------------|---------------------------------------------------------------------|
| `entity_id`  | Primary signal for all downstream `/v2/insights` calls              |
| `name`       | Confirm correct brand was matched                                   |
| `popularity` | Baseline signal density — higher popularity = more data-rich signal |
| `tags[].id`  | Additional tag URNs to add to your signal pool                      |

------------------------------------------------------------------------

##### Step 2: Taste Analysis — Psychographic Profile

Use Taste Analysis with `filter.type=urn:tag` to discover the psychographic vocabulary that defines this product's audience. Combine the tag signals from Step 1 with location scoping for Nigeria.

###### Request

```bash
curl --request GET \
  --url 'https://api.qloo.com/v2/insights/?filter.type=urn:tag\
&signal.interests.tags=urn:tag:genre:brand:fashion:accessories,urn:tag:style:qloo:artisan\
&signal.interests.entities=A1B2C3D4-COMPARABLE_BRAND_ID\
&signal.location.query=Nigeria\
&filter.tag.types=urn:tag:style:qloo\
&take=20' \
  --header 'X-Api-Key: YOUR_API_KEY'
```

**Parameters:**

| Parameter                   | Value                                         | Purpose                                       | Impact on Response                                                                     |
|-----------------------------|-----------------------------------------------|-----------------------------------------------|----------------------------------------------------------------------------------------|
| `filter.type`               | `urn:tag`                                     | Switches output mode from entities to tags    | Returns ranked tags instead of entities — reveals the taste vocabulary of the audience |
| `signal.interests.tags`     | `urn:tag:genre:brand:fashion:accessories,...` | Anchors the analysis to this product category | Tags that correlate with fashion accessories audiences rise to the top                 |
| `signal.interests.entities` | `A1B2C3D4-...`                                | Adds a comparable brand as signal             | Blends brand-level taste data with category-level tags for richer results              |
| `signal.location.query`     | `Nigeria`                                     | Localises results to Nigerian audience        | Affinity scores reflect Nigerian cultural context, not global averages                 |
| `filter.tag.types`          | `urn:tag:style:qloo`                          | Scopes output to style tags only              | Keeps results focused on style psychographics; remove to get all tag types             |
| `take`                      | `20`                                          | Number of tags to return                      | Controls how broad the psychographic vocabulary is                                     |

###### Example Response

```json
{
  "success": true,
  "results": {
    "tags": [
      {
        "tag_id": "urn:tag:style:qloo:artisan",
        "name": "Artisan",
        "subtype": "urn:tag:style:qloo",
        "query": { "affinity": 0.97 }
      },
      {
        "tag_id": "urn:tag:style:qloo:cultural-heritage",
        "name": "Cultural Heritage",
        "subtype": "urn:tag:style:qloo",
        "query": { "affinity": 0.94 }
      },
      {
        "tag_id": "urn:tag:style:qloo:premium",
        "name": "Premium",
        "subtype": "urn:tag:style:qloo",
        "query": { "affinity": 0.89 }
      },
      {
        "tag_id": "urn:tag:style:qloo:expressive",
        "name": "Expressive",
        "subtype": "urn:tag:style:qloo",
        "query": { "affinity": 0.85 }
      }
    ]
  }
}
```

**Key fields to retain:**

| Field            | Usage                                                                                                     |
|------------------|-----------------------------------------------------------------------------------------------------------|
| `tag_id`         | Reuse as `signal.interests.tags` in Steps 3–6 to carry this psychographic fingerprint into other queries  |
| `name`           | Direct input to LLM as messaging themes (e.g., "Artisan", "Cultural Heritage" → craft storytelling angle) |
| `query.affinity` | Score 0–1; retain tags above ~0.80 as core psychographic signals; lower scores = weaker associations      |

> **LLM use:** Top tags = the brand's messaging pillars. "Cultural Heritage + Artisan + Premium" tells the LLM to frame messaging around pride, craftsmanship, and quality rather than price or trend.

------------------------------------------------------------------------

##### Step 3: Cross-Domain Affinity — What Else Does This Audience Love?

Use the tag and entity signals to discover correlated entities across domains. This reveals media channels, cultural touchpoints, and partnership opportunities within Nigeria.

###### 3A: Correlated Brands (co-marketing / retail adjacency)

```bash
curl --request GET \
  --url 'https://api.qloo.com/v2/insights/?filter.type=urn:entity:brand\
&signal.interests.tags=urn:tag:genre:brand:fashion:accessories,urn:tag:style:qloo:artisan\
&signal.interests.entities=A1B2C3D4-COMPARABLE_BRAND_ID\
&signal.location.query=Nigeria\
&take=15' \
  --header 'X-Api-Key: YOUR_API_KEY'
```

###### 3B: Correlated Artists (media/cultural alignment)

```bash
curl --request GET \
  --url 'https://api.qloo.com/v2/insights/?filter.type=urn:entity:artist\
&signal.interests.tags=urn:tag:genre:brand:fashion:accessories,urn:tag:style:qloo:artisan\
&signal.location.query=Nigeria\
&take=15' \
  --header 'X-Api-Key: YOUR_API_KEY'
```

###### 3C: Correlated TV Shows / Podcasts (advertising channel discovery)

```bash
curl --request GET \
  --url 'https://api.qloo.com/v2/insights/?filter.type=urn:entity:tv_show\
&signal.interests.tags=urn:tag:genre:brand:fashion:accessories\
&signal.location.query=Nigeria\
&take=15' \
  --header 'X-Api-Key: YOUR_API_KEY'
```

**Parameters (applies to all 3 sub-calls):**

| Parameter                   | Value                                                           | Purpose                                               | Impact on Response                                                       |
|-----------------------------|-----------------------------------------------------------------|-------------------------------------------------------|--------------------------------------------------------------------------|
| `filter.type`               | `urn:entity:brand` / `urn:entity:artist` / `urn:entity:tv_show` | Defines what type of entity is returned               | Changes the entire output domain — same signals, different cultural lens |
| `signal.interests.tags`     | Tag URNs from Step 1–2                                          | Carries psychographic context into cross-domain query | Entities that correlate with these taste attributes score highest        |
| `signal.interests.entities` | Comparable brand entity ID                                      | Adds behavioral signal from a known proxy brand       | Sharpens affinity towards entities loved by that brand's real audience   |
| `signal.location.query`     | `Nigeria`                                                       | Localises results                                     | Returns entities popular with Nigerian audiences specifically            |
| `take`                      | `15`                                                            | Result count                                          | Adjust based on how many options the LLM needs to rank                   |

###### Example Response (Brands)

```json
{
  "success": true,
  "results": {
    "entities": [
      {
        "entity_id": "X9Y8Z7-...",
        "name": "Alara Lagos",
        "subtype": "urn:entity:brand",
        "popularity": 0.81,
        "query": { "affinity": 0.93 },
        "tags": [
          { "id": "urn:tag:genre:brand:fashion", "name": "Fashion" },
          { "id": "urn:tag:style:qloo:premium", "name": "Premium" }
        ]
      },
      {
        "entity_id": "P1Q2R3-...",
        "name": "Zara",
        "subtype": "urn:entity:brand",
        "popularity": 0.98,
        "query": { "affinity": 0.87 },
        "tags": [
          { "id": "urn:tag:genre:brand:fashion", "name": "Fashion" }
        ]
      }
    ]
  }
}
```

**Key fields to retain:**

| Field            | Usage                                                                                     |
|------------------|-------------------------------------------------------------------------------------------|
| `entity_id`      | Use as signal in Step 6 for audience-layered queries                                      |
| `name`           | Pass to LLM — correlated brands indicate media adjacency and partnership potential        |
| `query.affinity` | Correlation strength; sort descending — top results are strongest cultural co-occurrences |
| `popularity`     | High popularity = broad reach; low popularity = niche/emerging segment                    |
| `tags[]`         | Reveals shared taste attributes between your product and the correlated entity            |

> **LLM use:** Correlated artists tell the LLM which music/cultural figures to reference in creative. Correlated TV shows indicate where to buy media. Correlated brands identify retail partners or competitive context.

------------------------------------------------------------------------

##### Step 4: Demographic Breakdown

Use `filter.type=urn:demographics` to understand the age and gender skew of the beaded bags audience in Nigeria.

###### Request

```bash
curl --request GET \
  --url 'https://api.qloo.com/v2/insights/?filter.type=urn:demographics\
&signal.interests.tags=urn:tag:genre:brand:fashion:accessories,urn:tag:style:qloo:artisan\
&signal.interests.entities=A1B2C3D4-COMPARABLE_BRAND_ID' \
  --header 'X-Api-Key: YOUR_API_KEY'
```

**Parameters:**

| Parameter                   | Value                              | Purpose                                      | Impact on Response                                                          |
|-----------------------------|------------------------------------|----------------------------------------------|-----------------------------------------------------------------------------|
| `filter.type`               | `urn:demographics`                 | Switches output to demographic distributions | Returns age and gender affinity blocks instead of entities or tags          |
| `signal.interests.tags`     | Fashion accessories + artisan URNs | Defines the category signal                  | Demographics shown are for audiences who engage with these taste attributes |
| `signal.interests.entities` | Comparable brand ID                | Adds brand-level signal                      | Blends category and brand demographics; run both separately to compare      |

###### Example Response

```json
{
  "success": true,
  "results": {
    "demographics": [
      {
        "entity_id": "urn:tag:genre:brand:fashion:accessories",
        "query": {
          "age": {
            "24_and_younger": 0.12,
            "25_to_29": 0.61,
            "30_to_34": 0.74,
            "35_to_44": 0.38,
            "45_to_54": -0.22,
            "55_and_older": -0.41
          },
          "gender": {
            "male": -0.31,
            "female": 0.31
          }
        }
      }
    ]
  }
}
```

**Key fields to retain:**

| Field                          | Usage                                                                                                       |
|--------------------------------|-------------------------------------------------------------------------------------------------------------|
| `query.age.*`                  | Positive = over-indexes in that age group; negative = under-indexes. Retain all buckets for the LLM to rank |
| `query.gender.male` / `female` | Gender skew direction and magnitude — informs tone, imagery, and channel selection                          |
| `entity_id`                    | Identifies which signal the demographic block is for (tag vs brand) — allows comparison                     |

> **LLM use:** In this example, `30_to_34: 0.74` and `female: 0.31` tells the LLM the core target is **women aged 25–34**. The LLM should flag `25_to_29: 0.61` as a strong secondary cohort and `55_and_older: -0.41` as not worth targeting.

------------------------------------------------------------------------

##### Step 5: Geographic Heatmap — Where in Nigeria?

Use `filter.type=urn:heatmap` to identify which cities or neighborhoods within Nigeria have the highest concentration of affinity for this audience.

###### 5A: Country-level — which cities?

```bash
curl --request GET \
  --url 'https://api.qloo.com/v2/insights/?filter.type=urn:heatmap\
&signal.location.query=Nigeria\
&signal.interests.tags=urn:tag:genre:brand:fashion:accessories,urn:tag:style:qloo:artisan\
&signal.interests.entities=A1B2C3D4-COMPARABLE_BRAND_ID' \
  --header 'X-Api-Key: YOUR_API_KEY'
```

###### 5B: City-level — drill into Lagos

```bash
curl --request GET \
  --url 'https://api.qloo.com/v2/insights/?filter.type=urn:heatmap\
&signal.location.query=Lagos\
&signal.interests.tags=urn:tag:genre:brand:fashion:accessories,urn:tag:style:qloo:artisan\
&signal.interests.entities=A1B2C3D4-COMPARABLE_BRAND_ID' \
  --header 'X-Api-Key: YOUR_API_KEY'
```

###### 5C: Heatmap with demographic layering

```bash
curl --request GET \
  --url 'https://api.qloo.com/v2/insights/?filter.type=urn:heatmap\
&signal.location.query=Lagos\
&signal.interests.tags=urn:tag:genre:brand:fashion:accessories\
&signal.demographics.age=25_to_29,30_to_34\
&signal.demographics.gender=female' \
  --header 'X-Api-Key: YOUR_API_KEY'
```

**Parameters:**

| Parameter                    | Value                | Purpose                                  | Impact on Response                                                  |
|------------------------------|----------------------|------------------------------------------|---------------------------------------------------------------------|
| `filter.type`                | `urn:heatmap`        | Switches output to geographic cells      | Returns geohash tiles with affinity scores instead of entities      |
| `signal.location.query`      | `Nigeria` / `Lagos`  | Defines the geographic scope             | Restricts heatmap cells to that region; use city name to drill down |
| `signal.interests.tags`      | Fashion/artisan URNs | Taste signal to map geographically       | Cells where this taste is concentrated score highest                |
| `signal.interests.entities`  | Comparable brand ID  | Brand signal layered onto geography      | Finds where that brand's audience is geographically concentrated    |
| `signal.demographics.age`    | `25_to_29,30_to_34`  | Layers demographic filter onto geography | Narrows heatmap to cells where this age cohort is concentrated      |
| `signal.demographics.gender` | `female`             | Gender filter                            | Further narrows to female-skewed geographic concentrations          |

###### Example Response

```json
{
  "success": true,
  "results": {
    "heatmap": [
      {
        "location": {
          "latitude": 6.4531,
          "longitude": 3.3958,
          "geohash": "s17mp4"
        },
        "query": {
          "affinity": 0.98,
          "affinity_rank": 0.9990,
          "popularity": 0.94
        }
      },
      {
        "location": {
          "latitude": 6.5244,
          "longitude": 3.3792,
          "geohash": "s17nm2"
        },
        "query": {
          "affinity": 0.91,
          "affinity_rank": 0.9870,
          "popularity": 0.88
        }
      }
    ]
  }
}
```

**Key fields to retain:**

| Field                             | Usage                                                                                                       |
|-----------------------------------|-------------------------------------------------------------------------------------------------------------|
| `location.latitude` / `longitude` | Pass to a mapping tool to resolve to neighborhood name; pass to LLM with a reverse geocoding label          |
| `location.geohash`                | Unique cell ID; use to deduplicate and sort                                                                 |
| `query.affinity_rank`             | **Most important for targeting** — how this cell ranks vs all others (0–1). Sort descending, take top cells |
| `query.affinity`                  | Absolute interest level within the cell                                                                     |
| `query.popularity`                | Signal density at this location — high popularity + high affinity = confirmed hotspot                       |

> **LLM use:** Sort by `affinity_rank` descending. Top cells = highest-priority geographic targets. Label them with human-readable location names (e.g., "Victoria Island, Lagos") and use them to produce city/neighbourhood-level targeting recommendations.

------------------------------------------------------------------------

##### Step 6: Audience Segment Layering

Use the known audience URN taxonomy directly — no deprecated endpoint needed. Pass audience URNs as `signal.demographics.audiences` to produce audience-conditioned insights.

###### Request: What brands resonate with sustainability-minded Nigerian

*Sources cited by the assistant: Get Tag Types Taste Analysis.*

> **[Source truncated.]** The saved page ends here, mid-sentence, at Step 6. The next recorded message is the user's "Continue", with no reply.

---

### Message 14 — You

> Continue
