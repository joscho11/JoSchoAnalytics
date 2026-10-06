"""Public NFL abbreviations on the JoSchoAnalytics website.

nflverse records and internal joins keep ``LA`` for the Los Angeles Rams.
Every user-visible abbreviation is ``LAR``. Do not rewrite stored records.
"""
from __future__ import annotations

import re

# Exact stored code -> what the website shows. LAC (Chargers) is not in here.
_PUBLIC_TEAM_ABBR = {"LA": "LAR"}
_RAMS_TOKEN = re.compile(r"\bLA\b")
_MISSING = {"", "nan", "None", "<NA>", "NaT"}


def public_team_abbr(code) -> str:
    """Map one stored team code to the abbreviation the website shows."""
    if code is None:
        return ""
    try:
        if code != code:  # NaN
            return ""
    except Exception:
        pass
    text = str(code).strip()
    if text in _MISSING:
        return ""
    return _PUBLIC_TEAM_ABBR.get(text, text)


def public_matchup_text(value) -> str:
    """Replace a standalone Rams token in a label or sentence. Leaves LAC alone."""
    if value is None:
        return ""
    return _RAMS_TOKEN.sub("LAR", str(value))
