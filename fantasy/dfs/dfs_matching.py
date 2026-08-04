"""Constrained DK <-> model-projection matching for the DFS pipeline.

WHY THIS EXISTS
---------------
The original `merge_projections` (duplicated in `dfs_pipeline.ipynb` and
`optimizer.ipynb`) matched a DraftKings salary row to a projection row with a bare
``difflib.get_close_matches(cutoff=0.72)`` over *every* projection name, with no
position and no team constraint. Because `predict_fantasy` drops every player ruled
Out, a real DK export always contains names the projection file does not have, so the
fuzzy fallback fired constantly and silently substituted a *different* player. Measured
leave-one-out over `projections_2025_week10.csv` (568 names): 148/568 = 26.1% of absent
players still got a match, 95 of them CROSS-POSITION -- e.g.

    Josh Allen (QB, BUF)      -> josh palmer   (WR, LAC)
    Aaron Rodgers (QB, PIT)   -> aaron jones   (RB, MIN)
    Mac Jones (QB, SF)        -> zay jones     (WR, ARI)
    Caleb Williams (QB, CHI)  -> kyle williams (WR, NE)

Every one of those rows was labelled ``match == "model"``, so the notebook's own
"unmatched" warning never flagged them and the wrong player's projection went straight
into the ILP objective.

THE CASCADE (in order; first hit wins)
--------------------------------------
1. ``id``            stable player id present on BOTH sides and equal.
2. ``exact``         normalized name equal, CONSTRAINED by compatible position AND
                     same (normalized) team. Exactly one candidate required.
3. ``team_mismatch`` normalized name + compatible position unique across the whole
                     projection file, but the teams disagree (trade not yet reflected,
                     or an abbreviation we do not normalize). Same human, stale team ->
                     the projection IS used, but the row keeps its own explicit status
                     and is never labelled like a clean match.
4. ``alias``         a small reviewed alias table (`ALIAS_GROUPS`) of known DK-vs-
                     nflverse spellings, applied under the same position constraint.
5. ``fuzzy``         same team AND compatible position only, and requires BOTH a high
                     similarity (``FUZZY_MIN``) AND a separation margin from the
                     runner-up (``FUZZY_MARGIN``).
6. ``ambiguous``     two or more candidates survive a step, or the fuzzy leader clears
                     the score bar but not the margin bar. Never resolved by guessing.
7. ``unmatched``     no candidate. Falls back to DK's season average.
8. ``dst``           team defense; there is no DST projection model.

`ambiguous` and `unmatched` are EXPLICIT fallback statuses and are never folded into a
generic "model" label. There is no "model" status any more -- the granular status is
the label -- so any downstream filter that wants "did this row use our projection?"
must ask `MODEL_STATUSES` / the `used_model` column.

FUZZY THRESHOLDS -- what the numbers actually show
--------------------------------------------------
`FUZZY_MIN = 0.88`, `FUZZY_MARGIN = 0.05`.

Measured on `projections_2025_week10.csv` (568 players), sweeping `FUZZY_MIN` over
{0.72, 0.80, 0.85, 0.88, 0.90, 0.94}:

  * leave-one-out false-match rate is **0/568 at every one of those thresholds**. It is
    the team+position pool, NOT the score bar, that kills all 150 legacy false matches.
    Do not credit 0.88 with that -- it is not what the data says.
  * recall (a perturbation harness that re-spells every one of the 568 names with a
    suffix / punctuation strip / upper-casing / one-character surname typo) is
    568/568 from 0.72 through 0.90, and drops to 567/568 at 0.94.

So 0.88 is chosen as the highest bar that still preserves full measured recall -- pure
defence in depth for slates whose noise is worse than this file's, not a fitted number.

`FUZZY_MARGIN` is likewise a guard, not a fitted value: the worst same-team,
same-position name collision in this file scores only 0.692 ("Tez Johnson" vs "Kameron
Johnson", TB WR), far under the score bar, so the margin rule never fires here. It
exists for the case this file happens not to contain -- one team rostering two players
whose names are both close to a DK spelling -- where the score alone cannot separate
them and guessing is the wrong answer.
"""
from __future__ import annotations

import difflib
import math
import re
from dataclasses import dataclass

import pandas as pd

