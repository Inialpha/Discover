"""discover CLI.

  discover run "what do women 25-35 in Lagos like? what media?" [options]
  discover probe            # tiny connectivity/auth check against Qloo
Exit codes: 0 ok · 1 partial failures · 2 all Qloo calls failed · 3 config/auth problem
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .config import Settings, load_dotenv
from .runner import RunOptions, execute


def _split(v: str | None) -> list[str] | None:
    return [x.strip() for x in v.split(",") if x.strip()] if v else None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="discover", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run the business workflow end to end")
    r.add_argument("question")
    r.add_argument("--product"); r.add_argument("--own-brand"); r.add_argument("--location")
    r.add_argument("--keyword", action="append", default=[], help="repeatable theme/interest phrase")
    r.add_argument("--brand", action="append", default=[], help="competitor/reference brand, repeatable")
    r.add_argument("--interest", action="append", default=[], help='"name:kind", e.g. "Burna Boy:artist"')
    r.add_argument("--segment", action="append", default=[], help='"label:gender:age", e.g. "Young women:female:25-35"')
    r.add_argument("--gender"); r.add_argument("--age", help='e.g. "25-35"')
    r.add_argument("--domains", help="comma list of entity kinds")
    r.add_argument("--take", type=int, default=10)
    r.add_argument("--steps", help="comma list: resolve,taste,affinity,demographics,heatmap,compare")
    r.add_argument("--skip", help="comma list of steps to skip")
    r.add_argument("--no-llm", action="store_true"); r.add_argument("--mock", action="store_true", help="synthetic offline Qloo")
    r.add_argument("--dry-run", action="store_true", help="write planned requests, make no Qloo calls")
    r.add_argument("--plan-only", action="store_true")
    r.add_argument("--out", default="runs"); r.add_argument("--max-calls", type=int, default=80)
    r.add_argument("--concurrency", type=int, default=2); r.add_argument("--delay", type=float, default=0.0)
    r.add_argument("--no-zip", action="store_true")
    r.add_argument("--location-mode", choices=["auto", "signal", "filter", "both"], default="auto",
                   help="how the location is sent to Qloo (experiment: filter may localise movies/artists better)")
    sub.add_parser("probe", help="check key/base URL with two tiny calls")
    return p


async def _probe(settings: Settings) -> int:
    from .qloo import calls
    from .qloo.client import QlooClient
    from .recorder import RunRecorder
    rec = RunRecorder(Path("runs") / "probe")
    if not settings.qloo_api_key:
        print("QLOO_API_KEY missing"); return 3
    async with QlooClient(settings, rec, max_calls=12) as c:
        a = await c.call(calls.search_entities("probe-search", "Nike", "brand", take=2, step="probe"))
        b = await c.call(calls.insights_entities("probe", "probe-insights", "movie", calls.Signals(), take=2, explain=False))
    for r in (a, b):
        print(f"{r.spec.label}: ok={r.ok} status={r.status} variant={r.variant_index} -> {r.file}")
    return 0 if a.ok and b.ok else 3 if c.auth_failed else 2


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    settings = Settings.from_env()
    if args.cmd == "probe":
        return asyncio.run(_probe(settings))
    opts = RunOptions(
        question=args.question, out=Path(args.out), product=args.product, own_brand=args.own_brand,
        keywords=args.keyword, competitors=args.brand, interests=args.interest, location=args.location,
        segments=args.segment, gender=args.gender, age=args.age, domains=_split(args.domains), take=args.take,
        steps=_split(args.steps), skip=_split(args.skip) or [], no_llm=args.no_llm, mock=args.mock,
        dry_run=args.dry_run, plan_only=args.plan_only, max_calls=args.max_calls,
        concurrency=args.concurrency, delay=args.delay, zip=not args.no_zip, location_mode=args.location_mode)
    code, run_dir, summary = asyncio.run(execute(opts, settings))
    print(f"run folder : {run_dir}")
    print(f"status     : {summary.get('status')}  (exit {code})")
    if "qloo_calls" in summary:
        print(f"qloo calls : {summary['qloo_ok']}/{summary['qloo_calls']} ok, {summary['http_requests']} http requests")
    for w in summary.get("warnings", []):
        print("warning    :", w)
    for f in summary.get("failures", [])[:8]:
        print(f"failed     : {f['label']} -> {f['error']}")
    if summary.get("zip"):
        print(f"send me    : {summary['zip']}")
    return code


if __name__ == "__main__":
    sys.exit(main())
