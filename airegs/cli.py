"""Command-line queries over the registry."""

from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import sys
from pathlib import Path

from . import build as build_mod
from . import watch as watch_mod
from .schema import ValidationError, load

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "instruments"
DB_PATH = ROOT / "build" / "registry.db"
WATCH_STATE = ROOT / "state" / "watch.json"

# Statuses under which an instrument has legal or practical effect.
LIVE = {"published", "entry_into_force", "applies", "amended"}


def _date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def _filter(instruments, args):
    if getattr(args, "jurisdiction", None):
        want = {j.upper() for j in args.jurisdiction}
        instruments = [i for i in instruments
                       if i.jurisdiction.upper() in want
                       or i.jurisdiction.split("-")[0].upper() in want]
    if getattr(args, "binding", False):
        instruments = [i for i in instruments if i.binding]
    if getattr(args, "topic", None):
        instruments = [i for i in instruments if args.topic in i.topics]
    return instruments


def cmd_validate(instruments, args):
    print(f"OK: {len(instruments)} instruments")


def cmd_build(instruments, args):
    path = build_mod.build(instruments, Path(args.db))
    print(f"Built {path} ({len(instruments)} instruments)")


def cmd_applies_on(instruments, args):
    day = args.date
    for i in sorted(_filter(instruments, args), key=lambda i: (i.jurisdiction, i.name)):
        status = i.status_on(day)
        if status not in LIVE:
            continue
        print(f"{i.jurisdiction:6} {i.name}  [{status.replace('_', ' ')}]")
        for m in sorted(i.milestones, key=lambda m: m["date"]):
            if m["event"] == "applies" and m["date"] <= day and m.get("scope"):
                print(f"         since {m['date']}: {m['scope']}")


def cmd_upcoming(instruments, args):
    start = args.start
    end = start + dt.timedelta(days=args.days)
    rows = [(m["date"], i, m) for i in _filter(instruments, args) for m in i.milestones
            if start <= m["date"] <= end]
    if not rows:
        print(f"Nothing between {start} and {end}.")
    for day, i, m in sorted(rows, key=lambda r: (r[0], r[1].name)):
        scope = f": {m['scope']}" if m.get("scope") else ""
        print(f"{day}  {i.jurisdiction:6} {i.name}  {m['event'].replace('_', ' ')}{scope}")


def cmd_search(instruments, args):
    db = build_mod.build(instruments, Path(args.db))
    con = sqlite3.connect(db)
    try:
        rows = con.execute(
            "SELECT i.instrument_id, i.jurisdiction, coalesce(i.short_title, i.title), "
            "snippet(instruments_fts, 4, '[', ']', '...', 12) "
            "FROM instruments_fts f JOIN instruments i USING (instrument_id) "
            "WHERE instruments_fts MATCH ? ORDER BY rank", (args.query,)).fetchall()
    except sqlite3.OperationalError as e:
        sys.exit(f"Bad search query: {e}")
    finally:
        con.close()
    if not rows:
        print("No matches.")
    for iid, jur, name, snip in rows:
        print(f"{jur:6} {name} ({iid})\n       {snip}")


def cmd_show(instruments, args):
    by_id = {i.id: i for i in instruments}
    i = by_id.get(args.id)
    if i is None:
        sys.exit(f"No instrument {args.id!r}. Try: {', '.join(sorted(by_id))}")
    today = args.today
    print(f"{i.title}" + (f" ({i.official_id})" if i.official_id else ""))
    print(f"{i.jurisdiction} · {i.type.replace('_', ' ')} · {'binding' if i.binding else 'voluntary'}"
          f" · {i.issuer}")
    print(f"Status on {today}: {i.status_on(today).replace('_', ' ')}")
    print(f"\n{i.summary.strip()}\n")
    print("Timeline:")
    for m in sorted(i.milestones, key=lambda m: (m["date"], m["event"])):
        mark = " " if m["date"] <= today else ">"
        scope = f": {m['scope']}" if m.get("scope") else ""
        print(f" {mark} {m['date']}  {m['event'].replace('_', ' ')}{scope}")
        if m.get("note"):
            print(f"               ({m['note']})")
    if i.relations:
        print("\nRelated:")
        for r in i.relations:
            print(f"   {r['type'].replace('_', ' ')} {by_id[r['target']].name} ({r['target']})")
    print("\nSources:")
    for s in i.sources:
        print(f"   [{s['kind']}] {s.get('label') or ''} {s['url']}")
    print(f"\nLast verified: {i.last_verified or 'never'}")
    if i.review_notes:
        print(f"Review notes: {i.review_notes.strip()}")


