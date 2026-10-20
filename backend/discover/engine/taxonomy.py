"""Qloo tag taxonomy crawl and live category probe (commands: `discover taxonomy`, `discover category-probe`).

Why: brand tags are hierarchical categories (urn:tag:genre:brand:health_and_beauty:skincare). If we know which categories
exist, the LLM can be asked to PICK one from the real list instead of guessing words, and Qloo can then return brands in
that category. These commands collect the facts we cannot see from the sandbox: what the namespaces are, how many categories
exist, whether paging works, and whether `filter.tags` really restricts brands to a category.
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import Settings
from .personas.competitors import genre_paths
from .qloo import calls, normalize as nz
from .qloo.client import QlooClient
from .recorder import RunRecorder

GENRE_TYPES = ("urn:tag:genre:brand",)


PRIORITY_BRAND = ("urn:tag:genre:brand", "urn:tag:industry:qloo", "urn:tag:product_service:qloo", "urn:tag:customer_segment:qloo",
                  "urn:tag:competitor_brand:qloo", "urn:tag:category:qloo", "urn:tag:price_range:qloo", "urn:tag:similar_brand:qloo")


def priority_types(kind: str, types: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    """Which namespaces to enumerate. Live run: a cap of the first 14 (alphabetical) never reached genre:brand. Category-like
    namespaces first (genre/category/industry/product/segment/competitor/price), the rest only if room is left."""
    ids = {t["id"] for t in types}
    first = [t for t in types if t["id"] in PRIORITY_BRAND] if kind == "brand" else []
    key = ("genre", "category", "industry", "product", "segment", "competitor", "price", "cuisine")
    first += [t for t in types if t not in first and any(k in t["id"] for k in key)]
    return (first + [t for t in types if t not in first])[:limit] if ids else []


async def crawl(client: QlooClient, kinds: list[str], max_pages: int = 10, take: int = 50, seeds: list[str] | None = None,
                namespace_limit: int = 10) -> dict[str, Any]:
    """{kind: {"types": [...], "namespaces": {type_id: {"tags": [...], "pages": n, "paging_works": bool, "complete": bool}}}}"""
    out: dict[str, Any] = {}
    for kind in kinds:
        res = await client.call(calls.tag_types(f"tag-types-{kind}", kind))
        types = nz.tag_types_from_body(res.body) if res.ok else []
        entry: dict[str, Any] = {"ok": res.ok, "error": res.error, "types": types, "namespaces": {}}
        for t in priority_types(kind, types, namespace_limit):
            tid = t["id"]
            seen: dict[str, dict] = {}
            pages, paging_works, complete = 0, None, False
            first_ids: set[str] = set()
            for page in range(1, max_pages + 1):
                r = await client.call(calls.tags_of_type(f"tags-{kind}-{tid.split(':')[-1]}-p{page}", tid, take=take, page=page))
                if not r.ok:
                    break
                tags = nz.tags_from_body(r.body)
                ids = {x["id"] for x in tags if x.get("id")}
                pages += 1
                if page == 1:
                    first_ids = ids
                elif ids and ids == first_ids:
                    paging_works = False  # same tags again: page is ignored
                    break
                elif ids:
                    paging_works = True
                for x in tags:
                    if x.get("id"):
                        seen.setdefault(x["id"], {"id": x["id"], "name": x.get("name")})
                if len(tags) < take:
                    complete = True
                    break
            entry["namespaces"][tid] = {"name": t.get("name"), "tags": list(seen.values()), "count": len(seen), "pages": pages,
                                        "paging_works": paging_works, "complete": complete}
        for q in (seeds or []):  # keyword searches inside the brand genre namespace: catches categories paging missed
            for tid in GENRE_TYPES:
                if kind == "brand" and tid in entry["namespaces"]:
                    r = await client.call(calls.tags_of_type(f"seed-{q}", tid, query=q, take=take))
                    for x in (nz.tags_from_body(r.body) if r.ok else []):
                        if x.get("id"):
                            ns = entry["namespaces"][tid]
                            if x["id"] not in {y["id"] for y in ns["tags"]}:
                                ns["tags"].append({"id": x["id"], "name": x.get("name"), "found_by": q})
                                ns["count"] = len(ns["tags"])
        out[kind] = entry
    return out


def category_tree(tags: list[dict[str, Any]]) -> dict[str, list[str]]:
    """top-level category -> sub-category paths, from genre:brand ids."""
    tree: dict[str, list[str]] = {}
    for t in tags:
        path = genre_paths([t])
        if path:
            p = path[0]
            tree.setdefault(p[0], [])
            if len(p) > 1:
                tree[p[0]].append(":".join(p[1:]))
    return {k: sorted(set(v)) for k, v in sorted(tree.items())}


def _brand_rows(ents: list[dict[str, Any]], category_id: str | None) -> list[dict[str, Any]]:
    rows = []
    for e in ents:
        ids = [t.get("id") for t in e.get("tags") or []]
        rows.append({"name": e.get("name"), "affinity": e.get("affinity"), "popularity": e.get("popularity"),
                     "genre_tags": [t.get("name") for t in e.get("tags") or [] if str(t.get("id", "")).startswith("urn:tag:genre")],
                     "carries_category": bool(category_id and any(i and str(i).startswith(category_id) for i in ids))})
    return rows


async def probe_category(client: QlooClient, search: list[str], categories: list[str], entity: list[str], location: str,
                         take: int = 10) -> dict[str, Any]:
    """Live experiment: does a hard tag filter return brands of that category? Does 'related brands' stay in category?"""
    out: dict[str, Any] = {"searches": {}, "categories": {}, "related": {}}
    cats = list(categories)
    for q in search:
        r = await client.call(calls.tags_of_type(f"search-{q}", "urn:tag:genre:brand", query=q, take=10, semantic=True))
        tags = nz.tags_from_body(r.body) if r.ok else []
        out["searches"][q] = {"ok": r.ok, "candidates": tags}
        cats += [t["id"] for t in tags[:3] if t.get("id") and t["id"] not in cats]
    for cid in cats:
        hard = await client.call(calls.insights_entities("probe", f"hard-{cid.split(':')[-1]}", "brand",
                                                         calls.Signals(filter_tags=[cid], location=location), take=take,
                                                         explain=False, allow_no_location=True))
        soft = await client.call(calls.insights_entities("probe", f"soft-{cid.split(':')[-1]}", "brand",
                                                         calls.Signals(tags=[cid], location=location), take=take,
                                                         explain=False, allow_no_location=True))
        nolocation = await client.call(calls.insights_entities("probe", f"hard-nolocation-{cid.split(':')[-1]}", "brand",
                                                               calls.Signals(filter_tags=[cid]), take=take, explain=False))
        out["categories"][cid] = {
            name: {"ok": r.ok, "status": r.status, "error": r.error,
                   "brands": _brand_rows(nz.entities_from_insights(r.body) if r.ok else [], cid)}
            for name, r in (("hard_filter_with_location", hard), ("soft_signal_with_location", soft), ("hard_filter_no_location", nolocation))}
    for name in entity:
        r = await client.call(calls.search_entities(f"find-{name}", name, "brand", take=3))
        cands = nz.entities_from_search(r.body) if r.ok else []
        if not cands:
            out["related"][name] = {"error": "not found"}
            continue
        base = cands[0]
        rel = await client.call(calls.insights_entities("probe", f"related-{name}", "brand",
                                                        calls.Signals(entities=[base["entity_id"]], location=location), take=take,
                                                        explain=False, allow_no_location=True))
        det = await client.call(calls.entity_by_id(f"detail-{name}", base["entity_id"]))
        extras = nz.entity_extras(det.body) if det.ok else {}
        out.setdefault("entity_detail", {})[name] = {
            "ok": det.ok, "status": det.status, "competitive_set": extras.get("competitive_set"),
            "complementary_brands": extras.get("complementary_brands"),
            "genre_tag_ids": [t["id"] for t in extras.get("tags", []) if str(t.get("id", "")).startswith("urn:tag:genre:brand:")],
            "tag_namespaces": sorted({str(t.get("type")) for t in extras.get("tags", [])})}
        gids = [t["id"] for t in base.get("tags", []) if str(t.get("id", "")).startswith("urn:tag:genre:brand:")]
        gids.sort(key=lambda i: -i.count(":"))
        out.setdefault("anchor_categories", {})[name] = {}
        for gid in gids[:3]:
            row = {}
            for scope, loc, ents_sig in (("local", location, []), ("local_with_anchor_signal", location, [base["entity_id"]]),
                                         ("global", None, []), ("global_with_anchor_signal", None, [base["entity_id"]])):
                rr = await client.call(calls.insights_entities("probe", f"anchorcat-{name}-{gid.split(':')[-1]}-{scope}", "brand",
                                                               calls.Signals(filter_tags=[gid], entities=ents_sig, location=loc), take=take,
                                                               explain=False, allow_no_location=False))
                row[scope] = {"ok": rr.ok, "brands": _brand_rows(nz.entities_from_insights(rr.body) if rr.ok else [], gid)}
            out["anchor_categories"][name][gid] = row
        out["related"][name] = {"anchor": base["name"], "anchor_genre": [t["name"] for t in base.get("tags", [])],
                                "anchor_genre_ids": gids,
                                "brands": _brand_rows(nz.entities_from_insights(rel.body) if rel.ok else [], None)}
    return out


def tree_markdown(cat: dict[str, Any]) -> str:
    L = ["# Qloo tag taxonomy (as returned by the API)", ""]
    for kind, e in cat.items():
        L += [f"## {kind}", ""]
        if not e["ok"]:
            L += [f"tag types call failed: {e['error']}", ""]
            continue
        L += ["Namespaces: " + ", ".join(f"`{t['id']}` ({e['namespaces'].get(t['id'], {}).get('count', '?')} tags)" for t in e["types"]), ""]
        for tid, ns in e["namespaces"].items():
            L += [f"- `{tid}`: {ns['count']} tags, pages fetched {ns['pages']}, paging works: {ns['paging_works']}, complete: {ns['complete']}"]
        g = e["namespaces"].get("urn:tag:genre:brand")
        if kind == "brand" and g:
            L += ["", "### Brand categories (genre tree)", ""]
            for top, subs in category_tree(g["tags"]).items():
                L.append(f"- **{top}**" + (f": {', '.join(subs[:12])}{' ...' if len(subs) > 12 else ''}" if subs else ""))
        L.append("")
    return "\n".join(L)


def probe_markdown(res: dict[str, Any]) -> str:
    L = ["# Category probe", ""]
    for q, s in res["searches"].items():
        L += [f"## Tag search '{q}' (brand genre namespace)", ""] + [f"- `{t['id']}` — {t['name']}" for t in s["candidates"]] + [""]
    for cid, modes in res["categories"].items():
        L += [f"## Category `{cid}`", ""]
        for mode, m in modes.items():
            n = len(m["brands"])
            hit = sum(1 for b in m["brands"] if b["carries_category"])
            L += [f"**{mode}**: ok={m['ok']} status={m['status']} · {hit}/{n} brands carry the category", ""]
            L += [f"- {b['name']} {'✔' if b['carries_category'] else '✘'} — {', '.join(b['genre_tags'][:3])}" for b in m["brands"]] + [""]
    for name, d in res.get("entity_detail", {}).items():
        L += [f"## Entity record for {name} (GET /entities)", "", f"ok={d['ok']} status={d['status']}",
              f"- competitive_set: {d['competitive_set']}", f"- complementary_brands: {d['complementary_brands']}",
              f"- genre tags: {d['genre_tag_ids']}", f"- tag namespaces present: {d['tag_namespaces']}", ""]
    for name, cats in res.get("anchor_categories", {}).items():
        L += [f"## Categories named by {name}'s own tags, tested as hard filters", ""]
        for gid, row in cats.items():
            for scope, m in row.items():
                hit = sum(1 for b in m["brands"] if b["carries_category"])
                L += [f"**{gid}** ({scope}): {hit}/{len(m['brands'])} carry it — " + ", ".join(b["name"] for b in m["brands"][:8]), ""]
    for name, r in res["related"].items():
        L += [f"## Related brands for {name}", ""]
        if "error" in r:
            L += [r["error"], ""]
            continue
        L += [f"Anchor: {r['anchor']} ({', '.join(r['anchor_genre'][:4])})", ""]
        L += [f"- {b['name']} — {', '.join(b['genre_tags'][:3])}" for b in r["brands"]] + [""]
    return "\n".join(L)


def add_parsers(sub: Any) -> None:
    t = sub.add_parser("taxonomy", help="crawl Qloo's tag namespaces and categories (what categories exist per entity kind)")
    t.add_argument("--kinds", default="brand"); t.add_argument("--pages", type=int, default=10)
    t.add_argument("--seed", default="toothpaste,skincare,smartphone,beverage,bank,software,fashion,restaurant,fitness,travel",
                   help="keywords searched inside the brand genre namespace to catch categories paging misses")
    t.add_argument("--out", default="runs"); t.add_argument("--max-calls", type=int, default=120)
    t.add_argument("--delay", type=float, default=0.0); t.add_argument("--no-zip", action="store_true"); t.add_argument("--mock", action="store_true")
    c = sub.add_parser("category-probe", help="live test: do hard tag filters and related-brands calls stay inside a category?")
    c.add_argument("--search", action="append", default=[], help='keyword to find brand categories, e.g. "oral care" (repeatable)')
    c.add_argument("--category", action="append", default=[], help="tag id, e.g. urn:tag:genre:brand:health_and_beauty (repeatable)")
    c.add_argument("--entity", action="append", default=[], help="brand name to test related-brands from (repeatable)")
    c.add_argument("--location", default="Lagos"); c.add_argument("--take", type=int, default=10)
    c.add_argument("--out", default="runs"); c.add_argument("--max-calls", type=int, default=80)
    c.add_argument("--delay", type=float, default=0.0); c.add_argument("--no-zip", action="store_true"); c.add_argument("--mock", action="store_true")


def run(args: argparse.Namespace, settings: Settings | None = None, transport: Any = None) -> int:
    from .qloo.mock import make_transport
    settings = settings or Settings.from_env()
    if not settings.qloo_api_key and not args.mock:
        print("QLOO_API_KEY missing")
        return 3
    name = "taxonomy" if args.cmd == "taxonomy" else "category-probe"
    run_dir = Path(args.out) / f"{datetime.now():%Y%m%d-%H%M%S}_{name}"
    rec = RunRecorder(run_dir)
    started = time.time()

    async def go() -> tuple[dict[str, Any], QlooClient]:
        async with QlooClient(settings, rec, transport=transport or (make_transport() if args.mock else None), max_calls=args.max_calls,
                              concurrency=1, delay=args.delay, synthetic=args.mock) as c:
            if args.cmd == "taxonomy":
                res = await crawl(c, [k.strip() for k in args.kinds.split(",") if k.strip()], args.pages,
                                  seeds=[s.strip() for s in args.seed.split(",") if s.strip()])
            else:
                if not (args.search or args.category or args.entity):
                    raise SystemExit("give at least one of --search, --category, --entity")
                res = await probe_category(c, args.search, args.category, args.entity, args.location, args.take)
            return res, c
    res, client = asyncio.run(go())
    rec.write_json("01_taxonomy.json" if args.cmd == "taxonomy" else "01_probe.json", res)
    md = tree_markdown(res) if args.cmd == "taxonomy" else probe_markdown(res)
    rec.write_text("02_summary.md", md)
    ok = sum(1 for r in client.results if r.ok)
    rec.write_json("99_run_summary.json", {"calls": len(client.results), "ok": ok, "seconds": round(time.time() - started, 1),
                                           "failures": [{"label": r.spec.label, "status": r.status, "error": r.error} for r in client.results if not r.ok]})
    print(md[:3000])
    print(f"run folder : {run_dir}\nqloo calls : {ok}/{len(client.results)} ok")
    if not args.no_zip:
        print("send me    :", shutil.make_archive(str(run_dir), "zip", run_dir.parent, run_dir.name))
    return 0 if ok == len(client.results) else 1 if ok else 2
