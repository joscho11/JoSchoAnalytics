"""Canonical All-Pro player identity — the single source of truth for who is who.

WHY THIS EXISTS (2026-08-03)
----------------------------
`betting/nfl_allpro_1997_2025.csv` has no player ID. Every consumer keyed on the `Player`
NAME, which silently merges distinct people who share one. The source contains exactly one
such collision in 2,047 rows:

    ILB,C.J. Mosley,BAL,2014,defense
    MLB,C.J. Mosley,DET,2014,defense

Two different real players. Because the weighted 3-year lookback then ran

    comb.sort_values("Weight", ascending=False).drop_duplicates(["Player", "Year_target"])

one of them was discarded, and *which* one depended on `sort_values`' default
`kind="quicksort"`, which is not stable. Consequences, per target season:

* **2015** — both rows carry weight 4 (one year back). One team arbitrarily survives.
* **2016** — both carry weight 2 (two years back). One team arbitrarily survives.
* **2017** — the BAL player's newer 2016 selection wins weight 4, and the *separate* DET
  player's 2014 weight-1 record is discarded as if it were the same person.
* Four production features (`diff_active_allpro_weighted`,
  `diff_allpro_last_3_years_weighted`, `allpro_diff_home_off_away_def_3_years`,
  `away_defense_allpro_3_years`) moved between pandas 2.3.3 and 3.0.3, shifting tier
  membership in the walk-forward.

**Adding `kind="stable"` would only have made the wrong answer deterministic.** The defect
is identity, not ordering. This module fixes identity and removes the order dependence
entirely by never sorting: the lookback dedupe is a `groupby(...).max()`, which is
invariant under row permutation by construction.

DESIGN
------
* Unambiguous names get a deterministic default identity derived from the name alone.
* A name that ever appears on two teams in the same year is AMBIGUOUS, and then **every**
  row bearing that name must be assigned explicitly in `IDENTITY_OVERRIDES` — including
  the years that are not themselves collisions, because a per-collision-year fix would
  sever the rest of that player's lineage.
* An unresolved collision **aborts**. It is never guessed.
"""
from __future__ import annotations

import re
import unicodedata

import pandas as pd

__all__ = [
    "AllProIdentityError", "IDENTITY_OVERRIDES", "REVIEW_NOTES",
    "default_identity", "resolve_allpro_identities", "weighted_lookback",
]

WEIGHTS_BY_YEARS_BACK = {1: 4, 2: 2, 3: 1}


class AllProIdentityError(RuntimeError):
    """An identity collision the override table does not resolve. Fail closed."""


def default_identity(name: str) -> str:
    """Deterministic identity for an unambiguous name. Pure function of the name."""
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


# ---------------------------------------------------------------------------
# Reviewed identity overrides, keyed by (Player, Year, Team) from the source file.
# ---------------------------------------------------------------------------
# Every row whose Player name appears here MUST be listed, not just the colliding year.
_MOSLEY_RAVENS = "cj_mosley__ravens_jets_ilb"
_MOSLEY_LIONS = "cj_mosley__lions_2014"

IDENTITY_OVERRIDES: dict[tuple[str, int, str], str] = {
    # --- C.J. Mosley: two distinct players sharing a name ---------------------
    # Reviewed 2026-08-03. The source lists BOTH BAL and DET for 2014. A single player
    # cannot hold two teams in one All-Pro class, so these are two people. The BAL 2014
    # selection belongs to the linebacker whose selections continue at BAL in 2016, 2017
    # and 2018 and at NYJ in 2022 and 2023 — that continuous lineage is why the BAL 2014
    # row must share an identity with those later rows rather than being resolved in
    # isolation. The DET 2014 row is the other player and has no other selection in the
    # file.
    ("C.J. Mosley", 2014, "BAL"): _MOSLEY_RAVENS,
    ("C.J. Mosley", 2014, "DET"): _MOSLEY_LIONS,
    ("C.J. Mosley", 2016, "BAL"): _MOSLEY_RAVENS,
    ("C.J. Mosley", 2017, "BAL"): _MOSLEY_RAVENS,
    ("C.J. Mosley", 2018, "BAL"): _MOSLEY_RAVENS,
    ("C.J. Mosley", 2022, "NYJ"): _MOSLEY_RAVENS,
    ("C.J. Mosley", 2023, "NYJ"): _MOSLEY_RAVENS,
}

REVIEW_NOTES = {
    "C.J. Mosley": (
        "Two distinct players. BAL 2014 + BAL 2016/2017/2018 + NYJ 2022/2023 are one "
        "linebacker; DET 2014 is a different player with a single selection. Resolved "
        "manually because the source carries no player ID and a name key merges them. "
        "The team-change BAL->NYJ is the SAME identity — a real move must not create a "
        "second identity."
    ),
}

# Names that must be fully covered by IDENTITY_OVERRIDES once seen in the source.
_AMBIGUOUS_NAMES = frozenset(n for (n, _y, _t) in IDENTITY_OVERRIDES)


