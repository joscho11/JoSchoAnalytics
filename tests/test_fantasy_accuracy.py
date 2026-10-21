"""Postgame ranking accuracy: hand-checked definitions, plus a guard on every real graded week."""
import math
import os
import sys
from pathlib import Path

os.environ["APP_OFFLINE"] = "1"

import pandas as pd
import pytest

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE / "site_pages"))

import fantasy_accuracy as fa


def _frame(position, rows):
    """rows are (player_id, projected_pts, slp_proj, actual_half_ppr)."""
    return pd.DataFrame(
        [(pid, position, proj, slp, actual) for pid, proj, slp, actual in rows],
        columns=list(fa.REQUIRED_COLUMNS),
    )


NAN = float("nan")
# Five QBs. Our order a, b, c, d, e. Sleeper's order b, a, c, d (no projection for e).
# Finish order a, c, d, b, e.
QBS = _frame("QB", [
    ("a", 20, 18, 25), ("b", 18, 21, 10), ("c", 15, 14, 16),
    ("d", 10, 12, 12), ("e", 5, NAN, 2),
])
RBS = _frame("RB", [
    ("r1", 12, 10, 14), ("r2", 9, 11, 3), ("r3", 7, 6, 9), ("r4", 2, 1, 0),
])


def test_constants_match_the_approved_definitions():
    assert fa.BOARD_TOP_N == {"QB": 24, "RB": 40, "WR": 40, "TE": 24}
    assert fa.HIT_K == {"QB": 12, "RB": 24, "WR": 24, "TE": 12}
    assert fa.REQUIRED_COLUMNS == (
        "player_id", "position", "projected_pts", "slp_proj", "actual_half_ppr",
    )


def test_rank_frame_ranks_within_position_with_ties():
    frame = pd.concat([
        _frame("QB", [
            ("a", 20, 18, 25), ("b", 18, 21, 10), ("c", 15, 14, 10), ("d", 10, 12, 12),
        ]),
        _frame("RB", [("r1", 10, NAN, 0), ("r2", 10, 9, 0), ("r3", 5, 6, 7)]),
    ], ignore_index=True)

    ranked = fa.rank_frame(frame).set_index("player_id")

    assert ranked["our_rank"].to_dict() == {
        "a": 1, "b": 2, "c": 3, "d": 4, "r1": 1, "r2": 2, "r3": 3,
    }
    # r1 and r2 tie at 10 and the earlier row wins; r1 has no Sleeper projection.
    assert ranked.loc[["a", "b", "c", "d"], "slp_rank"].to_dict() == {
        "a": 2, "b": 1, "c": 3, "d": 4,
    }
    assert ranked.loc[["r2", "r3"], "slp_rank"].to_dict() == {"r2": 1, "r3": 2}
    assert math.isnan(ranked.loc["r1", "slp_rank"])
    # Tied scores share the best rank: b and c both finish 3rd, r1 and r2 both 2nd.
    assert ranked["finish_rank"].to_dict() == {
        "a": 1, "b": 3, "c": 3, "d": 2, "r1": 2, "r2": 2, "r3": 1,
    }
    assert ranked["rank_delta"].to_dict() == {
        "a": 0, "b": -1, "c": 0, "d": 2, "r1": -1, "r2": 0, "r3": 2,
    }


def test_rank_frame_drops_rows_it_cannot_place():
    frame = pd.concat([
        _frame("QB", [("ok", 10, 9, 8), ("no-proj", NAN, 9, 8), ("no-actual", 10, 9, NAN)]),
        _frame("K", [("kicker", 8, 8, 8)]),
    ], ignore_index=True)

    assert fa.rank_frame(frame)["player_id"].tolist() == ["ok"]


@pytest.mark.parametrize("column", fa.REQUIRED_COLUMNS)
def test_missing_required_column_raises_value_error(column):
    with pytest.raises(ValueError, match=column):
        fa.rank_frame(QBS.drop(columns=[column]))
    ranked = fa.rank_frame(QBS)
    with pytest.raises(ValueError, match=column):
        fa.position_scorecard(ranked.drop(columns=[column]))


