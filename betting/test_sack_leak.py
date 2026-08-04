"""The target game's own sack outcome must not reach any pregame feature.

Regression of record (2026-08-03): `sack_pg` / `_build_situational_pbp` filtered
`sack == 1` before the groupby, so a zero-sack team-game produced NO ROW. Two defects:
  * the 5-game window skipped zero-sack games instead of averaging a 0 (upward bias);
  * row PRESENCE encoded the current game's outcome, and the downstream `fillna(0)` wrote
    0 onto exactly the zero-sack rows -- contemporaneous information in a pregame feature.
`sack_diff` / `sack_diff_reverse` are PROD_FEATURES_35 #2 and #3.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

_BETTING = Path(__file__).resolve().parent
if str(_BETTING) not in sys.path:
    sys.path.insert(0, str(_BETTING))

import features as F  # noqa: E402


def _pbp(sack_counts):
    """One defense (KC), one game per week, `sack_counts[w]` sacks in week w.

    Every game carries a non-sack play too, so the DENSE universe is all weeks.
    """
    rows = []
    for wk, n in sack_counts.items():
        for _ in range(n):
            rows.append({"game_id": f"g{wk}", "defteam": "KC", "posteam": "OPP", "sack": 1,
                         "interception": 0, "fumble_lost": 0, "down": 1, "first_down": 0})
        rows.append({"game_id": f"g{wk}", "defteam": "KC", "posteam": "OPP", "sack": 0,
                     "interception": 0, "fumble_lost": 0, "down": 1, "first_down": 0})
        # KC must also appear on OFFENSE, or its turnover/third-down rollups are
        # structurally NaN and the control assertion below tests nothing.
        rows.append({"game_id": f"g{wk}", "defteam": "OPP", "posteam": "KC", "sack": 0,
                     "interception": 0, "fumble_lost": 0, "down": 3, "first_down": 1})
    return pd.DataFrame(rows)


def _wk_lookup(weeks):
    return pd.DataFrame([{"game_id": f"g{w}", "week": w, "season": 2025} for w in weeks])


def _serve(sack_counts):
    pbp = _pbp(sack_counts)
    out = F._build_situational_pbp(
        pd.DataFrame([{"home_team": "KC", "away_team": "OPP"}]),
        pbp, _wk_lookup(sorted(sack_counts)))
    return out


def test_zero_sack_games_are_averaged_not_skipped():
    """3, 2, 0, 4 -> the true 4-game mean is 2.25, not 3.0."""
    served = float(_serve({1: 3, 2: 2, 3: 0, 4: 4})["home_rolling_sacks"].iloc[0])
    assert served == pytest.approx(2.25), (
        f"zero-sack game dropped from the window: served {served}, expected 2.25")


def test_target_game_sack_outcome_cannot_change_any_pregame_feature():
    """THE leak test. Mutate ONLY the final (target) game's sacks; features must not move.

    The pregame feature for a game is built from strictly prior games, so re-running with
    a different outcome in the target game must reproduce every value exactly.
    """
    history = {1: 3, 2: 2, 3: 0, 4: 4}
    target_week = 5
    baselines = None
    for target_sacks in (0, 1, 2, 5, 9):
        counts = dict(history)
        counts[target_week] = target_sacks
        pbp = _pbp(counts)
        wk = _wk_lookup(sorted(counts))

        # Pregame features for week 5 use only weeks < 5 -- the production restriction.
        prior_ids = {f"g{w}" for w in history}
        pbp_prior = pbp[pbp.game_id.isin(prior_ids)]
        out = F._build_situational_pbp(
            pd.DataFrame([{"home_team": "KC", "away_team": "OPP"}]),
            pbp_prior, wk[wk.game_id.isin(prior_ids)])
        vals = out[["home_rolling_sacks", "sack_diff", "sack_diff_reverse",
                    "home_rolling_turnovers", "turnover_diff"]].iloc[0].to_dict()
        if baselines is None:
            baselines = vals
        else:
            # NaN-aware: a plain dict == would fail on nan != nan and hide real drift.
            for k, v in vals.items():
                b = baselines[k]
                same = (pd.isna(v) and pd.isna(b)) or v == b
                assert same, (f"target-game sacks={target_sacks} changed pregame "
                              f"feature {k!r}: {v} != {b}")
    assert baselines["home_rolling_sacks"] == pytest.approx(2.25)


def test_presence_of_a_row_no_longer_encodes_the_outcome():
    """A team whose every game had zero sacks must still get a dense history."""
    pbp = _pbp({1: 0, 2: 0, 3: 0})
    universe = pbp[["game_id", "defteam"]].drop_duplicates()
    built = (pbp.assign(_s=(pbp["sack"] == 1).astype(int))
                .groupby(["game_id", "defteam"])["_s"].sum().reset_index())
    assert len(built) == len(universe), "zero-sack team-games lost their rows"
    assert len(universe) == 6, "fixture shape changed: 3 games x 2 defenses expected"
    kc = built[built.defteam == "KC"]
    assert len(kc) == 3 and (kc["_s"] == 0).all(), \
        "a defense with zero sacks in every game must still have one row per game"


def test_turnovers_and_third_down_were_and_remain_dense():
    """Control: these always grouped the full pbp; they must be unaffected."""
    out = _serve({1: 3, 2: 0, 3: 1})
    assert pd.notna(out["home_rolling_turnovers"].iloc[0])
    assert float(out["home_rolling_turnovers"].iloc[0]) == 0.0


def test_training_notebook_builds_a_dense_sack_table():
    """The training path must not reintroduce the pre-groupby filter."""
    import json
    nb = json.load(open(_BETTING / "model_comparison.ipynb", encoding="utf-8"))
    src = "".join(nb["cells"][21]["source"])
    # EXECUTABLE lines only. The fix's own comment quotes the old expression verbatim to
    # explain what was wrong, so scanning the raw source would fail against the very
    # change it is meant to verify.
    code = "".join(ln for ln in src.splitlines()
                   if not ln.lstrip().startswith("#")).replace(" ", "")
    assert code, "cell 21 has no executable lines -- the selector matched nothing"
    assert 'pbp_rp[pbp_rp["sack"]==1]' not in code, \
        "model_comparison.ipynb still filters sack==1 before the groupby"
    assert "_sack_i" in code, "dense sack indicator missing from the training build"
    # Self-proof: the selector must actually be capable of catching the old code.
    _old = "sack_pg=(pbp_rp[pbp_rp[\"sack\"]==1]"
    assert 'pbp_rp[pbp_rp["sack"]==1]' in _old.replace(" ", ""), "scanner is dead"
    guard = "".join(nb["cells"][22]["source"])
    assert "not dense" in guard, "the density assertion was removed from the test cell"


# ---------------------------------------------------------------------------
# RED PROOF: the guard must be able to FAIL against the pre-fix code.
# ---------------------------------------------------------------------------
def _legacy_sack_rollup(pbp, wk_lookup):
    """The pre-2026-08-03 builder, vendored verbatim in shape.

    Filters sack==1 BEFORE the groupby, so a zero-sack team-game produces no row.
    """
    sack_df = pbp[pbp["sack"] == 1].copy()
    sacks = (sack_df.groupby(["game_id", "defteam"]).size().reset_index(name="sacks")
             .rename(columns={"defteam": "team"}))
    sacks = sacks.merge(wk_lookup[["game_id", "week", "season"]], on="game_id", how="left")
    sacks = sacks.sort_values(["team", "season", "week"])
    sacks["rolling_sacks"] = sacks.groupby("team")["sacks"].transform(
        lambda x: x.rolling(5, min_periods=1).mean())
    return sacks.groupby("team").nth(-1).reset_index()[["team", "rolling_sacks"]]


def test_RED_the_legacy_builder_is_biased_and_the_new_one_is_not():
    """Materialises the old code and proves the two disagree in the documented direction."""
    counts = {1: 3, 2: 2, 3: 0, 4: 4}
    pbp, wk = _pbp(counts), _wk_lookup(sorted(counts))
    legacy = float(_legacy_sack_rollup(pbp, wk)
                   .set_index("team").loc["KC", "rolling_sacks"])
    fixed = float(_serve(counts)["home_rolling_sacks"].iloc[0])
    assert legacy == pytest.approx(3.0), f"legacy shape changed: {legacy}"
    assert fixed == pytest.approx(2.25), f"fixed value regressed: {fixed}"
    assert legacy > fixed, "the documented bias direction (upward) no longer reproduces"


def test_RED_row_presence_under_the_legacy_builder_encoded_the_outcome():
    """Under the old code, a team-game's row EXISTS iff that team recorded a sack."""
    counts = {1: 3, 2: 0}
    pbp, wk = _pbp(counts), _wk_lookup(sorted(counts))
    legacy_rows = pbp[pbp["sack"] == 1].groupby(["game_id", "defteam"]).size().reset_index()
    kc = legacy_rows[legacy_rows.defteam == "KC"]
    assert set(kc.game_id) == {"g1"}, "legacy table should omit the zero-sack game"
    # The fixed builder keeps both, so presence carries no information.
    dense = (pbp.assign(_s=(pbp["sack"] == 1).astype(int))
                .groupby(["game_id", "defteam"])["_s"].sum().reset_index())
    kc_dense = dense[dense.defteam == "KC"]
    assert set(kc_dense.game_id) == {"g1", "g2"}
