"""Hermetic tests for the NFL odds client — no network."""
import math

import odds_client as oc


def _event():
    # Chiefs (home) favored; two books, median home spread -3.25, total 47.5
    return {
        "home_team": "Kansas City Chiefs", "away_team": "Buffalo Bills",
        "commence_time": "2026-09-13T17:00:00Z",
        "bookmakers": [
            {"key": "fanduel", "markets": [
                {"key": "spreads", "outcomes": [
                    {"name": "Kansas City Chiefs", "point": -3.0},
                    {"name": "Buffalo Bills", "point": 3.0}]},
                {"key": "totals", "outcomes": [
                    {"name": "Over", "point": 47.0}, {"name": "Under", "point": 47.0}]}]},
            {"key": "draftkings", "markets": [
                {"key": "spreads", "outcomes": [
                    {"name": "Kansas City Chiefs", "point": -3.5},
                    {"name": "Buffalo Bills", "point": 3.5}]},
                {"key": "totals", "outcomes": [
                    {"name": "Over", "point": 48.0}, {"name": "Under", "point": 48.0}]}]},
        ],
    }


def test_consensus_parsing():
    c = oc.consensus(_event(), min_books=2)
    assert c["home_team"] == "KC" and c["away_team"] == "BUF"
    # Odds API home points -3.0/-3.5 (home favored) -> negated to nflverse +3.25
    assert c["spread"] == 3.25
    assert c["total"] == 47.5       # median of 47, 48
    assert c["n_books"] == 2
    assert c["date"] == "2026-09-13"


def test_consensus_min_books_guard():
    assert oc.consensus(_event(), min_books=3) is None   # only 2 books in the fixture
    assert oc.consensus(_event(), min_books=2) is not None


def test_consensus_unknown_team_returns_none():
    ev = _event(); ev["home_team"] = "London Monarchs"
    assert oc.consensus(ev, min_books=1) is None


def test_pick_side():
    assert oc.pick_side("HOME (KC)") == "HOME"
    assert oc.pick_side("AWAY (BUF)") == "AWAY"
    assert oc.pick_side("PASS") is None


def test_clv_home_beats_close():
    # nflverse sign (positive = home favored). Pick home +3.0, closes +3.5 (home
    # more favored) -> you beat the close (+0.5).
    assert oc.clv_points(3.0, 3.5, "HOME") == 0.5
    assert oc.clv_points(3.0, 2.5, "HOME") == -0.5   # home less favored at close


def test_clv_away_beats_close():
    # away bettor beats the close when home becomes LESS favored (close < pick).
    assert oc.clv_points(3.0, 2.5, "AWAY") == 0.5
    assert oc.clv_points(3.0, 3.5, "AWAY") == -0.5


def test_clv_pass_is_nan():
    assert math.isnan(oc.clv_points(3.0, 3.5, "PASS"))


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")


# ---- review 2026-07-17 U4A-8 / U4A-9 -------------------------------------------
def test_clv_points_two_decimals():
    assert oc.clv_points(3.0, 3.25, "HOME") == 0.25    # was banker-rounded to 0.2
    assert oc.clv_points(3.25, 3.0, "AWAY") == 0.25


def test_consensus_totals_gated_on_own_book_count():
    spread_books = [{"key": f"s{i}", "markets": [{"key": "spreads", "outcomes": [
        {"name": "Atlanta Falcons", "point": -3.0},
        {"name": "Los Angeles Rams", "point": 3.0}]}]} for i in range(3)]
    totals_books = [{"key": "t1", "markets": [{"key": "totals", "outcomes": [
        {"name": "Over", "point": 44.5}, {"name": "Under", "point": 44.5}]}]},
                    {"key": "t2", "markets": [{"key": "totals", "outcomes": [
        {"name": "Over", "point": 45.0}, {"name": "Under", "point": 45.0}]}]}]
    ev = {"home_team": "Atlanta Falcons", "away_team": "Los Angeles Rams",
          "commence_time": "2026-09-13T17:00:00Z",
          "bookmakers": spread_books + totals_books}
    c = oc.consensus(ev)
    assert c is not None and c["spread"] == 3.0        # 3 spread books pass
    assert c["total"] is None and c["n_books_total"] == 2   # 2 totals books gated