__all__ = [
    "norm_name", "norm_team", "pos_class", "ALIAS_GROUPS", "ALIAS_CANON",
    "FUZZY_MIN", "FUZZY_MARGIN", "MODEL_STATUSES", "FALLBACK_STATUSES", "ALL_STATUSES",
    "Match", "ProjectionIndex", "match_row", "match_projections", "merge_projections",
    "match_status_counts", "format_match_report", "calc_dk_proj_pts",
    "assert_objective_finite", "loo_match_rate", "num",
]

# ── thresholds ─────────────────────────────────────────────────────────────────
FUZZY_MIN = 0.88      # minimum difflib ratio for the same-team/same-position leader
FUZZY_MARGIN = 0.05   # required separation between the leader and the runner-up

DK_ID_COLS = ("player_id", "gsis_id", "nfl_id", "nflverse_id")
PROJ_ID_COL = "player_id"

# ── name normalisation ────────────────────────────────────────────────────────
_SUFFIX_RE = re.compile(r"\s+(jr|sr|ii|iii|iv|v)$")
_DROP_RE = re.compile(r"[‘’'`\.,]")      # dropped outright
_SPACE_RE = re.compile(r"[-/]")           # become a space, so "Amon-Ra" == "Amon Ra"


def norm_name(name) -> str:
    """Lowercase, drop apostrophes/periods/commas, turn hyphens and slashes into spaces,
    drop generational suffixes. ``"T.J. Hockenson"`` and ``"TJ Hockenson"`` both become
    ``"tj hockenson"``; ``"Amon-Ra St. Brown"`` and ``"Amon Ra St Brown"`` both become
    ``"amon ra st brown"``; ``"Marvin Harrison Jr."`` and ``"Marvin Harrison"`` both
    become ``"marvin harrison"``.
    """
    if name is None or (isinstance(name, float) and math.isnan(name)):
        return ""
    s = _SPACE_RE.sub(" ", _DROP_RE.sub("", str(name).lower().strip()))
    s = re.sub(r"\s+", " ", s)
    prev = None
    while prev != s:                     # "Joe Milton III Jr" style stacking
        prev = s
        s = _SUFFIX_RE.sub("", s)
    return s.strip()


# ── team normalisation ────────────────────────────────────────────────────────
# DK, nflverse and PFR disagree on a handful of abbreviations. Canonical form is the
# nflverse code used by the projection files (verified against the 28 team codes in
# projections_2025_week10.csv: ... 'JAX', 'LA', 'LAC', 'LV', 'WAS' ...).
_TEAM_ALIASES = {
    "LAR": "LA", "STL": "LA", "RAM": "LA",
    "JAC": "JAX",
    "WSH": "WAS", "WFT": "WAS",
    "OAK": "LV", "LVR": "LV", "RAI": "LV",
    "SD": "LAC", "SDG": "LAC",
    "ARZ": "ARI",
    "BLT": "BAL",
    "CLV": "CLE",
    "HST": "HOU",
    "KAN": "KC",
    "GNB": "GB",
    "NWE": "NE",
    "NOR": "NO",
    "SFO": "SF",
    "TAM": "TB",
    "TEN": "TEN",
}


def norm_team(team) -> str:
    if team is None or (isinstance(team, float) and math.isnan(team)):
        return ""
    t = str(team).upper().strip()
    return _TEAM_ALIASES.get(t, t)


# ── position compatibility ────────────────────────────────────────────────────
# A DK slot label and an nflverse position are "compatible" only inside one of these
# classes. RB/FB/HB are one backfield class; everything else is its own class. This is
# what stops Josh Allen (QB) from ever being considered against Josh Palmer (WR).
_POS_CLASS = {
    "QB": "QB",
    "RB": "RB", "FB": "RB", "HB": "RB",
    "WR": "WR",
    "TE": "TE",
    "DST": "DST", "DEF": "DST", "D/ST": "DST", "DEFENSE": "DST",
    "K": "K", "PK": "K",
}


def pos_class(pos) -> str:
    if pos is None or (isinstance(pos, float) and math.isnan(pos)):
        return ""
    p = str(pos).upper().strip()
    return _POS_CLASS.get(p, p)