def resolve_allpro_identities(ap: pd.DataFrame, *, player_col: str = "Player",
                              year_col: str = "Year", team_col: str = "Team",
                              out_col: str = "allpro_id") -> pd.DataFrame:
    """Attach a canonical `allpro_id` to every row. Fails closed on unresolved collisions.

    Invariants enforced here (not merely documented):
      1. every row receives a non-null identity;
      2. any (name, year) appearing on more than one team must be covered by the override
         table, else `AllProIdentityError`;
      3. once a name is in the override table, every row with that name must be covered,
         so a lineage cannot be half-resolved;
      4. no identity may hold two teams in the same year after resolution.
    """
    for col in (player_col, year_col, team_col):
        if col not in ap.columns:
            raise AllProIdentityError(f"All-Pro frame is missing {col!r}")
    out = ap.copy()

    # (2) detect collisions in the DATA, independently of the override table.
    spans = out.groupby([player_col, year_col])[team_col].nunique()
    colliding = {name for (name, _yr) in spans[spans > 1].index}
    unresolved = sorted(colliding - _AMBIGUOUS_NAMES)
    if unresolved:
        raise AllProIdentityError(
            "unresolved All-Pro identity collision(s) — the same name appears on more than "
            f"one team in one year and no reviewed override exists: {unresolved}. Add an "
            "entry to IDENTITY_OVERRIDES for EVERY row of that name (not only the "
            "colliding year) after confirming who is who."
        )

    keys = list(zip(out[player_col], out[year_col].astype(int), out[team_col]))
    ids, missing = [], []
    for name, yr, team in keys:
        if name in _AMBIGUOUS_NAMES:
            ident = IDENTITY_OVERRIDES.get((name, yr, team))
            if ident is None:
                missing.append((name, yr, team))
                ident = None
            ids.append(ident)
        else:
            ids.append(default_identity(name))
    # (3) a partially-covered ambiguous name is a defect, not a fallback.
    if missing:
        raise AllProIdentityError(
            "ambiguous All-Pro name(s) with rows missing from IDENTITY_OVERRIDES: "
            f"{sorted(set(missing))}. Every row of an ambiguous name must be assigned, or "
            "the player's lineage is silently split."
        )
    out[out_col] = ids
    # (1) non-null everywhere.
    if out[out_col].isna().any():
        raise AllProIdentityError("identity resolution produced null keys")
    # (4) post-resolution, one identity must not hold two teams in a year.
    bad = out.groupby([out_col, year_col])[team_col].nunique()
    bad = bad[bad > 1]
    if len(bad):
        raise AllProIdentityError(
            f"identity holds >1 team in a single year after resolution: {list(bad.index)}")
    return out


def weighted_lookback(ap: pd.DataFrame, target_season: int, *,
                      id_col: str = "allpro_id", year_col: str = "Year",
                      team_col: str = "Team") -> pd.DataFrame:
    """Per-team weighted All-Pro count for one target season. ORDER-INVARIANT.

    Each identity contributes its **maximum** weight across the three-year window — a
    player selected in several lookback years counts once, at his most recent (highest)
    weight — credited to the team of that highest-weight selection.

    There is no `sort_values` anywhere in this function. Selection is `idxmax` over a
    deterministic key, so the result cannot depend on input row order or on the sort
    implementation pandas happens to use.
    """
    frames = []
    for yrs_back, weight in WEIGHTS_BY_YEARS_BACK.items():
        sel = ap[ap[year_col] == target_season - yrs_back]
        if len(sel):
            f = sel[[id_col, team_col, year_col]].copy()
            f["Weight"] = weight
            frames.append(f)
    if not frames:
        return pd.DataFrame(columns=["season", team_col, "allpro_weighted"])
    comb = pd.concat(frames, ignore_index=True)

    # Deterministic tie-break: highest Weight, then most recent Year, then team code.
    # Ranking on a composite key rather than sorting keeps this permutation-invariant.
    comb["_rank_key"] = (comb["Weight"].astype("int64") * 1_000_000
                         + comb[year_col].astype("int64") * 100
                         + comb[team_col].astype(str).map(lambda t: sum(ord(c) for c in t) % 100))
    pick = comb.loc[comb.groupby(id_col)["_rank_key"].idxmax()]
    wc = pick.groupby(team_col)["Weight"].sum().reset_index()
    wc.insert(0, "season", target_season)
    wc.columns = ["season", team_col, "allpro_weighted"]
    return wc


