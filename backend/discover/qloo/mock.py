"""Offline mock transport. Responses are SYNTHETIC (shapes follow entity_examples/) and flagged as such.

Used for `--mock` runs and the test suite. Deterministic: values derive from a crc32 of the request.
`reject` lets tests simulate a spelling Qloo refuses (HTTP 400) to exercise variant fallback.
"""

from __future__ import annotations

import zlib
from typing import Callable

import httpx

_NAMES = {
    "movie": ["Blood Sisters", "Jagun Jagun", "Brotherhood", "King of Boys", "Anikulapo"],
    "tv_show": ["Big Brother Naija", "Shanty Town", "Skinny Girl in Transit", "Jenifa's Diary", "The Real Housewives of Lagos"],
    "artist": ["Burna Boy", "Tems", "Asake", "Ayra Starr", "Rema"],
    "podcast": ["Naija Money Talks", "The Honest Bunch", "Industry Nite", "Zero Chill", "Gist Lounge"],
    "brand": ["Zara", "Fenty Beauty", "Glo", "Jumia", "Paystack"],
    "place": ["Nkoyo Lagos", "Terra Kulture", "Shiro", "The Palms Mall", "Lekki Conservation Centre"],
    "book": ["Stay With Me", "Born on a Tuesday", "Americanah", "Lagoon", "Children of Blood and Bone"],
    "game": ["FIFA", "Candy Crush", "Ludo King", "Call of Duty Mobile", "Subway Surfers"],
    "destination": ["Lagos", "Abuja", "Accra", "Cape Town", "Zanzibar"],
    "person": ["Funke Akindele", "Mo Abudu", "Tiwa Savage", "Toke Makinwa", "Bovi"],
}
_TAGS = [
    ("urn:tag:genre:media:afrobeats", "Afrobeats", "urn:tag:genre:media"),
    ("urn:tag:genre:media:drama", "Drama", "urn:tag:genre:media"),
    ("urn:tag:genre:media:reality", "Reality TV", "urn:tag:genre:media"),
    ("urn:tag:genre:media:comedy", "Comedy", "urn:tag:genre:media"),
    ("urn:tag:keyword:media:lifestyle", "Lifestyle", "urn:tag:keyword:media"),
    ("urn:tag:interest:fashion", "Fashion", "urn:tag:interest"),
]


def _h(*parts: str) -> int:
    return zlib.crc32("|".join(parts).encode())


def _entity(kind: str, i: int, seed: int, with_query: bool = True) -> dict:
    names = _NAMES.get(kind, _NAMES["brand"])
    name = names[i % len(names)]
    e = {
        "entity_id": f"MOCK{seed % 100000:05d}{kind[:2].upper()}{i}",
        "name": name,
        "type": f"urn:entity:{kind}",
        "subtype": f"urn:entity:{kind}",
        "popularity": round(0.5 + ((seed + i * 7) % 49) / 100, 3),
        "tags": [{"id": t[0], "name": t[1], "type": t[2], "weight": round(0.2 + ((seed + i + j) % 5) / 10, 2)} for j, t in enumerate(_TAGS[:3])],
        "properties": {"description": f"[SYNTHETIC] {name}", "release_country": ["Mockland"], "key_markets": ["Mockland"],
                       "address": "1 Mock Street, Mockland"},
        "external": {},
    }
    if with_query:
        e["query"] = {"affinity": round(0.55 + ((seed + i * 13) % 40) / 100, 3), "measurements": {"audience_growth": 0.1}}
    return e


def make_transport(reject: Callable[[httpx.Request], bool] | None = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if reject and reject(request):
            return httpx.Response(400, json={"success": False, "errors": ["mock: parameter not accepted"]})
        path = request.url.path
        q = dict(request.url.params)
        seed = _h(path, *(f"{k}={v}" for k, v in sorted(q.items())))
        if path == "/search":
            kind = (q.get("types") or q.get("filter.type") or "urn:entity:brand").split(":")[-1]
            term = q.get("query", "x")
            results = [{
                "entity_id": f"MOCKS{_h(term, str(i)) % 100000:05d}",
                "name": term.title() if i == 0 else f"{term.title()} {i}",
                "types": [f"urn:entity:{kind}"],
                "popularity": round(0.9 - i * 0.1, 2),
                "disambiguation": "[SYNTHETIC]",
                "tags": [],
            } for i in range(int(q.get("take", 3)))]
            return httpx.Response(200, json={"success": True, "results": results})
        if path == "/v2/tags":
            term = q.get("filter.query") or q.get("query") or "tag"
            tags = [{"id": f"urn:tag:keyword:mock:{term.lower().replace(' ', '_')}", "name": term.title(), "type": "urn:tag:keyword:mock"}]
            return httpx.Response(200, json={"success": True, "results": {"tags": tags}})
        if path == "/v2/insights":
            ft = q.get("filter.type", "")
            if ft == "urn:tag":
                tags = [{"id": t[0], "name": t[1], "type": t[2], "query": {"affinity": round(0.6 + ((seed + i * 11) % 35) / 100, 3)}} for i, t in enumerate(_TAGS)]
                return httpx.Response(200, json={"success": True, "results": {"tags": tags}})
            if ft == "urn:demographics":
                age = {"24_and_younger": 0.2, "25_to_29": 0.32, "30_to_34": 0.25, "35_to_44": 0.15, "45_to_54": 0.05, "55_and_older": 0.03}
                return httpx.Response(200, json={"success": True, "results": {"demographics": [{"entity_id": "MOCK", "query": {"age": age, "gender": {"female": 0.58, "male": 0.42}}}]}})
            if ft == "urn:heatmap":
                pts = [{"location": {"geohash": g, "latitude": 6.45 + i * 0.02, "longitude": 3.4 + i * 0.02}, "query": {"affinity": round(0.9 - i * 0.1, 2), "popularity": round(0.5 + i * 0.05, 2)}}
                       for i, g in enumerate(["s0yd5k", "s0yd5m", "s0yd5q", "s0yd5w"])]
                return httpx.Response(200, json={"success": True, "results": {"heatmap": pts}})
            kind = ft.split(":")[-1] or "brand"
            n = int(q.get("take", 5))
            return httpx.Response(200, json={"success": True, "results": {"entities": [_entity(kind, i, seed) for i in range(n)]}})
        if path == "/v2/analysis/compare":
            return httpx.Response(200, json={"success": True, "results": {"tags": [{"name": "Drama", "a": 0.7, "b": 0.4}], "note": "[SYNTHETIC]"}})
        return httpx.Response(404, json={"success": False, "errors": [f"mock: unknown path {path}"]})

    return httpx.MockTransport(handler)