# ── reviewed alias table ──────────────────────────────────────────────────────
# Each group is a set of normalized names that refer to ONE player, i.e. a real
# DK-vs-nflverse spelling divergence. Entries are hand-reviewed, not generated. They
# are still applied under the position constraint, so an alias can never create a
# cross-position match. Keep this list SHORT: it is a correction table, not a
# similarity heuristic -- similarity is what step 5 is for.
ALIAS_GROUPS = [
    {"josh palmer", "joshua palmer"},                      # DK short / nflverse long
    {"gabe davis", "gabriel davis"},                       # nflverse flipped to "Gabe"
    {"tank dell", "nathaniel dell"},                       # nickname vs legal first name
    {"mitch trubisky", "mitchell trubisky"},               # DK short / nflverse long
    {"jeff wilson", "jeffery wilson"},                     # DK short / nflverse long
    {"cam ward", "cameron ward"},                          # DK short / nflverse long
    {"chig okonkwo", "chigoziem okonkwo"},                 # DK short / nflverse long
    {"hollywood brown", "marquise brown"},                 # nickname used by DK
    {"scotty miller", "scott miller"},                     # DK nickname
    {"nick westbrook ikhine", "nicholas westbrook ikhine"},  # DK short / nflverse long
    {"joe milton", "joseph milton"},                       # DK short / nflverse long
    {"chris rodriguez", "christopher rodriguez"},          # DK short / nflverse long
]

# name -> canonical group key (the alphabetically-first member of its group)
ALIAS_CANON: dict[str, str] = {}
for _g in ALIAS_GROUPS:
    _key = sorted(_g)[0]
    for _m in _g:
        ALIAS_CANON[_m] = _key


def _alias_key(n: str) -> str:
    return ALIAS_CANON.get(n, n)


# ── statuses ──────────────────────────────────────────────────────────────────
MODEL_STATUSES = ("id", "exact", "team_mismatch", "alias", "fuzzy")
FALLBACK_STATUSES = ("ambiguous", "unmatched", "dst")
ALL_STATUSES = MODEL_STATUSES + FALLBACK_STATUSES


@dataclass(frozen=True)
class Match:
    status: str
    proj_pos: int | None = None   # positional index into proj_df, or None
    score: float | None = None    # fuzzy similarity of the winner
    note: str = ""

    @property
    def used_model(self) -> bool:
        return self.status in MODEL_STATUSES


class ProjectionIndex:
    """Lookup structures over the projection frame, built once per merge."""

    def __init__(self, proj_df: pd.DataFrame, name_col: str = "player_display_name"):
        self.df = proj_df.reset_index(drop=True)
        self.name_col = name_col
        self.names = [norm_name(v) for v in self.df[name_col]]
        self.teams = [norm_team(v) for v in self.df.get("team", pd.Series([""] * len(self.df)))]
        self.poss = [pos_class(v) for v in self.df.get("position", pd.Series([""] * len(self.df)))]

        self.by_id: dict[str, list[int]] = {}
        if PROJ_ID_COL in self.df.columns:
            for i, v in enumerate(self.df[PROJ_ID_COL]):
                if pd.notna(v) and str(v).strip():
                    self.by_id.setdefault(str(v).strip(), []).append(i)

        self.by_name_pos_team: dict[tuple, list[int]] = {}
        self.by_name_pos: dict[tuple, list[int]] = {}
        self.by_alias_pos_team: dict[tuple, list[int]] = {}
        self.by_alias_pos: dict[tuple, list[int]] = {}
        self.by_team_pos: dict[tuple, list[int]] = {}
        for i, (n, p, t) in enumerate(zip(self.names, self.poss, self.teams)):
            self.by_name_pos_team.setdefault((n, p, t), []).append(i)
            self.by_name_pos.setdefault((n, p), []).append(i)
            a = _alias_key(n)
            self.by_alias_pos_team.setdefault((a, p, t), []).append(i)
            self.by_alias_pos.setdefault((a, p), []).append(i)
            self.by_team_pos.setdefault((t, p), []).append(i)


def _dk_id(row) -> str:
    for c in DK_ID_COLS:
        if c in row.index:
            v = row[c]
            if pd.notna(v) and str(v).strip():
                return str(v).strip()
    return ""