# ---------------------------------------------------------------------------
# Injury -> All-Pro identity matching (shared by training and serving)
# ---------------------------------------------------------------------------
# The aggregate fix above resolved `allpro_id` and then BOTH consumers threw it away and
# merged injuries on `_name_norm + season` (features.py) / `["norm_name","season"]`
# (model_comparison.ipynb). With two players sharing a name in the same weight window that
# merge FANS OUT: one injury row matches two All-Pro rows, so the injured player's weight is
# subtracted twice and `diff_active_allpro_weighted` (PROD_FEATURES_35 #11) is wrong.
#
# There is no shared player ID: nflverse injuries carry `gsis_id`, the All-Pro CSV carries
# no ID at all. So matching is name+season, with an explicit fail-closed crosswalk for the
# names that are ambiguous in that season's weight window. Team is used only to
# disambiguate a collision -- never as a general join key, because a player's All-Pro weight
# is earned at a former team (the BAL->NYJ lineage must keep matching).
INJURY_IDENTITY_CROSSWALK: dict[tuple[str, int, str], str] = {
    # C.J. Mosley is ambiguous in seasons 2015-2017 (both 2014 selections sit in the
    # 3-year window). Reviewed 2026-08-03: the injured man's CURRENT team resolves it.
    ("cj mosley", 2015, "BAL"): _MOSLEY_RAVENS,
    ("cj mosley", 2015, "DET"): _MOSLEY_LIONS,
    ("cj mosley", 2016, "BAL"): _MOSLEY_RAVENS,
    ("cj mosley", 2016, "DET"): _MOSLEY_LIONS,
    ("cj mosley", 2017, "BAL"): _MOSLEY_RAVENS,
    ("cj mosley", 2017, "DET"): _MOSLEY_LIONS,
}


def _norm(s):
    """Local copy of features.norm_name semantics (avoids a circular import)."""
    import re as _re
    if not isinstance(s, str):
        return ""
    s = "".join(c for c in unicodedata.normalize("NFD", s)
                if unicodedata.category(c) != "Mn").lower().strip()
    s = _re.sub(r"\s+(jr\.?|sr\.?|ii|iii|iv|v)\s*$", "", s)
    s = _re.sub(r"[\'.\-]", "", s)
    return _re.sub(r"\s+", " ", s).strip()


def attach_injury_identity(inj: pd.DataFrame, allpro_weighted: pd.DataFrame, *,
                           inj_name_col: str, inj_team_col: str = "team",
                           season_col: str = "season",
                           id_col: str = "allpro_id") -> pd.DataFrame:
    """Attach `allpro_id` to injury rows. At most one identity per row; ambiguity aborts.

    `allpro_weighted` must already carry `allpro_id` and one row per (identity, season).
    Injury rows that match no All-Pro identity get NaN and are dropped by the caller, which
    is the pre-existing behaviour for non-All-Pro players.
    """
    ap = allpro_weighted.copy()
    ap["_name_norm"] = ap["Player"].map(_norm)
    # name -> identities present in that season's weight window
    per_season = (ap.groupby(["_name_norm", season_col])[id_col]
                    .agg(lambda s: sorted(set(s))).to_dict())

    out = inj.copy()
    out["_name_norm"] = out[inj_name_col].map(_norm)
    ids, unresolved = [], []
    for nm, seas, team in zip(out["_name_norm"], out[season_col].astype(int),
                              out[inj_team_col]):
        cands = per_season.get((nm, seas))
        if not cands:
            ids.append(None)
        elif len(cands) == 1:
            ids.append(cands[0])
        else:
            key = (nm, seas, team)
            hit = INJURY_IDENTITY_CROSSWALK.get(key)
            if hit is None:
                unresolved.append(key)
                ids.append(None)
            else:
                ids.append(hit)
    if unresolved:
        raise AllProIdentityError(
            "ambiguous injury->All-Pro match(es) with no reviewed crosswalk entry: "
            f"{sorted(set(unresolved))}. Two All-Pro players share this name in that "
            "season's weight window; add (norm_name, season, team) -> identity to "
            "INJURY_IDENTITY_CROSSWALK after confirming who is injured. Name-only "
            "matching would duplicate the row and double-subtract the weight."
        )
    out[id_col] = ids
    return out


def injured_allpro_weight(inj: pd.DataFrame, allpro_weighted: pd.DataFrame, *,
                          inj_name_col: str, inj_team_col: str = "team",
                          season_col: str = "season",
                          weight_col: str = "weight") -> pd.DataFrame:
    """Per-team injured All-Pro weight. THE shared implementation for train and serve.

    Returns the matched injury rows carrying `allpro_id` and `weight`, with a hard
    assertion that the merge did not fan out.
    """
    ap = allpro_weighted[["allpro_id", season_col, weight_col, "Player"]].copy()
    dup = ap.duplicated(["allpro_id", season_col]).sum()
    if dup:
        raise AllProIdentityError(
            f"allpro_weighted has {dup} duplicate (identity, season) rows — dedupe to the "
            "max weight before matching injuries")
    tagged = attach_injury_identity(inj, allpro_weighted, inj_name_col=inj_name_col,
                                    inj_team_col=inj_team_col, season_col=season_col)
    n_before = len(tagged)
    merged = tagged.merge(ap.drop(columns=["Player"]), on=["allpro_id", season_col],
                          how="left")
    if len(merged) != n_before:
        raise AllProIdentityError(
            f"injury merge fanned out: {n_before} rows -> {len(merged)}; an injury row "
            "matched more than one All-Pro identity")
    return merged[merged[weight_col].notna()]
