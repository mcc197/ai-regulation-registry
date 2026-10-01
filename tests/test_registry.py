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


def test_watch_treats_blank_pages_as_errors(registry, tmp_path):
    # EUR-Lex serves scripts an empty bot challenge; hashing it would hide real changes.
    (r,) = watch.check([registry["nist-ai-rmf"]], tmp_path / "w.json", lambda url: "<script>x</script>")
    assert r["status"] == "error" and "no visible text" in r["error"]


def test_watch_lists_added_and_removed_items(registry, tmp_path):
    insts, state = [registry["nist-ai-rmf"]], tmp_path / "w.json"
    feeds = iter([["corrigendum A", "amended by B"], ["amended by B", "amended by B"],
                  ["amended by B", "amended by C"]])
    fetch = lambda url: next(feeds)
    assert [r["status"] for r in watch.check(insts, state, fetch)] == ["new"]
    assert [r["status"] for r in watch.check(insts, state, fetch)] == ["changed"]
    (r,) = watch.check(insts, state, fetch)
    assert r["status"] == "changed" and r["added"] == ["amended by C"] and r["removed"] == []


def test_watch_sends_eurlex_links_to_cellar(monkeypatch):
    seen = []
    monkeypatch.setattr(watch, "eu_relations", lambda eli, timeout: seen.append(eli) or ["x"])
    assert watch.fetch("https://eur-lex.europa.eu/eli/reg/2024/1689/oj") == ["x"]
    assert seen == ["http://data.europa.eu/eli/reg/2024/1689/oj"]


@pytest.mark.parametrize("p, celex, kept", [
    ("resource_legal_amends_resource_legal", "32026R1744", "amended by 32026R1744"),
    ("act_consolidated_consolidates_resource_legal", "02024R1689-20260727",
     "consolidated version 02024R1689-20260727"),
    ("act_consolidated_consolidates_resource_legal", "02018R1139-20260802", None),
    ("resource_legal_proposes_to_amend_resource_legal", "52025PC0836", "proposal to amend 52025PC0836"),
    ("resource_legal_based_on_resource_legal", "52025IP0198", None),
])
def test_eu_relation_filter(p, celex, kept):
    row = {"own": "32024R1689", "p": f"http://publications.europa.eu/ontology/cdm#{p}", "celex": celex}
    assert watch._relation(row) == kept


def test_stale_exit_code_only_when_something_is_due(tmp_path):
    raw = minimal(last_verified="2026-09-01", verified_against="official")
    (tmp_path / "x.yaml").write_text(yaml.safe_dump(raw))
    args = ["--data", str(tmp_path), "stale", "--exit-code"]
    assert cli.main(args + ["--today", "2026-09-27"]) == 0
    assert cli.main(args + ["--today", "2027-09-27"]) == 3


def test_verified_against_is_required_with_last_verified():
    with pytest.raises(ValidationError, match="needs verified_against"):
        parse(minimal(last_verified="2026-01-01"), "x.yaml")
    with pytest.raises(ValidationError, match="needs last_verified"):
        parse(minimal(verified_against="official"), "x.yaml")
    ok = parse(minimal(last_verified="2026-01-01", verified_against="official"), "x.yaml")
    assert ok.verified_against == "official"


def test_stale_official_lists_secondary_only_checks(capsys, tmp_path):
    fresh = {"last_verified": "2026-09-01"}
    entries = [
        minimal(id="checked-official", verified_against="official", **fresh),
        minimal(id="checked-secondary", verified_against="secondary", **fresh),
    ]
    for raw in entries:
        (tmp_path / f"{raw['id']}.yaml").write_text(yaml.safe_dump(raw))
    args = ["--data", str(tmp_path), "stale", "--today", "2026-09-27"]
    cli.main(args)
    assert "Everything verified" in capsys.readouterr().out
    cli.main(args + ["--official"])
    listed = {line.split()[0] for line in capsys.readouterr().out.splitlines() if line.strip()}
    assert listed == {"checked-secondary"}


# --- requirements -----------------------------------------------------------

from airegs import query  # noqa: E402


def req(**over):
    raw = {"id": "r1", "ref": "Art. 1", "title": "T", "kind": "obligation",
           "category": "risk-management", "roles": ["provider"], "summary": "S."}
    raw.update(over)
    return raw


