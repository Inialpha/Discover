"""CLI commands for persona discovery: `discover segments` and `discover refdata`."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from .affordability import ReferenceDataMissing
from .engine import IntakeError, analyse
from .geography import MARKETS
from .intake import CATEGORIES, PURCHASE_TYPES, ProductIntake
from .refdata.records import CORE_INDICATORS
from .refdata.store import DEFAULT_CACHE, ReferenceStore, age_days


def add_parsers(sub: Any) -> None:
    s = sub.add_parser("segments", help="persona step 1: price/affordability + ranked candidate buyer segments (no Qloo, no LLM)")
    _intake_args(s)
    s.add_argument("--refresh", action="store_true", help="fetch live World Bank/FX data into the cache first")
    s.add_argument("--cache", default=str(DEFAULT_CACHE)); s.add_argument("--out", default="runs")
    s.add_argument("--no-zip", action="store_true")

    p = sub.add_parser("personas", help="full persona discovery: segments + Qloo evidence + persona cards")
    _intake_args(p)
    p.add_argument("--refresh", action="store_true"); p.add_argument("--cache", default=str(DEFAULT_CACHE))
    p.add_argument("--out", default="runs"); p.add_argument("--no-zip", action="store_true")
    p.add_argument("--kinds", default="brand,artist,tv_show,place", help="Qloo entity kinds per persona")
    p.add_argument("--take", type=int, default=8)
    p.add_argument("--no-llm", action="store_true"); p.add_argument("--mock", action="store_true", help="synthetic offline Qloo")
    p.add_argument("--dry-run", action="store_true", help="write planned Qloo requests, make no calls")
    p.add_argument("--max-calls", type=int, default=150); p.add_argument("--concurrency", type=int, default=2)
    p.add_argument("--delay", type=float, default=0.0, help="seconds between Qloo calls")
    p.add_argument("--no-discover", action="store_true", help="use only the competitors you list; do not look for more in Qloo")
    p.add_argument("--agent", action="store_true", help="let the LLM explore Qloo itself (tools, notebook, cited findings) to find competitors and audience")
    p.add_argument("--agent-steps", type=int, default=14, help="step budget of the exploring agent")
    p.add_argument("--llm-delay", type=float, default=0.0, help="seconds to wait between persona LLM calls (token-per-minute limits)")

    r = sub.add_parser("refdata", help="manage reference statistics (World Bank + exchange rates)")
    rs = r.add_subparsers(dest="refcmd", required=True)
    rr = rs.add_parser("refresh", help="fetch live data into the cache")
    rr.add_argument("--country", help="comma list of ISO3 codes (default: every supported market)")
    rr.add_argument("--cache", default=str(DEFAULT_CACHE))
    sh = rs.add_parser("show", help="show what is available (cache + shipped snapshot)")
    sh.add_argument("--country"); sh.add_argument("--cache", default=str(DEFAULT_CACHE))


def _intake_args(s: argparse.ArgumentParser) -> None:
    s.add_argument("--file", help="intake JSON file (other intake flags are ignored when given)")
    s.add_argument("--name"); s.add_argument("--description"); s.add_argument("--category", choices=sorted(CATEGORIES))
    s.add_argument("--price", type=float); s.add_argument("--currency", help="ISO code of the price you enter, e.g. NGN")
    s.add_argument("--location"); s.add_argument("--country", help="needed if the location is not a known city")
    s.add_argument("--purchase-type", choices=PURCHASE_TYPES, default="one_off")
    s.add_argument("--purchases-per-year", type=float)
    s.add_argument("--feature", action="append", default=[], help="repeatable product feature")
    s.add_argument("--product-type", help='plain words, e.g. "toothpaste"; used to find competitors in Qloo')
    s.add_argument("--competitor", action="append", default=[]); s.add_argument("--competitor-price", action="append", type=float, default=[])
    s.add_argument("--max-personas", type=int, default=6); s.add_argument("--gender", choices=["male", "female"])
    s.add_argument("--age", help="comma list of age buckets, e.g. 24_and_younger,25_to_29")


def _intake_from_args(a: argparse.Namespace) -> ProductIntake:
    if a.file:
        return ProductIntake.from_dict(json.loads(Path(a.file).read_text(encoding="utf-8")))
    return ProductIntake(
        name=a.name or "", description=a.description or "", category=a.category or "", price=a.price if a.price is not None else -1,
        currency=(a.currency or "").upper(), location=a.location or "", purchase_type=a.purchase_type,
        purchases_per_year=a.purchases_per_year, country=a.country, product_type=a.product_type or "", features=a.feature, competitors=a.competitor,
        competitor_prices=a.competitor_price, max_personas=a.max_personas, gender_focus=a.gender,
        age_focus=[x.strip() for x in a.age.split(",")] if a.age else [])


def markdown(res: dict[str, Any]) -> str:
    i, a, s = res["intake"], res["affordability"], res["segments"]
    L = [f"# Persona step 1: {i['name']}", "",
         f"**Market:** {a['country_name']} ({a['local_currency']}) · **Price:** {a['entered_price']:,.2f} {a['entered_currency']}"
         + (f" ≈ {a['local_price']:,.2f} {a['local_currency']}" if a["conversion"] else "")
         + f" · **Yearly cost:** {a['local_annual_cost']:,.2f} {a['local_currency']}", "",
         f"**Affordability tier:** `{a['tier']}` — yearly cost is {a['ratio']:.2%} of GNI per capita "
         f"({a['gni_per_capita_lcu']:,.0f} {a['local_currency']}, {a['gni_year']}). Profile `{a['profile']}`, "
         f"boundaries {a['boundaries']}. *(calculated)*", ""]
    if a["market_position"]:
        m = a["market_position"]
        L += [f"**Versus competitors:** {m['position']} (price is {m['price_vs_median']:.2f}× the median of {m['n']}).", ""]
    L += ["## Income bands (survey based, national)", "", "| Band | Income share % | Annual income | Cost / income | Reach |", "|---|---|---|---|---|"]
    for q in a["quintiles"]:
        inc = f"{q['annual_income_lcu']:,.0f}" if q["annual_income_lcu"] else "n/a"
        rt = f"{q['ratio']:.1%}" if q["ratio"] is not None else "n/a"
        sh = f"{q['income_share_pct']} ({q['share_year']})" if q["income_share_pct"] is not None else "n/a"
        L.append(f"| {q['quintile']} | {sh} | {inc} | {rt} | {q['reach']} |")
    L += ["", f"## Candidate segments (ranked by {s['ranked_by']}; ordering aid, not a share of buyers) *(rule-based)*", ""]
    for n, sc in enumerate(s["ranked"], 1):
        flag = (" (tied: no evidence separates it from others)" if sc.get("tied") else "") + (" (niche at this price)" if sc.get("niche") else "")
        L.append(f"{n}. **{sc['label']}** — score {sc['score']:.2f}, confidence {sc['confidence']}; ages {', '.join(sc['ages'])}{flag}")
        for r_ in sc["rationale"]:
            L.append(f"   - {r_}")
    if s["omitted_by_limit"]:
        L.append(f"\n({s['omitted_by_limit']} more segments omitted by max_personas)")
    if s["excluded"]:
        L += ["", "### Excluded", ""] + [f"- {e['label']}: {e['reason']}" for e in s["excluded"]]
    for n_ in s["notes"]:
        L.append(f"\n> {n_}")
    L += ["", "## Caveats", ""] + [f"- {c}" for c in a["caveats"]]
    L += ["", "## Sources", ""] + [f"- {x}" for x in res["attribution"]]
    L += [f"- {c['indicator']} {c['country']} {c['year'] or ''} = {c['value']:,} ({c['source']}, fetched {c['fetched_at']})"
          for c in a["inputs"]]
    return "\n".join(L) + "\n"


def run_segments(a: argparse.Namespace) -> int:
    store = ReferenceStore(cache_path=Path(a.cache))
    try:
        intake = _intake_from_args(a)
    except (OSError, ValueError, TypeError) as e:
        print(f"could not read intake: {e}")
        return 3
    errs = intake.validate()
    if errs:
        print("intake problems:")
        for e in errs:
            print(" -", e)
        return 3
    if a.refresh and intake.market:
        rep = store.refresh([intake.market.iso3], [intake.market.currency, intake.currency])
        print(f"refresh: {rep['fetched']} records, {len(rep['failed'])} failed, {len(rep['empty'])} empty")
        for f in rep["failed"]:
            print("  failed:", f["indicator"], f["error"])
    try:
        res = analyse(intake, store)
    except (IntakeError, ReferenceDataMissing) as e:
        print("cannot analyse:", e)
        return 3
    slug = re.sub(r"[^a-z0-9]+", "-", intake.name.lower()).strip("-")[:40] or "product"
    run = Path(a.out) / f"{datetime.now():%Y%m%d-%H%M%S}_segments_{slug}"
    run.mkdir(parents=True, exist_ok=True)
    (run / "00_input.json").write_text(json.dumps(intake.to_dict(), indent=2), encoding="utf-8")
    (run / "01_result.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    md = markdown(res)
    (run / "02_summary.md").write_text(md, encoding="utf-8")
    print(md[:3500])
    print(f"run folder : {run}")
    if not a.no_zip:
        z = shutil.make_archive(str(run), "zip", root_dir=run.parent, base_dir=run.name)
        print(f"send me    : {z}")
    return 0


def run_refdata(a: argparse.Namespace) -> int:
    store = ReferenceStore(cache_path=Path(a.cache))
    if a.refcmd == "refresh":
        codes = [c.strip().upper() for c in a.country.split(",")] if a.country else list(MARKETS)
        bad = [c for c in codes if c not in MARKETS]
        if bad:
            print("unsupported country codes:", ", ".join(bad), "| supported:", ", ".join(MARKETS))
            return 3
        rep = store.refresh(codes, [MARKETS[c].currency for c in codes])
        print(f"fetched {rep['fetched']} records into {store.cache_path}")
        for f in rep["failed"]:
            print("failed:", f["indicator"], f["error"])
        for e in rep["empty"]:
            print("no data:", e["indicator"], e["country"])
        return 0 if not rep["failed"] else 1
    codes = [a.country.upper()] if a.country else list(MARKETS)
    for c in codes:
        print(f"{c}  {MARKETS[c].name if c in MARKETS else ''}")
        for ind in CORE_INDICATORS:
            r = store.latest(c, ind)
            print(f"   {ind:<20} " + (f"{r.value:,.2f} ({r.year}, {r.source}, {age_days(r.fetched_at) or 0:.0f}d old)" if r else "missing"))
    rates = store.fx_rates()
    print("FX records:", ", ".join(f"{k}={v.value:g}" for k, v in sorted(rates.items())) or "none")
    return 0


def run_personas(a: argparse.Namespace) -> int:
    import asyncio
    from ...config import Settings
    from .runner import PersonaOptions, execute_personas
    try:
        intake = _intake_from_args(a)
    except (OSError, ValueError, TypeError) as e:
        print(f"could not read intake: {e}")
        return 3
    errs = intake.validate()
    if errs:
        print("intake problems:")
        for e in errs:
            print(" -", e)
        return 3
    opts = PersonaOptions(intake=intake, out=Path(a.out), kinds=[k.strip() for k in a.kinds.split(",") if k.strip()],
                          take=a.take, no_llm=a.no_llm, mock=a.mock, dry_run=a.dry_run, max_calls=a.max_calls,
                          concurrency=a.concurrency, delay=a.delay, llm_delay=a.llm_delay, zip=not a.no_zip, refresh=a.refresh, discover=not a.no_discover, agent=a.agent, agent_steps=a.agent_steps)
    code, run_dir, summary = asyncio.run(execute_personas(opts, Settings.from_env(), ReferenceStore(cache_path=Path(a.cache))))
    print(f"run folder : {run_dir}\nstatus     : {summary.get('status')}  (exit {code})")
    for e in summary.get("errors", []):
        print("error      :", e)
    if "qloo_calls" in summary:
        print(f"qloo calls : {summary['qloo_ok']}/{summary['qloo_calls']} ok · personas: {summary['persona_sources']}")
    for w in summary.get("warnings", []):
        print("warning    :", w)
    for f in summary.get("failures", [])[:8]:
        print(f"failed     : {f['label']} -> {f['error']}")
    if summary.get("zip"):
        print(f"send me    : {summary['zip']}")
    return code
