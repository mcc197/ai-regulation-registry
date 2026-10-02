# AI Regulation Registry

A curated, dated and sourced record of major AI laws, regulations, standards and
frameworks, which you can query from the command line or with SQL. See
[DESIGN.md](DESIGN.md) for the data model, how the registry stays current, and the
roadmap.

## Try it

```bash
pip install -r requirements.txt

python -m airegs applies-on 2027-01-01 -j US --binding   # what has effect then
python -m airegs upcoming --days 365                     # what's coming
python -m airegs show eu-ai-act                          # full timeline + sources
python -m airegs search 'literacy OR watermark*'         # full-text search
python -m airegs stale                                   # due for re-verification
python -m airegs build    # -> build/registry.db (open with sqlite3 or `datasette`)
python -m airegs watch    # check watched sources (EUR-Lex via CELLAR); exit 3 if any changed

# Obligations: filter requirements across every law and standard
python -m airegs obligations --assurance certification --assurance third-party-assessment
python -m airegs obligations --role deployer -j EU --detail
python -m airegs obligations --evidence logs --on 2028-01-01
python -m airegs obligations "red-teaming"
python -m airegs crosswalk "eu-ai-act#art-9"   # linked ISO, NIST and other requirements
python -m airegs stale --requirements          # requirements not yet verified
python -m airegs explorer                      # -> build/explorer.html (the web page)
```

## The explorer page

`python -m airegs explorer` writes a self-contained web page with the whole register
embedded. It has three tabs: **Obligations** (filters and search), **Ask** (Claude
answers questions from the register, citing requirements) and **Laws & standards**.
It is published as a claude.ai artifact; rebuild and republish it after data changes.

## The phone app

`python -m airegs site` builds the explorer as an installable web app (PWA) in
`build/site`: full screen, its own icon, works offline, no sign-in. It has no Ask tab,
because asking Claude needs the claude.ai version. The `app` workflow publishes it to
GitHub Pages on every push to `main`
(https://mcc197.github.io/ai-regulation-registry/).

One-off setup: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
On an iPhone, open the link in Safari, tap Share, then Add to Home Screen. On Android,
open it in Chrome and choose Install app.

## Adding or updating an instrument

1. Add or edit a file under `data/instruments/<id>.yaml`. Copy an existing one.
2. Put every date in `milestones`. Never hand-set a status: status is worked out from
   the milestones. If an amendment moves a date, add the new milestone with a `note`
   giving the old date, and link the two instruments with `amends` / `amended_by`.
3. Cite at least one `official` source. Set `last_verified` to the day you checked it,
   and `verified_against` to `official` or `secondary` for what you actually read.
4. Run `python -m airegs validate` and `pytest`.

`airegs stale` lists entries not checked in the last 90 days (`--exit-code` exits 3
if anything is due). Both checks run on a schedule and report through GitHub issues;
see "Scheduling" in DESIGN.md. `airegs stale --official`
also lists entries checked only against secondary sources (law-firm notes,
trackers). As of 27 Sept 2026 that is four entries (Korea, the two Colorado laws and
the CoE Convention), because their official sites were unreachable from the
environment used to check them.