@pytest.mark.parametrize("over, msg", [
    ({"roles": ["wizard"]}, "unknown roles"),
    ({"category": "vibes"}, "unknown category"),
    ({"evidence": ["selfie"]}, "unknown evidence"),
    ({"assurance": "certification"}, "assurance must be a list"),
    ({"applies_from": "soon"}, "not a YYYY-MM-DD"),
    ({"colour": "red"}, "unknown fields"),
    ({"summary": ""}, "missing summary"),
])
def test_requirement_validation(over, msg):
    with pytest.raises(ValidationError, match=msg):
        parse(minimal(requirements=[req(**over)]), "x.yaml")


def test_duplicate_requirement_ids_rejected():
    with pytest.raises(ValidationError, match="duplicate id"):
        parse(minimal(requirements=[req(), req()]), "x.yaml")


def test_crosswalk_target_must_exist(tmp_path):
    raw = minimal(id="a", requirements=[req(maps_to=["b#nope"])])
    (tmp_path / "a.yaml").write_text(yaml.safe_dump(raw))
    with pytest.raises(ValidationError, match="does not exist"):
        load(tmp_path)


def test_seed_requirements_load_with_crosswalk(registry):
    reqs = [r for i in registry.values() for r in i.requirements]
    assert len(reqs) >= 80
    links = __import__("airegs.requirements", fromlist=["x"]).crosswalk(registry.values())
    # Links are stored both ways.
    assert "eu-ai-act#art-9" in links["iso-iec-42001#cl-6-1-2"]


def test_find_filters_combine(registry):
    insts = list(registry.values())
    hits = query.find(insts, jurisdiction=["EU"], assurance=["third-party-assessment"], role=["provider"])
    keys = {r.key for _, r in hits}
    assert "eu-ai-act#art-43" in keys
    assert all(i.jurisdiction == "EU" and "provider" in r.roles for i, r in hits)


def test_find_on_date_respects_applies_from(registry):
    insts = list(registry.values())
    keys = lambda day: {r.key for _, r in query.find(insts, on=D(*day))}
    assert "eu-ai-act#art-9" not in keys((2026, 9, 27))
    assert "eu-ai-act#art-9" in keys((2027, 12, 2))
    assert "us-co-sb24-205#deployer-duties" not in keys((2027, 1, 1))  # superseded


def test_find_text_matches_controls(registry):
    hits = query.find(list(registry.values()), text="weights")
    assert "us-ca-sb53#frontier-framework" in {r.key for _, r in hits}


def test_export_and_explorer(registry, tmp_path, capsys):
    data = query.export(list(registry.values()), D(2026, 9, 27))
    assert {"instruments", "requirements", "vocab"} <= set(data)
    art9 = next(r for r in data["requirements"] if r["key"] == "eu-ai-act#art-9")
    assert "iso-iec-42001#cl-6-1-2" in art9["links"]
    out = tmp_path / "explorer.html"
    cli.main(["explorer", "--out", str(out), "--today", "2026-09-27"])
    html = out.read_text()
    assert "/*REGISTRY_DATA*/" not in html and '"eu-ai-act#art-9"' in html
    assert "</script" not in html.split("const DATA = ", 1)[1].split("\n", 1)[0]


def test_obligations_cli(capsys):
    cli.main(["obligations", "--role", "deployer", "-j", "EU", "--category", "impact-assessment"])
    out = capsys.readouterr().out
    assert "eu-ai-act#art-27" in out and "1 requirement(s)" in out


def test_site_builds_installable_app(tmp_path):
    out = tmp_path / "site"
    cli.main(["site", "--out", str(out), "--today", "2026-09-28"])
    html = (out / "index.html").read_text()
    assert html.startswith("<!doctype html>")
    assert 'rel="manifest"' in html and 'const MODE = "app"' in html
    assert "__BUILD_ID__" not in (out / "sw.js").read_text()
    for name in ("manifest.webmanifest", "icon-192.png", "icon-512.png", "apple-touch-icon.png"):
        assert (out / name).exists()


def test_artifact_build_keeps_ask(tmp_path):
    out = tmp_path / "e.html"
    cli.main(["explorer", "--out", str(out), "--today", "2026-09-28"])
    html = out.read_text()
    assert 'const MODE = /*APP_MODE*/"artifact"' in html and "<!doctype" not in html
