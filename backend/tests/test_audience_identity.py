from discover.engine.personas.evidence import AUDIENCE_MAX, _audience_text, segment_view
from discover.engine.personas.scoring import SegmentScore


def _seg():
    return SegmentScore(id="s", label="Seg", description="", ages=("25_to_29",), gender=None, score=0.5, confidence="low",
                        components={}, reach={}, matched_keywords=[], rationale=[])


def test_audience_text_trims_on_word_boundary_and_skips_missing():
    assert _audience_text({"properties": {}}) is None
    assert _audience_text({"properties": {"audience_identity": "   "}}) is None
    long = " ".join(["warm"] * 100)
    t = _audience_text({"properties": {"audience_identity": long}})
    assert t.endswith("…") and len(t) <= AUDIENCE_MAX + 1 and "  " not in t
    assert _audience_text({"properties": {"audience_identity": "Parents who value safety."}}) == "Parents who value safety."


def test_segment_view_passes_audience_only_when_present():
    items = [{"id": "E1", "step": "affinity", "ok": True, "segment": "Seg", "data": {"kind": "brand", "entities": [
        {"name": "A", "properties": {"audience_identity": "People who like bold flavour."}},
        {"name": "B", "properties": {}}]}}]
    got = segment_view(items, _seg())["lists"]["brand"]["items"]
    assert got[0]["audience"] == "People who like bold flavour."
    assert "audience" not in got[1]