def cmd_stale(instruments, args):
    cutoff = args.today - dt.timedelta(days=args.days)
    stale = [i for i in instruments if i.last_verified is None or i.last_verified < cutoff]

    def next_milestone(i):
        future = [m["date"] for m in i.milestones if m["date"] >= args.today]
        return min(future) if future else dt.date.max

    if not stale:
        print(f"Everything verified since {cutoff}.")
    for i in sorted(stale, key=lambda i: (next_milestone(i), i.id)):
        nxt = next_milestone(i)
        nxt_s = f"next milestone {nxt}" if nxt != dt.date.max else "no upcoming milestone"
        print(f"{i.id:32} verified {i.last_verified or 'never':10}  {nxt_s}")


def cmd_watch(instruments, args):
    results = watch_mod.check(instruments, Path(args.state))
    for r in results:
        extra = f"  {r['error']}" if r.get("error") else ""
        print(f"{r['status']:9} {r['instrument']:28} {r['url']}{extra}")
    if any(r["status"] == "changed" for r in results):
        return 3  # lets a scheduled job open an issue only when something moved


def main(argv=None) -> int:
    today = dt.date.today()
    p = argparse.ArgumentParser(prog="airegs", description="Query the AI regulation registry.")
    p.add_argument("--data", default=str(DATA_DIR), help="directory of instrument YAML files")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_filters(sp):
        sp.add_argument("-j", "--jurisdiction", action="append",
                        help="e.g. EU, US, US-CO (repeatable; US matches every US-xx state)")
        sp.add_argument("--binding", action="store_true", help="binding instruments only")
        sp.add_argument("-t", "--topic")

    sub.add_parser("validate", help="check every YAML file").set_defaults(fn=cmd_validate)

    sp = sub.add_parser("build", help="compile to SQLite")
    sp.add_argument("--db", default=str(DB_PATH))
    sp.set_defaults(fn=cmd_build)

    sp = sub.add_parser("applies-on", help="what has effect on a date")
    sp.add_argument("date", nargs="?", type=_date, default=today)
    add_filters(sp)
    sp.set_defaults(fn=cmd_applies_on)

    sp = sub.add_parser("upcoming", help="milestones in the next N days")
    sp.add_argument("--days", type=int, default=180)
    sp.add_argument("--from", dest="start", type=_date, default=today)
    add_filters(sp)
    sp.set_defaults(fn=cmd_upcoming)

    sp = sub.add_parser("search", help="full-text search (SQLite FTS5 syntax)")
    sp.add_argument("query")
    sp.add_argument("--db", default=str(DB_PATH))
    sp.set_defaults(fn=cmd_search)

    sp = sub.add_parser("show", help="one instrument in full")
    sp.add_argument("id")
    sp.add_argument("--today", type=_date, default=today)
    sp.set_defaults(fn=cmd_show)

    sp = sub.add_parser("stale", help="entries due for re-verification")
    sp.add_argument("--days", type=int, default=90)
    sp.add_argument("--today", type=_date, default=today)
    sp.set_defaults(fn=cmd_stale)

    sp = sub.add_parser("watch", help="check watched sources for changes (exit 3 if any changed)")
    sp.add_argument("--state", default=str(WATCH_STATE))
    sp.set_defaults(fn=cmd_watch)

    args = p.parse_args(argv)
    try:
        instruments = load(Path(args.data))
    except ValidationError as e:
        print(f"Invalid registry data: {e}", file=sys.stderr)
        return 2
    return args.fn(instruments, args) or 0


if __name__ == "__main__":
    sys.exit(main())
