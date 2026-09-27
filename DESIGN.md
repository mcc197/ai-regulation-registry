# AI Regulation Registry: design

A live, queryable record of major AI laws, regulations, standards and frameworks.
It answers questions like:

- What AI obligations apply in the EU on 1 January 2027?
- What changes in the next 90 days, anywhere?
- What amended the EU AI Act, and which dates moved?
- Which standards support NIST AI RMF or ISO/IEC 42001?
- Which entries haven't been checked against their source in 90 days?

## 1. Principles

1. **Every fact has a source and a check date.** An entry without `sources` fails
   validation. An entry whose `last_verified` is older than 90 days shows up in
   `airegs stale`.
2. **Dates are the backbone.** An instrument's status on a given day comes from its
   dated milestones. It is never a hand-set field, because hand-set fields drift. An
   amendment that moves a deadline is recorded as a new milestone plus an `amended_by`
   link. The old date is not silently overwritten.
3. **Git is the database of record; SQLite is the query engine.** Curated YAML files
   are easy to review, diff and blame, and the git log is the audit trail. They compile
   in about a second into a SQLite file with full-text search for querying.
4. **Automation proposes, humans approve.** Watchers and LLM triage open pull requests
   or issues. Nothing reaches `main` without review, because a wrong compliance date
   costs more than a late one.

## 2. Scope

| Type | Examples | Binding |
|---|---|---|
| `legislation` | EU AI Act, Colorado SB 26-189, Korea AI Basic Act | yes |
| `regulation` | China GenAI Interim Measures, delegated/implementing acts | yes |
| `treaty` | Council of Europe Framework Convention (CETS 225) | yes, once ratified |
| `executive_order` | US federal EOs | yes, for government |
| `standard` | ISO/IEC 42001, ISO/IEC 23894, CEN-CENELEC harmonised standards | voluntary; harmonised standards give a presumption of conformity |
| `framework` | NIST AI RMF, NIST AI 600-1 | voluntary |
| `code_of_practice` / `guidance` | EU GPAI Code of Practice, regulator guidance | voluntary / interpretive |

The bar for inclusion is **major**: national or supranational binding instruments,
significant sub-national laws (US states, Chinese provinces only if distinctive),
and standards or frameworks that regulators cite. Bills are included once they pass
one chamber, or earlier if they are widely tracked. Otherwise the registry becomes a
legislative-tracking product, which is a much bigger job.

## 3. Data model

```
Instrument ──< Milestone        (dated lifecycle events: proposed, adopted, in force, applies, ...)
     │    ──< Provision         (optional: article-level obligations, who they bind, when)
     │    ──< Source            (official text first, then secondary)
     └──< Relation >── Instrument  (amends, amended_by, supersedes, superseded_by,
                                    implements, supports, references)
```

### Instrument (one YAML file each: `data/instruments/<id>.yaml`)

| Field | Notes |
|---|---|
| `id` | Stable slug, e.g. `eu-ai-act`. Never reused. |
| `title`, `short_title` | |
| `type`, `binding` | From the table above. |
| `jurisdiction` | ISO 3166 code (`US-CO`, `KR`) or bloc code (`EU`, `COE`, `INTL`). |
| `issuer` | Body that made it. |
| `official_id` | CELEX number, bill number, standard number. |
| `url` | Canonical official text. |
| `topics` | Controlled vocabulary (see `airegs/schema.py`), used for filtering. |
| `summary` | Two or three neutral sentences. No legal advice. |
| `milestones[]` | `{date, event, scope?, note?}`. `event` comes from a fixed lifecycle vocabulary. |
| `provisions[]` | Optional `{ref, title, applies_to[], applies_from}`. Fill these in only where people need them. |
| `relations[]` | `{type, target}`, validated so that the target exists. |
| `sources[]` | `{url, label, kind: official\|secondary}`. At least one is required. |
| `last_verified`, `review_notes` | Provenance and anything uncertain. |

### Milestone events and derived status

`proposed → adopted → published → entry_into_force → applies (possibly several, phased) → amended → repealed | superseded | withdrawn`

`status_on(date)` takes the latest lifecycle event on or before `date`. So the EU AI
Act reads *in force, partly applicable* in 2025 and *applies* for a scope once the
relevant milestone passes. Colorado SB 24-205 reads *superseded* from 14 May 2026.
Standards and frameworks use `published` and `withdrawn`.

### Why not a graph DB, vector DB or hosted SaaS database?

