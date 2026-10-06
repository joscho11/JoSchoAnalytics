"""Website team abbreviations. Rams display as LAR; stored codes stay LA."""
import pandas as pd

from team_display import public_matchup_text, public_team_abbr


def test_rams_public_abbreviation_is_lar_and_chargers_stay_lac():
    assert public_team_abbr("LA") == "LAR"
    assert public_team_abbr("LAR") == "LAR"
    assert public_team_abbr("LAC") == "LAC"
    assert public_team_abbr("SF") == "SF"
    assert public_team_abbr(None) == ""
    assert public_matchup_text("SF @ LA") == "SF @ LAR"
    assert public_matchup_text("SF@LA") == "SF@LAR"
    assert public_matchup_text("LAC at KC") == "LAC at KC"
    assert "LARAR" not in public_matchup_text("LAR")


def test_props_board_shows_lar_for_a_stored_la_code():
    import page_anytime_td as page

    rows = pd.DataFrame({
        "player_display_name": ["Kyren Williams"],
        "position": ["RB"],
        "team": ["LA"],
        "opponent_team": ["LAC"],
        "p_ge1": [0.40],
        "p_ge2": [0.08],
        "p_book": [0.30],
        "fair_amer": [150],
        "book_amer": [233],
        "scored_anytime": [None],
    })
    display = page._display(page.priced_rows(rows))
    assert display.loc[0, "Player"].endswith(" · LAR")
    assert display.loc[0, "Opp"] == "LAC"


def test_rookie_board_display_uses_lar():
    import page_rookie_board as board

    assert board.canon_team("LA") == "LAR"
    assert board.canon_team("LAR") == "LAR"
    assert board.canon_team("STL") == "LAR"
    assert board.canon_team("LAC") == "LAC"
    assert board.canon_team("NWE") == "NE"
    assert board.canon_team("SDG") == "LAC"