def match_row(row, idx: ProjectionIndex) -> Match:
    """Run the cascade for one DK row. `row` is a pandas Series."""
    pos = pos_class(row.get("position"))
    if pos == "DST":
        return Match("dst", note="no DST projection model")

    name = norm_name(row.get("name"))
    team = norm_team(row.get("team"))

    # 1 -- stable id on both sides
    pid = _dk_id(row)
    if pid and pid in idx.by_id:
        hits = idx.by_id[pid]
        if len(hits) == 1:
            return Match("id", hits[0], note=f"player_id {pid}")
        return Match("ambiguous", note=f"player_id {pid} appears {len(hits)}x in projections")

    # 2 -- exact normalized name, constrained by position AND team
    hits = idx.by_name_pos_team.get((name, pos, team), [])
    if len(hits) == 1:
        return Match("exact", hits[0], score=1.0)
    if len(hits) > 1:
        return Match("ambiguous", note=f"{len(hits)} projections share name+position+team")

    # 3 -- name+position unique league-wide but the teams disagree (trade / stale team)
    hits = idx.by_name_pos.get((name, pos), [])
    if len(hits) == 1:
        j = hits[0]
        return Match("team_mismatch", j, score=1.0,
                     note=f"DK team {team or '?'} != projection team {idx.teams[j] or '?'}")
    if len(hits) > 1:
        return Match("ambiguous",
                     note=f"{len(hits)} same-name {pos}s and DK team {team or '?'} matches none")

    # 4 -- reviewed alias table (position-constrained)
    akey = _alias_key(name)
    if akey != name or akey in ALIAS_CANON:
        hits = idx.by_alias_pos_team.get((akey, pos, team), [])
        if len(hits) == 1:
            return Match("alias", hits[0], score=1.0, note=f"alias group '{akey}'")
        if len(hits) > 1:
            return Match("ambiguous", note=f"alias '{akey}' hits {len(hits)} same-team rows")
        hits = idx.by_alias_pos.get((akey, pos), [])
        if len(hits) == 1:
            return Match("alias", hits[0], score=1.0,
                         note=f"alias group '{akey}' (team differs)")
        if len(hits) > 1:
            return Match("ambiguous", note=f"alias '{akey}' hits {len(hits)} rows")

    # 5 -- fuzzy, restricted to the same team AND compatible position
    pool = idx.by_team_pos.get((team, pos), [])
    if not pool:
        return Match("unmatched", note=f"no {pos} projections for team {team or '?'}")
    scored = sorted(
        ((difflib.SequenceMatcher(None, name, idx.names[j]).ratio(), j) for j in pool),
        key=lambda t: (-t[0], t[1]),
    )
    best, bj = scored[0]
    runner = scored[1][0] if len(scored) > 1 else 0.0
    if best < FUZZY_MIN:
        return Match("unmatched", score=round(best, 3),
                     note=f"best same-team {pos} candidate '{idx.names[bj]}' scored "
                          f"{best:.3f} < {FUZZY_MIN}")
    if best - runner < FUZZY_MARGIN:
        return Match("ambiguous", score=round(best, 3),
                     note=f"'{idx.names[bj]}' {best:.3f} vs runner-up "
                          f"'{idx.names[scored[1][1]]}' {runner:.3f}; margin < {FUZZY_MARGIN}")
    return Match("fuzzy", bj, score=round(best, 3), note=f"'{idx.names[bj]}' {best:.3f}")


def match_projections(dk_df: pd.DataFrame, proj_df: pd.DataFrame,
                      name_col: str = "player_display_name") -> list[Match]:
    idx = ProjectionIndex(proj_df, name_col=name_col)
    return [match_row(row, idx) for _, row in dk_df.iterrows()]


# ── numeric hygiene ───────────────────────────────────────────────────────────
def num(value, default: float = 0.0) -> float:
    """Coerce to float, mapping None / NaN / non-numeric to `default`.

    The old code used ``float(row.get("pred_wr_receptions") or 0)``. ``or`` does not
    catch NaN -- ``float('nan') or 0`` is ``nan``, because NaN is truthy -- so an
    unmatched row's NaN stat flowed all the way into the pulp objective coefficient.
    """
    if value is None:
        return default
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(f) or math.isinf(f) else f


# ── merge ─────────────────────────────────────────────────────────────────────
STAT_COLS = [
    "pred_qb_pass_yards", "pred_qb_rush_yards",
    "pred_rush_yards", "pred_rec_yards",
    "pred_wr_receptions", "pred_wr_rec_yards",
    "pred_te_receptions", "pred_te_rec_yards",
]