def test_position_scorecard_hand_checked_values():
    ranked = fa.rank_frame(QBS)

    row = fa.position_scorecard(ranked, hit_k={"QB": 2}, top_n={"QB": 3}).iloc[0]

    assert row["position"] == "QB"
    assert row["k"] == 2
    # Our top 2 are a, b and Sleeper's are b, a; only a finished in the actual top 2 (a, c).
    assert (row["our_hits"], row["slp_hits"]) == (1, 1)
    # The top 3 on either list is a, b, c and all three have a Sleeper projection.
    assert (row["n"], row["n_excluded"]) == (3, 0)
    assert row["our_mae"] == pytest.approx((5 + 8 + 1) / 3)
    assert row["slp_mae"] == pytest.approx((7 + 11 + 2) / 3)
    assert row["our_rho"] == pytest.approx(0.5)
    assert row["slp_rho"] == pytest.approx(-0.5)


def test_players_without_a_sleeper_projection_are_excluded_not_zeroed():
    ranked = fa.rank_frame(QBS)

    row = fa.position_scorecard(ranked, hit_k={"QB": 2}, top_n={"QB": 5}).iloc[0]

    # e is in our top 5 but has no Sleeper projection, so both lists skip him.
    assert (row["n"], row["n_excluded"]) == (4, 1)
    assert row["our_mae"] == pytest.approx((5 + 8 + 1 + 2) / 4)
    assert row["slp_mae"] == pytest.approx((7 + 11 + 2 + 0) / 4)
    assert row["our_rho"] == pytest.approx(0.4)
    assert row["slp_rho"] == pytest.approx(-0.2)


def test_all_row_sums_hits_pools_misses_and_weights_rank_correlation_by_n():
    ranked = fa.rank_frame(pd.concat([QBS, RBS], ignore_index=True))

    card = fa.position_scorecard(
        ranked, hit_k={"QB": 2, "RB": 1}, top_n={"QB": 3, "RB": 4},
    )

    assert card["position"].tolist() == ["QB", "RB", "All"]
    rb = card.iloc[1]
    assert (rb["k"], rb["our_hits"], rb["slp_hits"], rb["n"]) == (1, 1, 0, 4)
    assert rb["our_mae"] == pytest.approx(3.0)
    assert rb["slp_mae"] == pytest.approx(4.0)
    assert rb["our_rho"] == pytest.approx(0.8)
    assert rb["slp_rho"] == pytest.approx(0.4)

    total = card.iloc[2]
    assert (total["k"], total["our_hits"], total["slp_hits"]) == (3, 2, 1)
    assert (total["n"], total["n_excluded"]) == (7, 0)
    # Pooled over all seven rows, not the mean of the two positional averages.
    assert total["our_mae"] == pytest.approx((14 + 12) / 7)
    assert total["slp_mae"] == pytest.approx((20 + 16) / 7)
    assert total["our_rho"] == pytest.approx((3 * 0.5 + 4 * 0.8) / 7)
    assert total["slp_rho"] == pytest.approx((3 * -0.5 + 4 * 0.4) / 7)


def test_k_larger_than_the_position_pool_is_capped_at_the_pool():
    three = _frame("QB", [("a", 3, 3, 3), ("b", 2, 2, 2), ("c", 1, 1, 1)])

    row = fa.position_scorecard(fa.rank_frame(three)).iloc[0]

    assert row["k"] == 3
    assert (row["our_hits"], row["slp_hits"]) == (3, 3)


def test_rank_correlation_needs_at_least_three_players():
    two = _frame("QB", [("a", 3, 3, 3), ("b", 2, 2, 2)])

    row = fa.position_scorecard(fa.rank_frame(two)).iloc[0]

    assert row["n"] == 2
    assert math.isnan(row["our_rho"]) and math.isnan(row["slp_rho"])
    assert row["our_mae"] == pytest.approx(0.0)


