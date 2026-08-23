"""Pick the newest ANPR extract by build number, not file timestamps."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

_VERSION_RE = re.compile(r'APP_VERSION\s*=\s*"([^"]+)"')
_REV_RE = re.compile(r"-r(\d+)\s*$", re.IGNORECASE)


def read_app_version(folder: str) -> str:
    path = Path(folder) / "anpr" / "version.py"
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    match = _VERSION_RE.search(text)
    return match.group(1) if match else ""


def revision_number(version: str) -> int:
    match = _REV_RE.search(version or "")
    return int(match.group(1)) if match else -1


def choose_anpr_source(folders: Iterable[str], preferred: str = "") -> str:
    """Return the folder with the highest rN. Ties prefer the launched folder."""
    scored = []
    seen = set()
    for folder in folders:
        if not folder:
            continue
        key = str(Path(folder))
        if key in seen:
            continue
        seen.add(key)
        scored.append((revision_number(read_app_version(folder)), key))
    if not scored:
        return ""
    best_rev = max(item[0] for item in scored)
    top = [path for rev, path in scored if rev == best_rev]
    if preferred:
        pref = str(Path(preferred))
        for path in top:
            if path == pref:
                return path
    return top[0]
