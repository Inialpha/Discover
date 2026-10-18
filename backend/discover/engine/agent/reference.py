"""What the agent knows about Qloo, as sections it can look up with the `qloo_help` tool (so prompts stay small).
Every line is tagged: VERIFIED = seen in our live runs; DOCUMENTED = from Qloo's documentation, not yet seen live."""

from __future__ import annotations

AGE_BANDS = ("24_and_younger", "25_to_29", "30_to_34", "35_to_44", "45_to_54", "55_and_older")

SECTIONS: dict[str, str] = {
    "overview": """Qloo is a taste/culture graph. Entities (brands, places, artists, movies, tv_shows, podcasts, books, games, destinations, people) are linked by audience overlap. Tags describe entities. Main calls: search (name -> entity id), entity record (all tags), tags (find tag ids), insights (ranked entities/tags/demographics/heatmap for a set of signals), compare (shared tags of two groups).
Help topics: kinds, filters, signals, weights, demographics, tags, response, pitfalls, recipes.""",

    "kinds": """Entity kinds (use in search_entity.kind and insights.kind): brand, place, movie, tv_show, artist, podcast, book, game, destination, person. [VERIFIED for brand, place, artist, tv_show]
Brands have no location filter (location only nudges ranking). Places and destinations accept hard location filters.""",

    "filters": """FILTERS restrict which entities can come back.
- filter_tags: [tag ids]  HARD membership filter: every result carries at least one of these tags. [VERIFIED: skincare tag -> 8/8 skincare brands]
- filter_operator: union (default, OR) or intersection (AND). With intersection and very specific pairs the result can be empty: fall back to union. [DOCUMENTED]
- kind: which entity kind to return (insights.kind).
- Location is fixed by the run. Brand location is a soft signal; narrow categories can be empty for one city: retry with use_location=false and say so. [VERIFIED: oral_care + Lagos -> 0]
- exclude_tags: [tag ids] removes entities carrying these tags. [DOCUMENTED, not live-verified]""",

    "signals": """SIGNALS bias ranking (they do not restrict).
- interest_entities: [entity ids] returns what the audience of those entities likes: taste neighbours across categories, NOT same-category peers. [VERIFIED]
- interest_tags: [tag ids] SOFT taste signal: does NOT restrict category (0/10 matching brands). [VERIFIED]
- Best peer recipe: filter_tags=[category tag] + interest_entities=[anchor brand]: category brands ranked by similarity to the anchor. [VERIFIED]
- audiences: [urn:audience:...] named audience groups such as urn:audience:life_stage, urn:audience:spending_habits, urn:audience:communities. [DOCUMENTED, not live-verified]
- age / gender: demographic signals (see demographics). Age alone barely re-orders results: pair it with an interest signal. [DOCUMENTED + observed]""",

    "weights": """weights: {signal name: strength}. Names: interests.entities, interests.tags, demographics.age, demographics.audiences. Strengths: very_low, low, medium, high, very_high. Each weight is independent: raising one does not lower the others. [DOCUMENTED, not live-verified; the tool drops weights and retries if Qloo rejects them]
Use high on the signal that should drive the result and low on the rest.""",

    "demographics": f"""age buckets (exact strings): {', '.join(AGE_BANDS)}. gender: male | female.
audience_demographics(entity_ids) returns a RELATIVE index per age band and gender for the audience of those entities (negative = under-indexes). It is not a share and is noisy between neighbouring bands. [VERIFIED]
Qloo has no income, platform or events data. Do not claim any.""",

    "tags": """Tag ids look like <namespace>:<...> (the urn:tag: prefix is added for you). Useful namespaces for brands:
- genre:brand:<group>:<category>  the product category, e.g. genre:brand:health_and_beauty:oral_care. Use for filter_tags. Hierarchical: a parent tag also matches its children. [VERIFIED]
- competitor_brand, similar_brand  names of competing / similar brands on a brand record. [VERIFIED]
- customer_segment, industry, product_service, brand_type, price_range, business_model  what the brand is and who buys it. [VERIFIED]
- aesthetic_property, lifestyle, core_value ... descriptive taste tags, good for audience_taste and persona colour, not for category.
find_tags(query, namespace) searches by MEANING (semantic): "toothpaste" finds oral_care. Results are noisy and ordered by relevance: read the names. Never invent a tag id. Enumerating a namespace without a query returns only a subset. [VERIFIED]
Place categories (urn:tag:category:place:*) are for places, never for brands.""",

    "response": """What comes back:
- search_entity / insights: entities with id, name, pop (popularity 0-1), aff (affinity, only when signals were sent), tags grouped by namespace. Qloo search is semantic: it can return lookalikes (a query "Colgate toothpaste" returned Colgate University and Crest). Always read industry / genre / product_service tags. [VERIFIED]
- entity_record: all tags grouped, including competitor_brand / similar_brand / customer_segment names.
- audience_taste: tags the audience over-indexes on, with aff.
- audience_demographics: age_index, gender_index (relative).
- heatmap: lat/lon points with affinity, no place names.
- compare: shared_tags with score; it returns tags only, never entities. Tags missing from the shared set are your differentiation space. [DOCUMENTED]""",

    "pitfalls": """1. interest_tags is not a category filter: use filter_tags.
2. interest_entities alone returns taste neighbours (Colgate's audience also likes Olay, Clorox): not competitors.
3. Several filter_tags default to OR. Set filter_operator=intersection for AND.
4. Location on brands is a soft signal; a filter on brands is silently ignored.
5. Demographics alone barely change a ranking: add an interest signal and weights.
6. A brand name may be the wrong entity (a university): check tags.
7. The business's own product is usually not in Qloo: search its competitors and category instead.
8. Narrow category + one city can be empty: use_location=false.""",

    "recipes": """RECIPES
A. Real competitors of a product: find_tags(product word, namespace genre:brand) -> pick the category tag -> search_entity(each given competitor) -> check tags -> entity_record(anchor): read competitor_brand / similar_brand -> insights(kind=brand, filter_tags=[category], interest_entities=[anchor]) -> keep brands whose tags carry the category and whose industry fits.
B. Who buys it: audience_demographics(entity_ids=[verified competitors]) for age/gender; entity_record customer_segment tags for named segments; audience_taste(interest_entities=[...]) for tastes.
C. Where to reach them: heatmap(interest_entities=[...], age=[bands]) for areas; insights(kind=place, interest_entities=[...], age=[...]) for venues.
D. How two groups differ: compare(a=[brand ids], b=[brand ids]) for shared tags; tags only in one side's taste are differentiators.
E. Segment differentiation: insights(kind=..., interest_entities=[anchor], age=[bands], weights={"interests.entities":"high","demographics.age":"high"}) so age actually changes the ranking.""",
}


def help_text(topic: str | None) -> str:
    t = (topic or "overview").strip().lower()
    if t in SECTIONS:
        return SECTIONS[t]
    near = [k for k in SECTIONS if t in k or k in t]
    return SECTIONS[near[0]] if near else f"Unknown topic {topic!r}. Topics: {', '.join(SECTIONS)}."