def merge_projections(dk_df: pd.DataFrame, proj_df: pd.DataFrame,
                      stat_cols: list[str] | None = None,
                      name_col: str = "player_display_name") -> pd.DataFrame:
    """Attach model projections to the DK pool through the constrained cascade.

    Adds: ``proj_pts``, ``match`` (granular status), ``used_model`` (bool),
    ``match_score``, ``match_name`` (the projection row actually used), ``match_note``,
    and the pulled-through stat columns. Rows that did NOT match fall back to DK's
    season average, exactly as before -- the difference is that they now say so.
    """
    stat_cols = [c for c in (stat_cols or STAT_COLS) if c in proj_df.columns]
    idx = ProjectionIndex(proj_df, name_col=name_col)

    pts, statuses, used, scores, mnames, notes = [], [], [], [], [], []
    stat_rows: dict[str, list] = {c: [] for c in stat_cols}

    for _, row in dk_df.iterrows():
        m = match_row(row, idx)
        statuses.append(m.status)
        used.append(m.used_model)
        scores.append(m.score)
        notes.append(m.note)
        if m.used_model and m.proj_pos is not None:
            prow = idx.df.iloc[m.proj_pos]
            pts.append(num(prow.get("projected_pts"), num(row.get("avg_pts"))))
            mnames.append(str(prow[name_col]))
            for c in stat_cols:
                stat_rows[c].append(prow.get(c))
        else:
            pts.append(num(row.get("avg_pts")))
            mnames.append("")
            for c in stat_cols:
                stat_rows[c].append(float("nan"))

    result = dk_df.drop(columns=["_norm"], errors="ignore").reset_index(drop=True).copy()
    result["proj_pts"] = pts
    result["match"] = statuses
    result["used_model"] = used
    result["match_score"] = scores
    result["match_name"] = mnames
    result["match_note"] = notes
    for c, vals in stat_rows.items():
        result[c] = vals
    result["value"] = (result["proj_pts"] / (result["salary"] / 1000)).round(2)
    return result


def match_status_counts(players: pd.DataFrame) -> dict[str, int]:
    vc = players["match"].value_counts().to_dict()
    return {s: int(vc.get(s, 0)) for s in ALL_STATUSES}


def format_match_report(players: pd.DataFrame) -> str:
    """Human-readable status breakdown printed BEFORE optimization."""
    counts = match_status_counts(players)
    n = len(players)
    skill = int((players["match"] != "dst").sum())
    modelled = int(players["used_model"].sum())
    lines = [f"=== Match status ({n} DK rows; {skill} skill-position) ==="]
    for s in ALL_STATUSES:
        lines.append(f"  {s:<14} {counts[s]:>4}")
    lines.append(f"  {'-- modelled':<14} {modelled:>4}  "
                 f"({modelled / skill:.1%} of skill rows)" if skill else "")
    bad = players[players["match"].isin(("ambiguous", "unmatched"))]
    if len(bad):
        lines.append(f"\n{len(bad)} row(s) fell back to DK season average "
                     f"(NOT our projection) -- review before locking a lineup:")
        cols = [c for c in ["position", "name", "team", "salary", "avg_pts", "match", "match_note"]
                if c in bad.columns]
        lines.append(bad[cols].to_string(index=False))
    else:
        lines.append("\nNo ambiguous or unmatched skill-position rows.")
    return "\n".join(x for x in lines if x)


# ── DK scoring ────────────────────────────────────────────────────────────────
def _norm_sf(threshold: float, mu: float, sigma: float) -> float:
    """P(X >= threshold) for X ~ Normal(mu, sigma) using stdlib math only."""
    return 0.5 * math.erfc((threshold - mu) / (sigma * math.sqrt(2)))