def test_rank_correlation_is_pearson_on_average_ranks():
    # Ties in the actual points: Spearman uses average ranks, not arbitrary order.
    frame = _frame("QB", [
        ("a", 5, 5, 9), ("b", 4, 4, 9), ("c", 3, 3, 1), ("d", 2, 2, 0),
    ])

    row = fa.position_scorecard(
        fa.rank_frame(frame), hit_k={"QB": 2}, top_n={"QB": 4},
    ).iloc[0]

    # Projection ranks 4,3,2,1 and actual average ranks 3.5,3.5,2,1.
    xs, ys = [4, 3, 2, 1], [3.5, 3.5, 2, 1]
    mx, my = sum(xs) / 4, sum(ys) / 4
    expected = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(
        sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)
    )
    assert row["our_rho"] == pytest.approx(expected)


def test_position_scorecard_skips_positions_with_no_players():
    card = fa.position_scorecard(fa.rank_frame(QBS), hit_k={"QB": 2}, top_n={"QB": 3})

    assert card["position"].tolist() == ["QB", "All"]
    assert fa.position_scorecard(fa.rank_frame(QBS.iloc[0:0])).empty


def test_season_table_is_long_format_with_every_week_in_order():
    week_2 = pd.concat([QBS, RBS], ignore_index=True)
    week_1 = RBS

    table = fa.season_table([(2, week_2), (1, week_1)])

    assert list(table.columns) == ["week", *fa.SCORECARD_COLUMNS]
    assert table["week"].tolist() == [1, 1, 2, 2, 2]
    assert table["position"].tolist() == ["RB", "All", "QB", "RB", "All"]
    assert fa.season_table([]).empty
    with pytest.raises(ValueError, match="slp_proj"):
        fa.season_table([(3, week_1.drop(columns=["slp_proj"]))])


def test_scorecard_display_formats_hits_and_rounds_to_two_decimals():
    card = pd.DataFrame([{
        "position": "All", "k": 72, "our_hits": 39, "slp_hits": 36, "n": 141,
        "our_mae": 5.0187, "slp_mae": 5.346, "our_rho": 0.3445, "slp_rho": NAN,
        "n_excluded": 1,
    }])

    shown = fa.scorecard_display(card, label="Position", column="position").iloc[0]

    assert shown["Position"] == "All"
    assert (shown["Top-tier hits"], shown["Sleeper hits"]) == ("39 of 72", "36 of 72")
    assert (shown["Avg miss"], shown["Sleeper miss"]) == (5.02, 5.35)
    assert shown["Rank corr"] == 0.34
    assert math.isnan(shown["Sleeper corr"])


def test_phone_display_stacks_ours_then_sleeper_for_each_row():
    card = pd.DataFrame([
        {"week": 1, "position": "All", "k": 72, "our_hits": 36, "slp_hits": 37, "n": 153,
         "our_mae": 6.3147, "slp_mae": 6.2201, "our_rho": 0.2618, "slp_rho": 0.3975,
         "n_excluded": 0},
        {"week": 2, "position": "All", "k": 72, "our_hits": 36, "slp_hits": 38, "n": 152,
         "our_mae": 5.6113, "slp_mae": 5.9349, "our_rho": 0.3249, "slp_rho": 0.4098,
         "n_excluded": 1},
    ])

    shown = fa.scorecard_display_phone(card, label="Week", column="week")

    assert list(shown.columns) == ["Week", "Who", "Top-tier hits", "Avg miss", "Rank corr"]
    assert shown["Week"].tolist() == [1, 1, 2, 2]
    assert shown["Who"].tolist() == ["Ours", "Sleeper", "Ours", "Sleeper"]
    assert shown["Top-tier hits"].tolist() == ["36 of 72", "37 of 72", "36 of 72", "38 of 72"]
    assert shown["Avg miss"].tolist() == [6.31, 6.22, 5.61, 5.93]
    assert shown["Rank corr"].tolist() == [0.26, 0.40, 0.32, 0.41]

    # Newest week first, still ours before Sleeper's inside each week.
    latest = fa.scorecard_display_phone(card, label="Week", column="week", newest_first=True)
    assert latest["Week"].tolist() == [2, 2, 1, 1]
    assert latest["Who"].tolist() == ["Ours", "Sleeper", "Ours", "Sleeper"]
    assert latest["Rank corr"].tolist() == [0.32, 0.41, 0.26, 0.40]


