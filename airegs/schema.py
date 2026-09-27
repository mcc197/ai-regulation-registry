"""Load and validate instrument YAML files, and derive status from milestones."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

import yaml

TYPES = {
    "legislation", "regulation", "treaty", "executive_order",
    "standard", "framework", "code_of_practice", "guidance",
}

# Lifecycle events, in the order they normally happen. Status on a date is the
# latest of these on or before that date.
EVENTS = [
    "proposed", "adopted", "signed", "published", "entry_into_force",
    "applies", "amended", "repealed", "superseded", "withdrawn",
]
ENDING_EVENTS = {"repealed", "superseded", "withdrawn"}

RELATION_TYPES = {
    "amends": "amended_by",
    "amended_by": "amends",
    "supersedes": "superseded_by",
    "superseded_by": "supersedes",
    "implements": "implemented_by",
    "implemented_by": "implements",
    "supports": "supported_by",
    "supported_by": "supports",
    "references": "referenced_by",
    "referenced_by": "references",
}

TOPICS = {
    "risk-based", "high-risk", "prohibited-practices", "gpai", "frontier-models",
    "generative-ai", "transparency", "content-labelling", "algorithmic-discrimination",
    "automated-decisions", "consumer-protection", "employment", "governance",
    "management-system", "risk-management", "human-rights", "safety-incidents",
    "ai-literacy", "innovation", "public-sector",
}

SOURCE_KINDS = {"official", "secondary"}

REQUIRED = ["id", "title", "type", "binding", "jurisdiction", "issuer", "summary",
            "milestones", "sources"]


class ValidationError(Exception):
    pass


@dataclass
class Instrument:
    id: str
    title: str
    type: str
    binding: bool
    jurisdiction: str
    issuer: str
    summary: str
    milestones: list[dict]
    sources: list[dict]
    short_title: str | None = None
    official_id: str | None = None
    url: str | None = None
    topics: list[str] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)
    provisions: list[dict] = field(default_factory=list)
    last_verified: dt.date | None = None
    review_notes: str | None = None

    @property
    def name(self) -> str:
        return self.short_title or self.title

    def status_on(self, day: dt.date) -> str:
        """Latest lifecycle event on or before `day`, or 'not_yet_proposed'."""
        past = [m for m in self.milestones if m["date"] <= day]
        # Once an instrument has ended, later "applies" dates are moot.
        ended = [m for m in past if m["event"] in ENDING_EVENTS]
        candidates = ended or past
        if not candidates:
            return "not_yet_proposed"
        # Same-day ties go to the later lifecycle stage.
        return max(candidates, key=lambda m: (m["date"], EVENTS.index(m["event"])))["event"]

    def ended_by(self, day: dt.date) -> bool:
        return any(m["event"] in ENDING_EVENTS and m["date"] <= day for m in self.milestones)


def _as_date(value, where: str) -> dt.date:
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        raise ValidationError(f"{where}: {value!r} is not a YYYY-MM-DD date") from None


def parse(raw: dict, where: str) -> Instrument:
    if not isinstance(raw, dict):
        raise ValidationError(f"{where}: expected a mapping")
    missing = [k for k in REQUIRED if raw.get(k) in (None, "", [])]
    if missing:
        raise ValidationError(f"{where}: missing {', '.join(missing)}")
    unknown = set(raw) - set(Instrument.__dataclass_fields__)
    if unknown:
        raise ValidationError(f"{where}: unknown fields {', '.join(sorted(unknown))}")
    if raw["type"] not in TYPES:
        raise ValidationError(f"{where}: type {raw['type']!r} not in {sorted(TYPES)}")
    if not isinstance(raw["binding"], bool):
        raise ValidationError(f"{where}: binding must be true or false")
    bad_topics = set(raw.get("topics") or []) - TOPICS
    if bad_topics:
        raise ValidationError(f"{where}: unknown topics {sorted(bad_topics)}")

    milestones = []
    for i, m in enumerate(raw["milestones"]):
        mw = f"{where}: milestones[{i}]"
        if m.get("event") not in EVENTS:
            raise ValidationError(f"{mw}: event {m.get('event')!r} not in {EVENTS}")
        milestones.append({**m, "date": _as_date(m.get("date"), mw)})

    for i, s in enumerate(raw["sources"]):
        if not str(s.get("url", "")).startswith("https://"):
            raise ValidationError(f"{where}: sources[{i}] needs an https url")
        if s.get("kind") not in SOURCE_KINDS:
            raise ValidationError(f"{where}: sources[{i}].kind must be one of {sorted(SOURCE_KINDS)}")

    for i, r in enumerate(raw.get("relations") or []):
        if r.get("type") not in RELATION_TYPES:
            raise ValidationError(f"{where}: relations[{i}].type {r.get('type')!r} not in {sorted(RELATION_TYPES)}")

    fields = {**raw, "milestones": milestones}
    if raw.get("last_verified") is not None:
        fields["last_verified"] = _as_date(raw["last_verified"], f"{where}: last_verified")
    for key in ("topics", "relations", "provisions"):
        fields[key] = raw.get(key) or []
    return Instrument(**fields)


def load(data_dir: Path) -> list[Instrument]:
    """Load every instrument and check cross-file rules. Raises ValidationError."""
    instruments = []
    for path in sorted(Path(data_dir).glob("*.yaml")):
        with open(path, encoding="utf-8") as f:
            inst = parse(yaml.safe_load(f), path.name)
        if inst.id != path.stem:
            raise ValidationError(f"{path.name}: id {inst.id!r} must match the file name")
        instruments.append(inst)

    by_id = {i.id: i for i in instruments}
    for inst in instruments:
        for r in inst.relations:
            target = by_id.get(r["target"])
            if target is None:
                raise ValidationError(f"{inst.id}: relation target {r['target']!r} does not exist")
            inverse = RELATION_TYPES[r["type"]]
            if not any(t["type"] == inverse and t["target"] == inst.id for t in target.relations):
                raise ValidationError(
                    f"{inst.id}: {r['type']} {target.id}, but {target.id} lacks {inverse} {inst.id}")
    return instruments
