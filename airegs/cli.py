"""Command-line queries over the registry."""

from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import sys
from pathlib import Path

import json

from . import build as build_mod
from . import query
from . import requirements as vocab
from . import watch as watch_mod
from .schema import ValidationError, load

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "instruments"
DB_PATH = ROOT / "build" / "registry.db"
WATCH_STATE = ROOT / "state" / "watch.json"

LIVE = query.LIVE
EXPLORER_TEMPLATE = ROOT / "explorer" / "template.html"
EXPLORER_OUT = ROOT / "build" / "explorer.html"
APP_DIR = ROOT / "app"


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
    against = f" (against {i.verified_against} sources)" if i.verified_against else ""
    print(f"\nLast verified: {i.last_verified or 'never'}{against}")
    if i.review_notes:
        print(f"Review notes: {i.review_notes.strip()}")


def cmd_stale(instruments, args):
    cutoff = args.today - dt.timedelta(days=args.days)
    stale = [i for i in instruments if i.last_verified is None or i.last_verified < cutoff
             or (args.official and i.verified_against != "official")]

    def next_milestone(i):
        future = [m["date"] for m in i.milestones if m["date"] >= args.today]
        return min(future) if future else dt.date.max

    if args.requirements:
        pending = [r for i in instruments for r in i.requirements
                   if r.last_verified is None or r.last_verified < cutoff
                   or (args.official and r.verified_against != "official")]
        for r in pending:
            print(f"{r.key:40} verified {str(r.last_verified or 'never'):10} "
                  f"{('(' + r.verified_against + ')') if r.verified_against else ''}")
        print(f"{len(pending)} requirement(s) due for verification")
        return 3 if args.exit_code and pending else None
    if not stale:
        print(f"Everything verified since {cutoff}.")
    for i in sorted(stale, key=lambda i: (next_milestone(i), i.id)):
        nxt = next_milestone(i)
        nxt_s = f"next milestone {nxt}" if nxt != dt.date.max else "no upcoming milestone"
        against = f"({i.verified_against})" if i.verified_against else ""
        print(f"{i.id:32} verified {str(i.last_verified or 'never'):10} {against:12} {nxt_s}")
    return 3 if args.exit_code and stale else None


def _wrap(text, indent="      ", width=88):
    import textwrap
    return textwrap.fill(" ".join(text.split()), width, initial_indent=indent,
                         subsequent_indent=indent)


def cmd_obligations(instruments, args):
    hits = query.find(
        instruments, role=args.role, category=args.category, risk=args.risk,
        evidence=args.evidence, assurance=args.assurance, kind=args.kind,
        jurisdiction=args.jurisdiction, text=args.text, on=args.on, binding=args.binding)
    if args.json:
        data = query.export(instruments, args.today)
        keep = {r.key for _, r in hits}
        print(json.dumps([r for r in data["requirements"] if r["key"] in keep], indent=2))
        return
    if not hits:
        print("No requirements match.")
        return
    for inst, r in hits:
        when = f"from {r.applies_from}" if r.applies_from else ""
        print(f"{r.key}  [{inst.jurisdiction}] {inst.name} {r.ref}: {r.title}  {when}".rstrip())
        print(f"      {r.kind} · {vocab.CATEGORIES[r.category]} · roles: {', '.join(r.roles)}")
        if args.detail:
            if r.scope:
                print(_wrap(f"Scope: {r.scope}"))
            print(_wrap(r.summary))
            for c in r.controls:
                print(f"      - {c}")
            if r.evidence:
                print(f"      Evidence: {', '.join(vocab.EVIDENCE[e] for e in r.evidence)}")
            if r.assurance:
                print(f"      Assurance: {', '.join(vocab.ASSURANCE[a] for a in r.assurance)}")
            if r.assurance_note:
                print(_wrap(r.assurance_note))
            if r.note:
                print(_wrap(f"Note: {r.note}"))
            print()
    print(f"{len(hits)} requirement(s)")


def cmd_crosswalk(instruments, args):
    links = vocab.crosswalk(instruments)
    by_key = {r.key: (i, r) for i in instruments for r in i.requirements}
    if args.key not in by_key:
        sys.exit(f"No requirement {args.key!r}. Keys look like eu-ai-act#art-9.")
    inst, r = by_key[args.key]
    print(f"{inst.name} {r.ref}: {r.title}")
    linked = sorted(links.get(args.key, ()))
    if not linked:
        print("  No crosswalk links yet.")
    for k in linked:
        li, lr = by_key[k]
        print(f"  <-> {k:40} {li.name} {lr.ref}: {lr.title}")


