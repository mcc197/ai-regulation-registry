"""Filter requirements across instruments, and export the registry as JSON."""

from __future__ import annotations

import datetime as dt

from . import requirements as vocab
from .requirements import Requirement, crosswalk
from .schema import Instrument

# Instrument statuses under which it has legal or practical effect.
LIVE = {"published", "entry_into_force", "applies", "amended"}


def _matches_jurisdiction(inst: Instrument, wanted: list[str] | None) -> bool:
    if not wanted:
        return True
    want = {j.upper() for j in wanted}
    return inst.jurisdiction.upper() in want or inst.jurisdiction.split("-")[0].upper() in want


def _haystack(inst: Instrument, r: Requirement) -> str:
    parts = [inst.name, inst.title, inst.official_id or "", r.ref, r.title, r.scope or "",
             r.summary, r.assurance_note or "", r.note or "", *r.controls,
             r.category, *r.roles, *r.risks, *r.evidence, *r.assurance]
    return " ".join(parts).lower()


def applies_on(inst: Instrument, r: Requirement, day: dt.date) -> bool:
    """True when the instrument has effect on `day` and the requirement has started."""
    if inst.status_on(day) not in LIVE:
        return False
    return r.applies_from is None or r.applies_from <= day


def find(instruments: list[Instrument], *, role=None, category=None, risk=None,
         evidence=None, assurance=None, kind=None, jurisdiction=None, text=None,
         on: dt.date | None = None, binding: bool = False) -> list[tuple[Instrument, Requirement]]:
    """Requirements matching every filter given. List-valued filters match any value."""
    def any_of(wanted, values):
        return not wanted or bool(set(wanted) & set(values))

    terms = (text or "").lower().split()
    out = []
    for inst in instruments:
        if binding and not inst.binding:
            continue
        if not _matches_jurisdiction(inst, jurisdiction):
            continue
        for r in inst.requirements:
            if not (any_of(role, r.roles) and any_of(risk, r.risks)
                    and any_of(evidence, r.evidence) and any_of(assurance, r.assurance)
                    and any_of(category, [r.category]) and any_of(kind, [r.kind])):
                continue
            if on and not applies_on(inst, r, on):
                continue
            if terms:
                hay = _haystack(inst, r)
                if not all(t in hay for t in terms):
                    continue
            out.append((inst, r))
    return out


def _clean(s):
    return " ".join(s.split()) if s else None


def export(instruments: list[Instrument], today: dt.date) -> dict:
    """Everything the explorer page needs, as plain JSON-ready data."""
    links = crosswalk(instruments)
    return {
        "generated": today.isoformat(),
        "vocab": {
            "kinds": vocab.KINDS, "categories": vocab.CATEGORIES, "roles": vocab.ROLES,
            "risks": vocab.RISKS, "evidence": vocab.EVIDENCE, "assurance": vocab.ASSURANCE,
        },
        "instruments": [
            {
                "id": i.id, "name": i.name, "title": i.title, "type": i.type,
                "binding": i.binding, "jurisdiction": i.jurisdiction, "issuer": i.issuer,
                "official_id": i.official_id, "url": i.url, "summary": _clean(i.summary),
                "status": i.status_on(today), "topics": i.topics,
                "milestones": [
                    {"date": m["date"].isoformat(), "event": m["event"],
                     "scope": _clean(m.get("scope"))}
                    for m in sorted(i.milestones, key=lambda m: m["date"])
                ],
                "last_verified": i.last_verified.isoformat() if i.last_verified else None,
                "verified_against": i.verified_against,
            }
            for i in instruments
        ],
        "requirements": [
            {
                "key": r.key, "instrument": i.id, "ref": r.ref, "title": r.title,
                "kind": r.kind, "category": r.category, "roles": r.roles,
                "scope": _clean(r.scope), "risks": r.risks, "summary": _clean(r.summary),
                "controls": r.controls, "evidence": r.evidence, "assurance": r.assurance,
                "assurance_note": _clean(r.assurance_note),
                "applies_from": r.applies_from.isoformat() if r.applies_from else None,
                "links": sorted(links.get(r.key, ())), "source": r.source or i.url,
                "note": _clean(r.note),
                "verified_against": r.verified_against,
                "last_verified": r.last_verified.isoformat() if r.last_verified else None,
            }
            for i in instruments for r in i.requirements
        ],
    }
