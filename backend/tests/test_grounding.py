"""Middle mode: competitors named by Qloo tags, narrower category from a brand's own tags, culture-backed claims, unique names."""

from discover.engine.personas import lean, writer as W


def tag(i, n):
    return {"id": i, "name": n}


def test_tag_competitor_names_skip_known_and_rank_by_sharing():
    crest = {"name": "Crest", "query": "Crest", "tags": [tag("urn:tag:competitor_brand:qloo:colgate", "Colgate"), tag("urn:tag:competitor_brand:qloo:aim", "Aim")]}
    senso = {"name": "Sensodyne", "query": "Sensodyne", "tags": [tag("urn:tag:competitor_brand:qloo:colgate", "Colgate"), tag("urn:tag:competitor_brand:qloo:crest", "Crest")]}
    assert lean.tag_competitor_names([crest, senso]) == ["Colgate", "Aim"]


def test_record_competitor_names_skip_used_and_rejected():
    crest = {"competitors": ["Colgate", "Sensodyne", "Arm & Hammer"], "similar": []}
    senso = {"competitors": ["Colgate", "Crest", "Arm & Hammer"], "similar": ["Pronamel", "Oral-B"]}
    anchors = [{"name": "Crest", "query": "Crest"}, {"name": "Sensodyne", "query": "Sensodyne"}]
    assert lean.record_competitor_names([crest, senso], anchors, []) == ["Arm & Hammer", "Colgate"]
    assert lean.record_competitor_names([crest, senso], anchors, ["Colgate"]) == ["Arm & Hammer", "Oral-B"]


def test_accepted_brand_records_feed_the_market_culture_and_rejected_ones_do_not():
    from discover.engine.personas.evidence import culture_for
    def prof(i, name, segs, **kw):
        return {"id": i, "step": "brand_profile", "ok": True, "segment": None, "label": "x", "data": {"name": name, "segments": segs, **kw}}
    items = [prof("E004", "Crest", ["Families", "Health-Conscious Consumers"]),
             prof("E006", "Colgate", ["Undergraduate Scholars"], rejected=True)]
    c = culture_for(items, "Everyday", [])
    got = [r["item"] for r in c["market"]["lists"]["customer_segments"]]
    assert "Families" in got and "Undergraduate Scholars" not in got


def test_deeper_category_from_a_brand_tag_stays_under_the_shared_one():
    base = {"id": "urn:tag:genre:brand:health_and_beauty", "depth": 1}
    colgate = {"tags": [tag("urn:tag:genre:brand:health_and_beauty:oral_care", "Oral Care")]}
    other = {"tags": [tag("urn:tag:genre:brand:finance:banks", "Banks")]}
    assert lean._deeper_from_anchors([other, colgate], base)["id"].endswith(":oral_care")
    assert lean._deeper_from_anchors([other], base) is None and lean._deeper_from_anchors([colgate], None) is None


def test_claim_is_evidence_only_when_it_shares_key_words_with_the_cited_entry():
    support = {"E001": ["Health-conscious families seeking dependable daily oral care Crest"]}
    ok = W.supported_by("Families want dependable daily care", support["E001"], "brightsmile toothpaste")
    off = W.supported_by("Loves emotional drama series", support["E001"], "brightsmile toothpaste")
    assert ok and not off


def test_first_names_are_unique_within_a_run():
    assert W.unique_name("Emily", "female", {"Emily"}) != "Emily"
    assert W.unique_name("Emily", "female", set()) == "Emily"