At a few hundred to a few thousand instruments, the whole corpus fits in memory.
Relations are one hop, which SQL joins handle fine, and review-by-diff matters more
than write throughput. Semantic search can come later as a sidecar (section 6)
without changing the source of truth.

## 4. Keeping it live

```
 official sources ──► watchers ──► change detected ──► triage ──► PR / issue ──► human review ──► main
 (EUR-Lex, Federal       (nightly     (content hash      (diff +      (edits YAML,     (CI validates
  Register, state         cron)        changed)           LLM summary)  cites source)    schema + links)
  legislatures, ISO,
  NIST, CAC, OJ ...)
```

**Watchers (tier 1, deterministic).** Each source can set `watch: true`. `airegs watch`
fetches the page, normalises the text (strips tags and whitespace), hashes it, and
compares the hash with `state/watch.json`. A change becomes a "check this" item. It
does not change any facts on its own. Where a source offers structured feeds, use those
in preference to scraping:

| Source | Feed |
|---|---|
| EUR-Lex / Official Journal | CELLAR SPARQL endpoint and RSS (new acts, consolidated versions) |
| US federal | Federal Register API (`/documents.json?conditions[term]=artificial intelligence`) |
| US states | LegiScan API (bill status changes by keyword) or Open States |
| UK | legislation.gov.uk Atom feeds, GOV.UK Content API |
| Standards | ISO/IEC JTC 1/SC 42 project list, CEN-CENELEC JTC 21 work programme, NIST CSRC/AI pages |
| Others | Regulator press pages (CAC, MSIT, Japan Cabinet Office), polled by hash |

**Discovery (tier 2).** A weekly job searches news and law-firm trackers for new
instruments that aren't in the registry yet and opens an issue listing candidates.
This is where an LLM earns its keep: it reads the changed page or the candidate, drafts
the YAML diff with a quoted passage and a source URL for every date, and opens a PR.
The human reviewer checks the quotes. The model never becomes the source.

**Staleness (tier 3).** `airegs stale --days 90` lists entries due for a re-check,
ordered by the nearest upcoming milestone. A deadline next month matters more than a
2023 standard.

**Scheduling.** GitHub Actions cron (nightly watch, weekly discovery, weekly stale
report posted as an issue). The workflow in this repo only validates and tests. The
scheduled jobs are described here but not switched on.

## 5. Querying

| Interface | Use |
|---|---|
| `airegs` CLI | `applies-on`, `upcoming`, `search`, `show`, `relations`, `stale` |
| SQL on `build/registry.db` | Ad-hoc analysis. Tables: `instruments`, `milestones`, `relations`, `sources`, `topics`, plus FTS5 `instruments_fts`. |
| [Datasette](https://datasette.io) on the same file | Free web UI, JSON API and CSV export, no code |
| MCP server (next step) | Exposes `search`, `applies_on`, `upcoming` and `show` as tools, so Claude or another assistant can answer questions from the registry, with citations, instead of from memory |

Example SQL: everything taking effect in the next six months:

```sql
SELECT m.date, i.short_title, m.event, m.scope
FROM milestones m JOIN instruments i USING (instrument_id)
WHERE m.date BETWEEN date('now') AND date('now', '+6 months')
ORDER BY m.date;
```

## 6. Roadmap

1. **Now (this prototype):** schema, validator, 12 seed instruments, SQLite build with
   full-text search, CLI, source watcher, CI validation.
2. **Next:** coverage pass (the rest of the US states, UK, Canada, Brazil, India,
   Japan, Singapore, China's labelling measures, EU implementing acts and harmonised
   standards), a Datasette deploy, and an MCP server.
3. **Then:** provision-level obligations for the big instruments (EU AI Act articles
   by role: provider, deployer, importer), crosswalks between standards and laws
   (for example ISO/IEC 42001 clauses to AI Act Art. 9–15), and embeddings over
   provision text for semantic search.
4. **Later:** notifications ("tell me when anything tagged `gpai` changes") via
   ntfy, email or webhooks (the notifiers from rail-alert-system can be reused).

## 7. Open decisions

- **Home:** this repository (moved out of rail-alert-system).
- **Licence of content:** summaries are our own words. Link to official texts; don't
  copy standards text (ISO/IEC text is copyrighted).
- **Depth vs breadth:** provision-level modelling is expensive to maintain. Do it for
  the EU AI Act first, and only where users are asking.
