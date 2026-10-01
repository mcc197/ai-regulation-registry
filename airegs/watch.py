"""Detect changes to watched source pages by hashing their normalised text.

A change never edits the registry. It is reported so a person (or an LLM
drafting a pull request for a person to review) can check what moved.
"""

from __future__ import annotations

import hashlib
import html
import json
import csv
import io
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

from .schema import Instrument

USER_AGENT = "ai-regulation-registry/0.1 (+change detection)"

# EUR-Lex answers scripts with an empty bot challenge, and a published Official Journal
# text never changes anyway. For EUR-Lex ELI links we watch the Publications Office
# metadata instead: what amends, corrects, consolidates or proposes to amend the act.
EURLEX_ELI = re.compile(r"^https?://eur-lex\.europa\.eu/eli/(.+?)/?$")
SPARQL = "https://publications.europa.eu/webapi/rdf/sparql"
RELATIONS = {
    "resource_legal_amends_resource_legal": "amended by",
    "resource_legal_corrects_resource_legal": "corrigendum",
    "act_consolidated_consolidates_resource_legal": "consolidated version",
    "resource_legal_repeals_resource_legal": "repealed by",
    "resource_legal_proposes_to_amend_resource_legal": "proposal to amend",
    "resource_legal_based_on_resource_legal": "act based on it",
    "resource_legal_completes_resource_legal": "supplemented by",
}
QUERY = """PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT DISTINCT ?own ?p ?celex WHERE {
  ?act cdm:resource_legal_eli ?eli . FILTER(STR(?eli) = "%s")
  ?act cdm:resource_legal_id_celex ?own .
  VALUES ?p { %s }
  ?w ?p ?act . ?w cdm:resource_legal_id_celex ?celex .
}"""


def fetch(url: str, timeout: float = 30) -> str | list[str]:
    """Page text, or for EUR-Lex acts a list of related acts (see `eu_relations`)."""
    m = EURLEX_ELI.match(url)
    if m:
        return eu_relations(f"http://data.europa.eu/eli/{m.group(1)}", timeout)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode(resp.headers.get_content_charset() or "utf-8", "replace")


def eu_relations(eli: str, timeout: float = 60) -> list[str]:
    """Acts linked to an EU act, as 'relation CELEX' lines, from the CELLAR SPARQL endpoint."""
    preds = " ".join(f"cdm:{p}" for p in RELATIONS)
    q = urllib.parse.urlencode({"query": QUERY % (eli, preds)})
    req = urllib.request.Request(f"{SPARQL}?{q}", headers={"Accept": "text/csv", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        rows = list(csv.DictReader(io.StringIO(resp.read().decode("utf-8"))))
    if not rows:
        raise ValueError(f"no metadata found for {eli}")
    return sorted({line for r in rows if (line := _relation(r))})


def _relation(row: dict) -> str | None:
    """Keep legal acts, corrigenda, proposals and the act's own consolidated texts;
    drop resolutions, staff documents and consolidated texts of other acts."""
    rel, celex, own = RELATIONS[row["p"].rsplit("#", 1)[1]], row["celex"], row["own"]
    if rel == "consolidated version":
        return f"{rel} {celex}" if celex.startswith("0" + own[1:]) else None
    if celex.startswith("3") or celex[5:7] == "PC":
        return f"{rel} {celex}"
    return None


def normalise(page: str) -> str:
    """Visible text only, so layout and script churn doesn't count as a change."""
    page = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", page)
    page = re.sub(r"(?s)<[^>]+>", " ", page)
    return re.sub(r"\s+", " ", html.unescape(page)).strip()


def digest(page: str) -> str:
    return hashlib.sha256(normalise(page).encode()).hexdigest()


def check(instruments: list[Instrument], state_path: Path,
          fetcher: Callable[[str], str] = fetch) -> list[dict]:
    """Return one result per watched source and update the saved hashes.

    Each result has `status`: 'new' (first time seen), 'changed', 'unchanged' or 'error'.
    Where the fetcher returns a list (EU acts), a change also lists `added` and `removed`
    items. A page with no visible text is an error, not a hash: it is usually a bot
    challenge, and hashing it would hide every later change.
    """
    state_path = Path(state_path)
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    results = []
    for inst in instruments:
        for src in inst.sources:
            if not src.get("watch"):
                continue
            url = src["url"]
            try:
                page = fetcher(url)
                items = sorted(set(page)) if isinstance(page, list) else None
                text = "\n".join(items) if items is not None else normalise(page)
                if not text:
                    raise ValueError("no visible text (blocked or bot challenge?)")
            except Exception as e:  # network errors shouldn't stop the other checks
                results.append({"instrument": inst.id, "url": url, "status": "error", "error": str(e)})
                continue
            h = hashlib.sha256(text.encode()).hexdigest()
            old = state.get(url)
            old_hash = old.get("hash") if isinstance(old, dict) else old
            status = "new" if old is None else ("unchanged" if old_hash == h else "changed")
            result = {"instrument": inst.id, "url": url, "status": status}
            if status == "changed" and items is not None and isinstance(old, dict):
                before = set(old.get("items", []))
                result["added"] = [i for i in items if i not in before]
                result["removed"] = sorted(before - set(items))
            state[url] = {"hash": h, "items": items} if items is not None else h
            results.append(result)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    return results
