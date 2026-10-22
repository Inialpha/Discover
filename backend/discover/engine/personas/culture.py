"""Culture digest: boil the audience text Qloo attaches to a segment's entities down to a short, grounded document.

No LLM and no extra dependency. Everything is extractive: every phrase or sentence in the digest is Qloo's own text and
keeps the name of the entity it came from, so nothing is invented and every line can be cited.

Three parts, per segment:
  lists      Qloo list fields that describe the AUDIENCE (customer segments, adjectives for fans, audience tags...).
             Each item is scored by how much of the segment's evidence carries it (counted per entity) and by how much
             more it appears here than in the other segments of the same run (a smoothed lift), so generic items that
             every segment has do not win. Support is always "n of m entities that had the field"; an entity without
             the field simply does not vote.
  sentences  Qloo's one-sentence audience descriptions. Ranked by centrality (mean TF-IDF cosine to the others, idf taken
             from the whole run so template words like "people who appreciate" carry little weight), then chosen with
             maximal marginal relevance so the few that are kept cover different themes.
  platforms  Social platforms found in the entities' `external` block, from a fixed allowlist of platforms advertisers can
             use. Never chosen by price or by anything else about the product.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Any, Iterable

# Qloo property -> kind of text. Only fields that talk about the audience, not about the entity itself.
LIST_FIELDS: dict[str, tuple[str, ...]] = {
    "brand": ("customer_segments", "interest_adjacencies", "cultural_relevance", "influencer_appeal"),
    "artist": ("adjectives_for_fans",),
    "videogame": ("audience_tags",),
    "place": ("good_for",),
}
SENTENCE_FIELDS: dict[str, tuple[str, ...]] = {
    "brand": ("audience_identity", "target_demographics_description", "situational_contexts"),
    "movie": ("audience_identity", "situational_contexts"),
    "tv_show": ("audience_identity", "situational_contexts"),
    "place": ("customer_demographics_description",),
}
# `external` keys that are platforms an advertiser can reach people on. Anything else (imdb, wikidata, musicbrainz, lastfm,
# goodreads, letterboxd, metacritic, rottentomatoes, itunes, ...) is dropped without asking anyone.
PLATFORMS: dict[str, str] = {
    "facebook": "Facebook", "instagram": "Instagram", "twitter": "X (Twitter)", "twitter_username": "X (Twitter)",
    "youtube": "YouTube", "tiktok": "TikTok", "snapchat": "Snapchat", "linkedin": "LinkedIn",
    "twitch": "Twitch", "spotify": "Spotify", "netflix": "Netflix",
}

SENTENCE_CHARS = 200
_STOP = frozenset("a an and are as at be but by for from has have in into is it its of on or that the their them they this to "
                  "who whom whose with often both can like also more most very well".split())


def _kind(e: dict[str, Any]) -> str:
    sub = str(e.get("subtype") or e.get("type") or "")
    return sub.rsplit(":", 1)[-1]


def _items(value: Any) -> list[str]:
    """A Qloo list field as clean strings (some are lists of {'name': ...} dicts)."""
    out: list[str] = []
    for v in value if isinstance(value, list) else ([value] if isinstance(value, str) else []):
        t = v.get("name") if isinstance(v, dict) else v
        if isinstance(t, str) and t.strip():
            out.append(" ".join(t.split()))
    return out


def _canon(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", s.lower().replace("-", " ")).strip()


def _tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in _STOP]


def _clip(t: str, n: int = SENTENCE_CHARS) -> str:
    t = " ".join(t.split())
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _props(e: dict[str, Any]) -> dict[str, Any]:
    return e.get("properties") if isinstance(e.get("properties"), dict) else {}


# --------------------------------------------------------------------------------------------- lists

def _list_stats(entities: list[dict[str, Any]]) -> tuple[dict[str, dict[str, dict[str, Any]]], dict[str, int]]:
    """(field -> canonical item -> {label, n, names}, field -> number of entities that carry the field)."""
    stats: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    carry: dict[str, int] = defaultdict(int)
    for e in entities:
        for f in LIST_FIELDS.get(_kind(e), ()):
            vals = _items(_props(e).get(f))
            if not vals:
                continue
            carry[f] += 1
            for c, label in {_canon(v): v for v in vals}.items():
                slot = stats[f].setdefault(c, {"label": label, "n": 0, "names": [], "eids": []})
                slot["n"] += 1
                slot["names"].append(e.get("name"))
                if e.get("evidence_id"):
                    slot["eids"].append(e["evidence_id"])
    return stats, carry


MIN_SUPPORT = 2  # an item carried by a single entity is an anecdote, not a pattern
MIN_LIFT = 1.5   # items that every segment has ("Loyal") say nothing about this one; applied once the baseline is big enough
MIN_BASELINE = 8


def rank_lists(seg_entities: list[dict[str, Any]], base_entities: list[dict[str, Any]], top: int = 6) -> dict[str, Any]:
    """Per list field: the items most carried by this segment's entities and most distinctive against the baseline.
    Items need at least MIN_SUPPORT entities behind them; a field with no such item is left out."""
    seg, carry = _list_stats(seg_entities)
    base, carry_b = _list_stats(base_entities)
    out: dict[str, Any] = {}
    for f, items in seg.items():
        m, mb = carry[f], carry_b.get(f, 0)
        rows = []
        for c, s in items.items():
            if s["n"] < MIN_SUPPORT:
                continue
            share = s["n"] / m
            b = base.get(f, {}).get(c, {}).get("n", 0)
            share_b = (b + 0.5) / (mb + 1.0)  # smoothed: an item the baseline never saw is not infinitely distinctive
            lift = share / share_b
            if mb >= MIN_BASELINE and lift < MIN_LIFT:
                continue
            rows.append({"item": s["label"], "n": s["n"], "of": m, "lift": round(lift, 2),
                         "score": round(share * math.log2(1.0 + lift), 3),
                         "from": [x for x in dict.fromkeys(s["names"]) if x][:3],
                         "evidence": list(dict.fromkeys(s["eids"]))[:3]})
        rows.sort(key=lambda r: (-r["score"], -r["n"], r["item"]))
        if rows:
            out[f] = rows[:top]
    return out


# ----------------------------------------------------------------------------------------- sentences

def _sentence_pool(entities: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    pool: list[dict[str, str]] = []
    for e in entities:
        for f in SENTENCE_FIELDS.get(_kind(e), ()):
            t = _props(e).get(f)
            if isinstance(t, str) and len(t.split()) >= 5:
                pool.append({"text": " ".join(t.split()), "entity": e.get("name") or "", "kind": _kind(e), "field": f,
                             "eid": e.get("evidence_id") or ""})
    return pool


def _vectors(texts: list[str], idf_docs: list[str]) -> list[dict[str, float]]:
    df: dict[str, int] = defaultdict(int)
    for d in idf_docs:
        for w in set(_tokens(d)):
            df[w] += 1
    n = len(idf_docs) + 1
    vecs = []
    for t in texts:
        tf: dict[str, float] = defaultdict(float)
        for w in _tokens(t):
            tf[w] += 1.0
        v = {w: (1 + math.log(c)) * (math.log((n + 1) / (df.get(w, 0) + 1)) + 1.0) for w, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({w: x / norm for w, x in v.items()})
    return vecs


def _cos(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(w, 0.0) for w, x in a.items())


def pick_sentences(seg_entities: list[dict[str, Any]], base_entities: list[dict[str, Any]], k: int = 4,
                   lam: float = 0.7) -> list[dict[str, Any]]:
    """k central-but-different sentences. Centrality = mean cosine to the other sentences; MMR then trades it off
    against similarity to what has already been picked."""
    pool, seen = [], set()
    for p in _sentence_pool(seg_entities):
        if p["text"] not in seen:
            seen.add(p["text"])
            pool.append(p)
    if not pool:
        return []
    texts = [p["text"] for p in pool]
    vecs = _vectors(texts, [p["text"] for p in _sentence_pool(base_entities)] + texts)
    n = len(pool)
    cent = [sum(_cos(vecs[i], vecs[j]) for j in range(n) if j != i) / max(1, n - 1) for i in range(n)]
    hi = max(cent) or 1.0
    cent = [c / hi for c in cent]
    chosen: list[int] = []
    while len(chosen) < min(k, n):
        best, best_s = -1, -1e9
        for i in range(n):
            if i in chosen or pool[i]["entity"] in {pool[j]["entity"] for j in chosen}:
                continue  # one sentence per entity, so a single brand cannot fill the digest
            red = max((_cos(vecs[i], vecs[j]) for j in chosen), default=0.0)
            s = lam * cent[i] - (1 - lam) * red
            if s > best_s:
                best, best_s = i, s
        if best < 0:
            break
        chosen.append(best)
    return [{"text": _clip(pool[i]["text"]), "entity": pool[i]["entity"], "kind": pool[i]["kind"],
             "evidence": pool[i]["eid"], "centrality": round(cent[i], 2)} for i in chosen]


# ----------------------------------------------------------------------------------------- platforms

def platforms(seg_entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Allowlisted social platforms found in the entities' `external` blocks, with how many entities carry each."""
    carriers: dict[str, set[str]] = defaultdict(set)
    eids: dict[str, list[str]] = defaultdict(list)
    for e in seg_entities:
        ext = e.get("external") or _props(e).get("external") or {}
        keys = set(ext) if isinstance(ext, dict) else set()
        keys |= set(e.get("external_keys") or [])
        for label in {PLATFORMS[k.lower()] for k in map(str, keys) if k.lower() in PLATFORMS}:
            carriers[label].add(e.get("name") or "")
            if e.get("evidence_id"):
                eids[label].append(e["evidence_id"])
    total = len(seg_entities)
    rows = [{"platform": p, "n": len(v), "of": total, "examples": sorted(x for x in v if x)[:3],
             "evidence": list(dict.fromkeys(eids[p]))[:4]} for p, v in carriers.items()]
    rows.sort(key=lambda r: (-r["n"], r["platform"]))
    return rows


def digest(seg_entities: list[dict[str, Any]], base_entities: list[dict[str, Any]], *, top: int = 6,
           sentences: int = 4) -> dict[str, Any]:
    """The whole digest for one segment. `base_entities` are the other segments' entities from the same run."""
    return {"lists": rank_lists(seg_entities, base_entities, top), "sentences": pick_sentences(seg_entities, base_entities, sentences),
            "platforms": platforms(seg_entities), "entities": len(seg_entities)}
