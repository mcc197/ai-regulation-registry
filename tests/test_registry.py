import datetime as dt
import sqlite3
from pathlib import Path

import pytest
import yaml

from airegs import build, cli, watch
from airegs.schema import ValidationError, load, parse

DATA = Path(__file__).resolve().parent.parent / "data" / "instruments"
D = dt.date


@pytest.fixture(scope="module")
def registry():
    return {i.id: i for i in load(DATA)}


def minimal(**over):
    raw = {
        "id": "x", "title": "X", "type": "legislation", "binding": True,
        "jurisdiction": "EU", "issuer": "Someone", "summary": "S.",
        "milestones": [{"date": "2025-01-01", "event": "adopted"}],
        "sources": [{"url": "https://example.org", "kind": "official"}],
    }
    raw.update(over)
    return raw


def test_seed_data_is_valid(registry):
    assert len(registry) >= 12


def test_every_instrument_has_an_official_source(registry):
    for i in registry.values():
        assert any(s["kind"] == "official" for s in i.sources), i.id


@pytest.mark.parametrize("over, msg", [
    ({"sources": []}, "missing sources"),
    ({"type": "vibes"}, "type"),
    ({"topics": ["made-up"]}, "unknown topics"),
    ({"milestones": [{"date": "2025-13-01", "event": "adopted"}]}, "not a YYYY-MM-DD"),
    ({"milestones": [{"date": "2025-01-01", "event": "rumoured"}]}, "event"),
    ({"sources": [{"url": "http://example.org", "kind": "official"}]}, "https"),
    ({"colour": "red"}, "unknown fields"),
])
def test_validation_rejects_bad_entries(over, msg):
    with pytest.raises(ValidationError, match=msg):
        parse(minimal(**over), "x.yaml")


def test_one_sided_relation_is_rejected(tmp_path):
    a = minimal(id="a", relations=[{"type": "amends", "target": "b"}])
    b = minimal(id="b")
    for raw in (a, b):
        (tmp_path / f"{raw['id']}.yaml").write_text(yaml.safe_dump(raw))
    with pytest.raises(ValidationError, match="lacks amended_by a"):
        load(tmp_path)


def test_status_follows_the_timeline(registry):
    act = registry["eu-ai-act"]
    assert act.status_on(D(2024, 7, 1)) == "signed"
    assert act.status_on(D(2024, 9, 1)) == "entry_into_force"
    assert act.status_on(D(2025, 3, 1)) == "applies"
    assert act.status_on(D(2021, 1, 1)) == "not_yet_proposed"


def test_superseded_instrument_stays_superseded(registry):
    old = registry["us-co-sb24-205"]
    assert old.status_on(D(2026, 1, 1)) == "amended"
    assert old.status_on(D(2030, 1, 1)) == "superseded"


def test_same_day_tie_goes_to_later_stage(registry):
    assert registry["us-co-sb26-189"].status_on(D(2026, 5, 14)) == "entry_into_force"


def test_applies_on_filters_by_state_prefix(capsys):
    cli.main(["applies-on", "2027-01-01", "-j", "US", "--binding"])
    out = capsys.readouterr().out
    assert "SB 26-189" in out and "SB 53" in out
    assert "SB 24-205" not in out  # superseded
    assert "NIST" not in out  # not binding


def test_upcoming_shows_deferred_high_risk_date(capsys):
    cli.main(["upcoming", "--from", "2027-06-01", "--days", "365", "-j", "EU"])
    out = capsys.readouterr().out
    assert "2027-12-02" in out and "Annex III" in out


def test_build_and_full_text_search(registry, tmp_path):
    db = build.build(list(registry.values()), tmp_path / "r.db")
    con = sqlite3.connect(db)
    hits = [r[0] for r in con.execute(
        "SELECT instrument_id FROM instruments_fts WHERE instruments_fts MATCH 'frontier'")]
    assert "us-ca-sb53" in hits
    assert con.execute("SELECT count(*) FROM milestones").fetchone()[0] > 20


def test_watch_reports_new_then_changed(registry, tmp_path):
    insts = [registry["nist-ai-rmf"]]
    state = tmp_path / "watch.json"
    pages = iter(["<p>v1</p>", "<p>v1</p><script>x()</script>", "<p>v2</p>"])
    fetch = lambda url: next(pages)
    assert [r["status"] for r in watch.check(insts, state, fetch)] == ["new"]
    assert [r["status"] for r in watch.check(insts, state, fetch)] == ["unchanged"]
    assert [r["status"] for r in watch.check(insts, state, fetch)] == ["changed"]


def test_watch_records_fetch_errors(registry, tmp_path):
    def boom(url):
        raise OSError("offline")
    (r,) = watch.check([registry["nist-ai-rmf"]], tmp_path / "w.json", boom)
    assert r["status"] == "error" and "offline" in r["error"]
