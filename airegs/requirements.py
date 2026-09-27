"""Requirements: what an instrument asks of whom, and how it is evidenced and assured.

Each instrument may list `requirements`. A requirement is one duty, prohibition,
right or recommended control, tagged with controlled vocabularies so it can be
filtered across instruments (every provider duty that needs third-party
assurance, every duty that produces logs, and so on).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

KINDS = {
    "obligation": "Binding duty",
    "prohibition": "Banned practice",
    "right": "Right of affected people",
    "recommendation": "Voluntary practice",
    "control": "Standard or framework control",
}

CATEGORIES = {
    "governance": "Governance and accountability",
    "risk-management": "Risk management",
    "impact-assessment": "Impact assessment",
    "data-governance": "Data governance",
    "technical-documentation": "Technical documentation",
    "record-keeping": "Record-keeping and logging",
    "transparency": "Transparency to users",
    "content-labelling": "Labelling AI-generated content",
    "human-oversight": "Human oversight",
    "accuracy-robustness-security": "Accuracy, robustness and security",
    "testing-evaluation": "Testing and evaluation",
    "quality-management": "Quality management system",
    "conformity-assessment": "Conformity assessment and certification",
    "registration": "Registration and filing",
    "post-market-monitoring": "Monitoring after deployment",
    "incident-reporting": "Incident reporting",
    "ai-literacy": "AI literacy and training",
    "prohibited-practice": "Prohibited practice",
    "copyright": "Copyright and training data",
    "third-party-management": "Suppliers and third parties",
    "individual-rights": "Rights of affected people",
    "whistleblowing": "Whistleblower protection",
    "representation": "Local representative",
}

ROLES = {
    "provider": "Provider (EU: puts an AI system on the market)",
    "deployer": "Deployer (uses an AI system professionally)",
    "importer": "Importer",
    "distributor": "Distributor",
    "gpai-provider": "Provider of a general-purpose AI model",
    "gpai-systemic-provider": "Provider of a general-purpose AI model with systemic risk",
    "developer": "Developer (US state laws)",
    "frontier-developer": "Frontier model developer",
    "large-frontier-developer": "Large frontier developer",
    "service-provider": "AI service provider or operator",
    "organisation": "Any organisation adopting the standard",
    "state": "State party or government",
    "affected-person": "Person affected by an AI decision",
}

RISKS = {
    "health-safety": "Health and safety",
    "fundamental-rights": "Fundamental rights",
    "discrimination": "Bias and discrimination",
    "privacy": "Privacy and personal data",
    "security": "Cybersecurity and misuse",
    "manipulation": "Manipulation and deception",
    "misinformation": "Misinformation and synthetic content",
    "catastrophic": "Catastrophic and systemic harm",
    "ip-copyright": "Intellectual property",
    "child-safety": "Child safety",
    "opacity": "Opacity and lack of explanation",
    "accountability": "Unclear accountability",
    "reliability": "Errors and unreliable output",
}

EVIDENCE = {
    "policy": "Policy or procedure",
    "risk-register": "Risk assessment and treatment records",
    "impact-assessment": "Impact assessment report",
    "technical-documentation": "Technical documentation file",
    "data-documentation": "Data sheets and data provenance records",
    "logs": "Automatically generated logs",
    "instructions-for-use": "Instructions for use",
    "test-reports": "Test, evaluation and red-team reports",
    "quality-manual": "Quality management system records",
    "conformity-declaration": "Declaration of conformity and marking",
    "certificate": "Certificate from an independent body",
    "registration-entry": "Registration or filing record",
    "monitoring-plan": "Post-deployment monitoring plan and records",
    "incident-report": "Incident reports",
    "transparency-report": "Public transparency report or framework",
    "user-notice": "Notice or disclosure to users",
    "content-marking": "Machine-readable marking of outputs",
    "training-records": "Training and competence records",
    "copyright-policy": "Copyright policy",
    "training-data-summary": "Public summary of training data",
    "audit-report": "Internal or external audit report",
    "management-review": "Management review records",
    "oversight-records": "Human oversight assignments and records",
}

ASSURANCE = {
    "none": "No assurance step specified",
    "self-assessment": "Self-assessment by the organisation",
    "internal-audit": "Internal audit",
    "third-party-assessment": "Independent third-party assessment",
    "certification": "Certification by an accredited body",
    "regulator-notification": "Notify or report to a regulator",
    "regulator-registration": "Register or file with a regulator",
    "regulator-review": "Regulator review, approval or inspection",
    "public-disclosure": "Public disclosure",
}

FIELDS = {
    "id", "ref", "title", "kind", "category", "roles", "scope", "risks", "summary",
    "controls", "evidence", "assurance", "assurance_note", "applies_from", "maps_to",
    "source", "last_verified", "verified_against", "note",
}
REQUIRED = ["id", "ref", "title", "kind", "category", "roles", "summary"]


@dataclass
class Requirement:
    id: str
    ref: str
    title: str
    kind: str
    category: str
    roles: list[str]
    summary: str
    instrument_id: str = ""
    scope: str | None = None
    risks: list[str] = field(default_factory=list)
    controls: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    assurance: list[str] = field(default_factory=list)
    assurance_note: str | None = None
    applies_from: dt.date | None = None
    maps_to: list[str] = field(default_factory=list)
    source: str | None = None
    last_verified: dt.date | None = None
    verified_against: str | None = None
    note: str | None = None

    @property
    def key(self) -> str:
        """Globally unique id: `<instrument>#<requirement>`."""
        return f"{self.instrument_id}#{self.id}"


def parse_requirements(raw_list, instrument_id: str, where: str, as_date, error) -> list[Requirement]:
    """Validate an instrument's `requirements` list. `as_date` and `error` come from schema.py."""
    reqs, seen = [], set()
    for i, raw in enumerate(raw_list or []):
        w = f"{where}: requirements[{i}]"
        if not isinstance(raw, dict):
            raise error(f"{w}: expected a mapping")
        w = f"{where}: requirement {raw.get('id', i)!r}"
        missing = [k for k in REQUIRED if raw.get(k) in (None, "", [])]
        if missing:
            raise error(f"{w}: missing {', '.join(missing)}")
        unknown = set(raw) - FIELDS
        if unknown:
            raise error(f"{w}: unknown fields {', '.join(sorted(unknown))}")
        if raw["id"] in seen:
            raise error(f"{w}: duplicate id")
        seen.add(raw["id"])

        def check(value, vocab, name, many=True):
            values = value if many else [value]
            if many and not isinstance(values, list):
                raise error(f"{w}: {name} must be a list")
            bad = [v for v in values if v not in vocab]
            if bad:
                raise error(f"{w}: unknown {name} {bad}; choose from {sorted(vocab)}")

        check(raw["kind"], KINDS, "kind", many=False)
        check(raw["category"], CATEGORIES, "category", many=False)
        check(raw["roles"], ROLES, "roles")
        check(raw.get("risks") or [], RISKS, "risks")
        check(raw.get("evidence") or [], EVIDENCE, "evidence")
        check(raw.get("assurance") or [], ASSURANCE, "assurance")
        if raw.get("source") and not str(raw["source"]).startswith("https://"):
            raise error(f"{w}: source needs an https url")

        fields = {k: raw.get(k) for k in FIELDS if raw.get(k) is not None}
        for key in ("risks", "controls", "evidence", "assurance", "maps_to"):
            fields[key] = list(raw.get(key) or [])
        if raw.get("applies_from") is not None:
            fields["applies_from"] = as_date(raw["applies_from"], f"{w}: applies_from")
        if raw.get("last_verified") is not None:
            fields["last_verified"] = as_date(raw["last_verified"], f"{w}: last_verified")
            if raw.get("verified_against") not in {"official", "secondary"}:
                raise error(f"{w}: last_verified needs verified_against: official or secondary")
        elif raw.get("verified_against") is not None:
            raise error(f"{w}: verified_against needs last_verified")
        reqs.append(Requirement(instrument_id=instrument_id, **fields))
    return reqs


def check_crosswalk(instruments, error) -> None:
    """Every maps_to target must be an existing `<instrument>#<requirement>`."""
    keys = {r.key for inst in instruments for r in inst.requirements}
    for inst in instruments:
        for r in inst.requirements:
            for target in r.maps_to:
                if target not in keys:
                    raise error(f"{r.key}: maps_to target {target!r} does not exist")
                if target == r.key:
                    raise error(f"{r.key}: maps_to itself")


def crosswalk(instruments) -> dict[str, set[str]]:
    """Undirected links between requirements, from every maps_to in either direction."""
    links: dict[str, set[str]] = {}
    for inst in instruments:
        for r in inst.requirements:
            for target in r.maps_to:
                links.setdefault(r.key, set()).add(target)
                links.setdefault(target, set()).add(r.key)
    return links
