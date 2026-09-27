"""Detect changes to watched source pages by hashing their normalised text.

A change never edits the registry. It is reported so a person (or an LLM
drafting a pull request for a person to review) can check what moved.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.request
from pathlib import Path
from typing import Callable

from .schema import Instrument

USER_AGENT = "ai-regulation-registry/0.1 (+change detection)"


def fetch(url: str, timeout: float = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode(resp.headers.get_content_charset() or "utf-8", "replace")


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
                h = digest(fetcher(url))
            except Exception as e:  # network errors shouldn't stop the other checks
                results.append({"instrument": inst.id, "url": url, "status": "error", "error": str(e)})
                continue
            old = state.get(url)
            status = "new" if old is None else ("unchanged" if old == h else "changed")
            state[url] = h
            results.append({"instrument": inst.id, "url": url, "status": status})
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    return results