def cmd_export(instruments, args):
    data = query.export(instruments, args.today)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    print(f"Wrote {out} ({len(data['instruments'])} instruments, "
          f"{len(data['requirements'])} requirements)")


APP_HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#1E5D57">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="AI Register">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" href="icon-192.png" type="image/png">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<style>
:root{color-scheme:light;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
body{margin:0}img{max-width:100%}[hidden]{display:none!important}
</style>
</head>
<body>
"""

APP_TAIL = """
<script>
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));
}
</script>
</body>
</html>
"""


def _app_document(fragment: str) -> str:
    """Wrap the page fragment as a standalone, installable document."""
    return APP_HEAD + fragment + APP_TAIL


def cmd_explorer(instruments, args):
    data = query.export(instruments, args.today)
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = EXPLORER_TEMPLATE.read_text().replace("/*REGISTRY_DATA*/null", blob, 1)
    if args.app:
        html = _app_document(html.replace('/*APP_MODE*/"artifact"', '"app"', 1))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    print(f"Wrote {out}")


def cmd_site(instruments, args):
    """Build the installable phone app into a folder ready for static hosting."""
    import hashlib
    import shutil
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    args.app = True
    args.out = str(out / "index.html")
    cmd_explorer(instruments, args)
    for f in APP_DIR.iterdir():
        if f.is_file():
            shutil.copy2(f, out / f.name)
    # A new cache name for every build, so installed apps pick up new data.
    build_id = hashlib.sha256((out / "index.html").read_bytes()).hexdigest()[:12]
    sw = out / "sw.js"
    sw.write_text(sw.read_text().replace("__BUILD_ID__", build_id))
    (out / ".nojekyll").write_text("")
    print(f"Built app in {out} (build {build_id})")


def cmd_watch(instruments, args):
    results = watch_mod.check(instruments, Path(args.state))
    for r in results:
        extra = f"  {r['error']}" if r.get("error") else ""
        print(f"{r['status']:9} {r['instrument']:28} {r['url']}{extra}")
        for sign, key in (("+", "added"), ("-", "removed")):
            for item in r.get(key, []):
                celex = item.rsplit(" ", 1)[1]
                print(f"          {sign} {item}  https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}")
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
    sp.add_argument("--official", action="store_true",
                    help="also list entries verified only against secondary sources")
    sp.add_argument("--requirements", action="store_true",
                    help="list requirements instead of instruments")
    sp.add_argument("--exit-code", action="store_true",
                    help="exit 3 if anything is due (for scheduled jobs)")
    sp.set_defaults(fn=cmd_stale)

    sp = sub.add_parser("obligations", help="filter requirements across instruments")
    sp.add_argument("text", nargs="?", help="words that must all appear")
    add_filters(sp)
    sp.add_argument("--role", action="append", choices=sorted(vocab.ROLES))
    sp.add_argument("--category", action="append", choices=sorted(vocab.CATEGORIES))
    sp.add_argument("--risk", action="append", choices=sorted(vocab.RISKS))
    sp.add_argument("--evidence", action="append", choices=sorted(vocab.EVIDENCE))
    sp.add_argument("--assurance", action="append", choices=sorted(vocab.ASSURANCE))
    sp.add_argument("--kind", action="append", choices=sorted(vocab.KINDS))
    sp.add_argument("--on", type=_date, help="only requirements that apply on this date")
    sp.add_argument("--detail", "-d", action="store_true", help="show summaries and controls")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--today", type=_date, default=today)
    sp.set_defaults(fn=cmd_obligations)

    sp = sub.add_parser("crosswalk", help="requirements linked to one requirement")
    sp.add_argument("key", help="e.g. eu-ai-act#art-9")
    sp.set_defaults(fn=cmd_crosswalk)

    sp = sub.add_parser("export", help="write the registry as JSON")
    sp.add_argument("--out", default=str(ROOT / "build" / "registry.json"))
    sp.add_argument("--today", type=_date, default=today)
    sp.set_defaults(fn=cmd_export)

    sp = sub.add_parser("explorer", help="build the explorer web page")
    sp.add_argument("--out", default=str(EXPLORER_OUT))
    sp.add_argument("--app", action="store_true",
                    help="build the standalone phone app page (no Ask tab) instead of the artifact")
    sp.add_argument("--today", type=_date, default=today)
    sp.set_defaults(fn=cmd_explorer)

    sp = sub.add_parser("site", help="build the installable phone app for static hosting")
    sp.add_argument("--out", default=str(ROOT / "build" / "site"))
    sp.add_argument("--today", type=_date, default=today)
    sp.set_defaults(fn=cmd_site)

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