def _card(rows):
    base = {"k": 12, "n": 40, "n_excluded": 0}
    return pd.DataFrame([{**base, **row} for row in rows])


def test_week_summary_counts_wins_by_the_numbers_on_screen():
    card = _card([
        # Wins hits, loses corr, wins miss.
        {"position": "QB", "our_hits": 8, "slp_hits": 7, "our_rho": 0.30, "slp_rho": 0.40,
         "our_mae": 5.0, "slp_mae": 5.5},
        # Level on hits, wins corr, level on miss (0.304 and 0.296 both show 0.30).
        {"position": "RB", "our_hits": 9, "slp_hits": 9, "our_rho": 0.50, "slp_rho": 0.40,
         "our_mae": 5.004, "slp_mae": 4.996},
        # Loses hits, loses corr, loses miss.
        {"position": "WR", "our_hits": 5, "slp_hits": 6, "our_rho": 0.10, "slp_rho": 0.20,
         "our_mae": 6.0, "slp_mae": 5.0},
        # No Sleeper numbers at all: not compared.
        {"position": "TE", "n": 0, "our_hits": 3, "slp_hits": 0, "our_rho": NAN,
         "slp_rho": NAN, "our_mae": NAN, "slp_mae": NAN},
        {"position": "All", "our_hits": 25, "slp_hits": 22, "our_rho": 0.3, "slp_rho": 0.3,
         "our_mae": 5.0, "slp_mae": 5.0},
    ])

    assert fa.week_summary(card) == (
        "We beat Sleeper on top-tier hits at 1 of 3 positions, "
        "on rank correlation at 1 of 3, and on average miss at 1 of 3."
    )
    assert fa.week_summary(card.iloc[[3, 4]]) == (
        "Sleeper's projections were not available to compare this week."
    )


def test_season_summary_reads_the_all_rows_and_pluralizes():
    table = _card([
        {"week": 1, "position": "QB", "our_hits": 9, "slp_hits": 1, "our_rho": 0.9,
         "slp_rho": 0.1, "our_mae": 1.0, "slp_mae": 9.0},
        {"week": 1, "position": "All", "our_hits": 40, "slp_hits": 38, "our_rho": 0.30,
         "slp_rho": 0.40, "our_mae": 5.0, "slp_mae": 5.5},
        {"week": 2, "position": "All", "our_hits": 40, "slp_hits": 41, "our_rho": 0.50,
         "slp_rho": 0.40, "our_mae": 5.0, "slp_mae": 4.5},
    ])

    assert fa.season_summary(table) == (
        "Over 2 graded weeks we beat Sleeper on top-tier hits in 1, "
        "on rank correlation in 1, and on average miss in 1."
    )
    assert fa.season_summary(table.iloc[[1]]).startswith("Over 1 graded week we beat")


def test_every_graded_2026_week_scores_all_four_positions():
    """Fails loudly if a future graded artifact drops slp_proj or actual_half_ppr."""
    import page_weekly_fantasy as weekly
    from publishing.manifest import published_builds, resolve_build_artifact

    graded = [
        build for build in published_builds("fantasy", root=_HERE)
        if int(build["season"]) == 2026 and (build.get("grading") or {}).get("complete")
    ]
    # Weeks 1-6 are final. Fewer means the manifest did not load, not that nothing is wrong.
    assert len(graded) >= 6

    for build in graded:
        path = resolve_build_artifact(build, root=_HERE, prefer_graded=True)
        frame = weekly._load_proj_csv(str(path))
        rows = weekly.eligible_board_rows(frame, 2026, int(build["week"]))
        card = fa.position_scorecard(fa.rank_frame(rows))
        assert card["position"].tolist() == [*fa.POSITIONS, fa.ALL_LABEL], build["build_id"]
        assert (card["n"] > 0).all(), build["build_id"]
        assert card["k"].tolist() == [*(fa.HIT_K[p] for p in fa.POSITIONS), 72], build["build_id"]
