from discover.engine.personas import culture as C


def ent(name, kind, **props):
    ext = props.pop("external", None)
    return {"name": name, "subtype": f"urn:entity:{kind}", "properties": props, **({"external": ext} if ext else {})}


def test_lists_need_support_and_beat_generic_items():
    seg = [ent(f"b{i}", "brand", customer_segments=["Families", "Students"] if i < 3 else ["Families"], interest_adjacencies=["Rare"] if i == 0 else []) for i in range(4)]
    base = [ent(f"x{i}", "brand", customer_segments=["Families"]) for i in range(8)]
    rows = C.rank_lists(seg, base)["customer_segments"]
    assert [r["item"] for r in rows][0] == "Students"          # distinctive beats the universal item
    assert all(r["n"] >= C.MIN_SUPPORT for r in rows)
    assert "interest_adjacencies" not in C.rank_lists(seg, base)  # only a single entity carried it
    assert rows[0]["of"] == 4                                   # support is out of entities that had the field


def test_missing_fields_do_not_vote():
    seg = [ent("a", "artist", adjectives_for_fans=["Loyal"]), ent("b", "artist", adjectives_for_fans=["Loyal"]), ent("c", "artist")]
    row = C.rank_lists(seg, [])["adjectives_for_fans"][0]
    assert (row["n"], row["of"]) == (2, 2)


def test_sentences_are_extractive_diverse_and_one_per_entity():
    s = [ent("A", "brand", audience_identity="Parents who want gentle safe products for infants and young children at home.",
             situational_contexts="Used daily at home during bath time with children around the house."),
         ent("B", "brand", audience_identity="Parents who want gentle safe products for babies and young children at home."),
         ent("C", "tv_show", audience_identity="Viewers who enjoy fast action thrillers with explosive stunts and chase scenes.")]
    out = C.pick_sentences(s, [], k=3)
    names = [o["entity"] for o in out]
    assert len(names) == len(set(names))
    src = {p["text"] for p in C._sentence_pool(s)}
    assert all(o["text"].rstrip("…") in " ".join(src) for o in out)  # nothing is written, only selected


def test_platforms_come_from_allowlist_only():
    s = [ent("A", "artist", external={"instagram": [{"id": "x"}], "imdb": [{"id": "n"}], "spotify": [{"id": "s"}]}),
         ent("B", "brand", external={"twitter": [{"id": "t"}], "wikidata": [{"id": "q"}], "instagram": [{"id": "y"}]})]
    got = {p["platform"]: p["n"] for p in C.platforms(s)}
    assert got == {"Instagram": 2, "Spotify": 1, "X (Twitter)": 1}