def calc_dk_proj_pts(players: pd.DataFrame) -> list[float]:
    """half-PPR ``projected_pts`` -> DraftKings Classic full-PPR + milestone bonuses.

    Every stat read goes through `num()`, so a NaN pulled from an unmatched row can
    never reach the objective. The result is guaranteed finite.
    """
    out = []
    for _, row in players.iterrows():
        pts = num(row.get("proj_pts"), num(row.get("avg_pts")))
        pos = pos_class(row.get("position"))

        if pos == "QB":
            mu_pass = num(row.get("pred_qb_pass_yards"))
            if mu_pass > 0:
                pts += _norm_sf(300, mu_pass, 65) * 3
        elif pos == "RB":
            mu_rush = num(row.get("pred_rush_yards"))
            mu_rec = num(row.get("pred_rec_yards"))
            if mu_rush > 0:
                pts += _norm_sf(100, mu_rush, 37) * 3
            if mu_rec > 0:
                pts += 0.5 * (mu_rec / 7.0)     # ~7 yds/rec estimate for RBs
        elif pos == "WR":
            pts += 0.5 * num(row.get("pred_wr_receptions"))
            mu_rec = num(row.get("pred_wr_rec_yards"))
            if mu_rec > 0:
                pts += _norm_sf(100, mu_rec, 28) * 3
        elif pos == "TE":
            pts += 0.5 * num(row.get("pred_te_receptions"))
            mu_rec = num(row.get("pred_te_rec_yards"))
            if mu_rec > 0:
                pts += _norm_sf(100, mu_rec, 22) * 3

        out.append(round(num(pts), 2))
    return out


def assert_objective_finite(players: pd.DataFrame, col: str = "dfs_proj_pts") -> None:
    """Fail loudly rather than hand a NaN coefficient to the ILP."""
    s = pd.to_numeric(players[col], errors="coerce")
    bad = players[s.isna() | ~pd.Series(s).apply(lambda v: math.isfinite(v) if pd.notna(v) else False)]
    if len(bad):
        names = ", ".join(str(x) for x in bad.get("name", bad.index)[:10])
        raise ValueError(f"{len(bad)} row(s) have a non-finite {col}: {names}")


# ── leave-one-out harness (used to derive/verify the thresholds) ───────────────
def loo_match_rate(proj_df: pd.DataFrame, matcher: str = "cascade",
                   name_col: str = "player_display_name") -> dict:
    """Drop each projection player in turn, then try to match a DK-style row for that
    absent player against the remaining pool. A match is by construction WRONG -- the
    player is not there. Returns counts + the wrong-match examples.

    `matcher="legacy"` reproduces the original unconstrained
    ``difflib.get_close_matches(cutoff=0.72)`` for the before/after comparison.
    """
    df = proj_df.reset_index(drop=True)
    names = [norm_name(v) for v in df[name_col]]
    n_total = len(df)
    matched = 0
    cross_pos = 0
    by_status: dict[str, int] = {}
    examples = []

    for i in range(n_total):
        keep = df.drop(index=i)
        row = pd.Series({
            "name": df.iloc[i][name_col],
            "position": df.iloc[i]["position"],
            "team": df.iloc[i].get("team"),
        })
        if matcher == "legacy":
            pool = [names[j] for j in range(n_total) if j != i]
            hits = difflib.get_close_matches(names[i], pool, n=1, cutoff=0.72)
            if hits:
                matched += 1
                j = next(j for j in range(n_total) if j != i and names[j] == hits[0])
                status = "model"
                wrong_pos = pos_class(df.iloc[j]["position"]) != pos_class(df.iloc[i]["position"])
            else:
                status, j, wrong_pos = "dk_avg", None, False
        else:
            idx = ProjectionIndex(keep, name_col=name_col)
            m = match_row(row, idx)
            status = m.status
            if m.used_model and m.proj_pos is not None:
                matched += 1
                orig_name = idx.df.iloc[m.proj_pos][name_col]
                j = next(k for k in range(n_total) if k != i
                         and df.iloc[k][name_col] == orig_name)
                wrong_pos = pos_class(df.iloc[j]["position"]) != pos_class(df.iloc[i]["position"])
            else:
                j, wrong_pos = None, False

        by_status[status] = by_status.get(status, 0) + 1
        if j is not None:
            cross_pos += int(wrong_pos)
            if len(examples) < 40:
                examples.append((
                    f"{df.iloc[i][name_col]} ({df.iloc[i]['position']}, {df.iloc[i].get('team')})",
                    f"{df.iloc[j][name_col]} ({df.iloc[j]['position']}, {df.iloc[j].get('team')})",
                    status,
                ))

    return {
        "n": n_total,
        "false_matches": matched,
        "rate": matched / n_total if n_total else 0.0,
        "cross_position": cross_pos,
        "by_status": by_status,
        "examples": examples,
    }
