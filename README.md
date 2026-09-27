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
python -m airegs watch    # hash watched source pages; exit code 3 if any changed
```

## Adding or updating an instrument

1. Add or edit a file under `data/instruments/<id>.yaml`. Copy an existing one.
2. Put every date in `milestones`. Never hand-set a status: status is worked out from
   the milestones. If an amendment moves a date, add the new milestone with a `note`
   giving the old date, and link the two instruments with `amends` / `amended_by`.
3. Cite at least one `official` source. Set `last_verified` to the day you checked it,
   and `verified_against` to `official` or `secondary` for what you actually read.
4. Run `python -m airegs validate` and `pytest`.

`airegs stale` lists entries not checked in the last 90 days. `airegs stale --official`
also lists entries checked only against secondary sources (law-firm notes,
trackers). As of Sept 2026 that is all of them, because the official sites were
unreachable from the environment used to check them.
