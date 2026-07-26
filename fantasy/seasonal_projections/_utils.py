"""Shared helpers for the seasonal-projections pipeline.

Kept in one place so the name-normalization convention is identical across
the ADP cache, the dataset builder, and (later) the join to model output.
"""
import unicodedata

# Sleeper fills 999.0 for "no ADP / undrafted"; anything at/above this is a sentinel.
ADP_SENTINEL = 900.0

# Cross-source name variants the normalizer can't bridge: Sleeper-side
# norm_name -> nflverse/dataset-side norm_name. Applied to the ADP frame at
# merge time in both dataset builders (the cached ADP CSV stores norm_name,
# so an alias inside norm_name() would never reach it).
SLEEPER_NAME_ALIASES = {
    "kenny gainwell": "kenneth gainwell",   # 2026: Sleeper "Kenny", nflverse "Kenneth" (audit M1)
    # 2026-07-26 code review: ADP + Sleeper projection were silently dropped for these
    # players. Each target was verified to exist in the dataset before being added; only
    # unambiguous same-person variants are listed. Fuzzy near-matches are deliberately NOT
    # aliased -- a wrong alias silently attaches another player's market number.
    "william fuller": "will fuller",           # Sleeper "William", nflverse "Will" (Fuller V)
    "joshua palmer": "josh palmer",            # Sleeper "Joshua", nflverse "Josh"
    "nyheim millerhines": "nyheim hines",      # legal name change; nflverse kept "Hines"
    "scotty miller": "scott miller",           # Sleeper "Scotty", nflverse "Scott"
    "drew ogletree": "andrew ogletree",        # Sleeper "Drew", nflverse "Andrew"
    "mitch tinsley": "mitchell tinsley",       # Sleeper "Mitch", nflverse "Mitchell"
}

# Skill positions we model.
SKILL_POSITIONS = ("QB", "RB", "WR", "TE")

_NAME_SUFFIXES = (" jr.", " jr", " sr.", " sr", " ii", " iii", " iv", " v")


def norm_name(s) -> str:
    """Normalize a player name for cross-source joins.

    Strips accents and Jr./Sr./roman-numeral suffixes, lowercases, and keeps
    only alphanumerics and spaces. Matches the convention used in the betting
    feature pipeline (betting/features.ipynb `norm_name`) so joins are
    consistent across the repo.

    Note: stripping Jr./Sr. means a father and son with the same name collapse
    to one key (e.g. "Frank Gore" and "Frank Gore Jr."). This only matters in
    the deep, undraftable tail and is documented in the ADP cache.
    """
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFD", str(s))
    s2 = "".join(c for c in nfkd if not unicodedata.combining(c)).lower()
    # No early break: matches the convention the cached ADP CSV was built with,
    # so join keys stay byte-identical. (Stacked suffixes don't occur in practice.)
    for sfx in _NAME_SUFFIXES:
        if s2.endswith(sfx):
            s2 = s2[: -len(sfx)]
    return "".join(c for c in s2 if c.isalnum() or c == " ").strip()
