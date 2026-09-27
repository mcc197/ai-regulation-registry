"""Compile the YAML instruments into a SQLite database with full-text search."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .schema import Instrument

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
    review_notes TEXT,
    provisions_json TEXT
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
                "INSERT INTO instruments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (i.id, i.title, i.short_title, i.type, int(i.binding), i.jurisdiction,
                 i.issuer, i.official_id, i.url, i.summary.strip(),
                 i.last_verified.isoformat() if i.last_verified else None, i.verified_against,
                 i.review_notes, json.dumps(i.provisions, default=str) if i.provisions else None))
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
        con.commit()
    finally:
        con.close()
    tmp.replace(db_path)
    return db_path
