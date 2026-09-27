"""Compile the YAML instruments into a SQLite database with full-text search."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .requirements import crosswalk
from .schema import Instrument


def _text(s):
    return " ".join(s.split()) if s else None


def _iso(d):
    return d.isoformat() if d else None

SCHEMA = """
CREATE TABLE instruments (
    instrument_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    short_title TEXT,
    type TEXT NOT NULL,
    binding INTEGER NOT NULL,
    jurisdiction TEXT NOT NULL,
    issuer TEXT NOT NULL,
    official_id TEXT,
    url TEXT,
    summary TEXT NOT NULL,
    last_verified TEXT,
    verified_against TEXT,
    review_notes TEXT
);
CREATE TABLE milestones (
    instrument_id TEXT NOT NULL REFERENCES instruments,
    date TEXT NOT NULL,
    event TEXT NOT NULL,
    scope TEXT,
    note TEXT
);
CREATE INDEX milestones_date ON milestones(date);
CREATE TABLE relations (
    instrument_id TEXT NOT NULL REFERENCES instruments,
    type TEXT NOT NULL,
    target_id TEXT NOT NULL REFERENCES instruments
);
CREATE TABLE sources (
    instrument_id TEXT NOT NULL REFERENCES instruments,
    url TEXT NOT NULL,
    label TEXT,
    kind TEXT NOT NULL,
    watch INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE topics (
    instrument_id TEXT NOT NULL REFERENCES instruments,
    topic TEXT NOT NULL
);
CREATE TABLE requirements (
    requirement_id TEXT PRIMARY KEY,           -- <instrument>#<id>
    instrument_id TEXT NOT NULL REFERENCES instruments,
    ref TEXT NOT NULL,
    title TEXT NOT NULL,
    kind TEXT NOT NULL,
    category TEXT NOT NULL,
    scope TEXT,
    summary TEXT NOT NULL,
    controls TEXT,                             -- one per line
    assurance_note TEXT,
    applies_from TEXT,
    source TEXT,
    last_verified TEXT,
    verified_against TEXT,
    note TEXT
);
-- Facet values: role, risk, evidence and assurance tags, one row each.
CREATE TABLE requirement_tags (
    requirement_id TEXT NOT NULL REFERENCES requirements,
    facet TEXT NOT NULL,
    value TEXT NOT NULL
);
CREATE INDEX requirement_tags_facet ON requirement_tags(facet, value);
-- Crosswalk, stored in both directions.
CREATE TABLE requirement_links (
    requirement_id TEXT NOT NULL REFERENCES requirements,
    linked_id TEXT NOT NULL REFERENCES requirements
);
CREATE VIRTUAL TABLE requirements_fts USING fts5(
    requirement_id UNINDEXED, ref, title, scope, summary, controls
);
CREATE VIRTUAL TABLE instruments_fts USING fts5(
    instrument_id UNINDEXED, title, short_title, official_id, summary, scopes
);
"""


def build(instruments: list[Instrument], db_path: Path) -> Path:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = db_path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    try:
        con.executescript(SCHEMA)
        for i in instruments:
            con.execute(
                "INSERT INTO instruments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (i.id, i.title, i.short_title, i.type, int(i.binding), i.jurisdiction,
                 i.issuer, i.official_id, i.url, i.summary.strip(),
                 i.last_verified.isoformat() if i.last_verified else None, i.verified_against,
                 i.review_notes))
            con.executemany(
                "INSERT INTO milestones VALUES (?,?,?,?,?)",
                [(i.id, m["date"].isoformat(), m["event"], m.get("scope"), m.get("note"))
                 for m in i.milestones])
            con.executemany("INSERT INTO relations VALUES (?,?,?)",
                            [(i.id, r["type"], r["target"]) for r in i.relations])
            con.executemany(
                "INSERT INTO sources VALUES (?,?,?,?,?)",
                [(i.id, s["url"], s.get("label"), s["kind"], int(bool(s.get("watch"))))
                 for s in i.sources])
            con.executemany("INSERT INTO topics VALUES (?,?)", [(i.id, t) for t in i.topics])
            scopes = " ".join(m.get("scope") or "" for m in i.milestones)
            con.execute("INSERT INTO instruments_fts VALUES (?,?,?,?,?,?)",
                        (i.id, i.title, i.short_title, i.official_id, i.summary, scopes))
            for r in i.requirements:
                con.execute(
                    "INSERT INTO requirements VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (r.key, i.id, r.ref, r.title, r.kind, r.category, _text(r.scope),
                     _text(r.summary), "\n".join(r.controls) or None, _text(r.assurance_note),
                     _iso(r.applies_from), r.source, _iso(r.last_verified),
                     r.verified_against, r.note))
                con.executemany(
                    "INSERT INTO requirement_tags VALUES (?,?,?)",
                    [(r.key, facet, v) for facet in ("roles", "risks", "evidence", "assurance")
                     for v in getattr(r, facet)])
                con.execute("INSERT INTO requirements_fts VALUES (?,?,?,?,?,?)",
                            (r.key, r.ref, r.title, _text(r.scope), _text(r.summary),
                             " ".join(r.controls)))
        links = crosswalk(instruments)
        con.executemany("INSERT INTO requirement_links VALUES (?,?)",
                        [(a, b) for a, bs in sorted(links.items()) for b in sorted(bs)])
        con.commit()
    finally:
        con.close()
    tmp.replace(db_path)
    return db_path
