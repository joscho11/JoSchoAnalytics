"""Named Playwright actions for visual scenes that are not a plain GET."""
from __future__ import annotations

import re
import time
from pathlib import Path

from playwright_support import wait_for_app

_REPO = Path(__file__).resolve().parents[2]
_DFS_SALARY = _REPO / "tests" / "fixtures" / "optimizer" / "dk_salaries.csv"
_DFS_PROJ = _REPO / "tests" / "fixtures" / "optimizer" / "direct_dk_projections.csv"
FIXTURE_LEAGUE_ID = "1255197436951932928"
OFFLINE_LEAGUE_ID = "111111111111111111"


def _click_option(page, label: str) -> None:
    """Streamlit segmented controls flip between button, radio, and button-group."""
    pattern = re.compile(rf"^{re.escape(label)}$")
    for role in ("radio", "button", "tab"):
        loc = page.get_by_role(role, name=pattern)
        if loc.count():
            loc.first.click()
            wait_for_app(page)
            return
    group = page.locator('[data-testid="stButtonGroup"]').filter(has_text=label)
    if group.count():
        group.first.get_by_text(label, exact=True).click()
        wait_for_app(page)
        return
    page.get_by_text(label, exact=True).first.click()
    wait_for_app(page)


def _click_segment(page, label: str) -> None:
    _click_option(page, label)


def _fill_labeled(page, label: str, value: str) -> None:
    page.get_by_role("textbox", name=label, exact=True).fill(value)


def _open_tab(page, name: str) -> None:
    pattern = re.compile(re.escape(name))
    tab = page.get_by_role("tab", name=pattern)
    if tab.count():
        tab.first.click()
    else:
        page.get_by_text(name, exact=False).first.click()
    wait_for_app(page)


def lh_espn(page) -> None:
    _click_segment(page, "ESPN")


def lh_espn_private(page) -> None:
    lh_espn(page)
    _click_segment(page, "Private")


def lh_yahoo(page) -> None:
    _click_segment(page, "Yahoo")


def lh_yahoo_private(page) -> None:
    lh_yahoo(page)
    _click_segment(page, "Private")


def lh_offline_error(page) -> None:
    _fill_labeled(page, "Sleeper League ID", OFFLINE_LEAGUE_ID)
    page.get_by_role("button", name="Load league history").click()
    wait_for_app(page)


def lh_load_fixture(page) -> None:
    _fill_labeled(page, "Sleeper League ID", FIXTURE_LEAGUE_ID)
    page.get_by_role("button", name="Load league history").click()
    page.get_by_text("Test League", exact=True).wait_for(timeout=30_000)
    wait_for_app(page)


def lh_tab_leaderboard(page) -> None:
    lh_load_fixture(page)
    _open_tab(page, "All-Time Leaderboard")


def lh_tab_hof(page) -> None:
    lh_load_fixture(page)
    _open_tab(page, "Hall of Fame")


def lh_tab_rivalries(page) -> None:
    lh_load_fixture(page)
    _open_tab(page, "Rivalries")


def lh_tab_report_cards(page) -> None:
    lh_load_fixture(page)
    _open_tab(page, "Report Cards")


def lh_tab_consistency(page) -> None:
    lh_load_fixture(page)
    _open_tab(page, "Consistency & Luck")


def lh_insights_best_values(page) -> None:
    lh_load_fixture(page)
    _click_segment(page, "Best Values")


def lh_insights_draft_room(page) -> None:
    lh_load_fixture(page)
    _click_segment(page, "Draft Room")


def help_open_ats(page) -> None:
    pattern = re.compile(r"What do spread, favorite, underdog, cover, and push mean\?")
    loc = page.get_by_role("button", name=pattern)
    if loc.count():
        loc.first.click()
    else:
        page.get_by_text(pattern).first.click()
    wait_for_app(page)


def help_scroll_models(page) -> None:
    page.get_by_text("Models & Data", exact=True).click()
    wait_for_app(page)
    page.get_by_text("How do the product-specific models work?", exact=True).click()
    wait_for_app(page)
    page.get_by_text("How the models work", exact=True).scroll_into_view_if_needed()
    wait_for_app(page)


def atd_first_td_view(page) -> None:
    _click_segment(page, "First TD")


def atd_two_plus_view(page) -> None:
    _click_segment(page, "2+ TD")


def atd_select_week06_matchup(page, market: str, matchup: str) -> None:
    _click_segment(page, market)
    combo = page.get_by_role("combobox", name="Matchup")
    if market != "Anytime TD":
        # The 2+ TD / First TD picker replaces the Anytime one on the next rerun and
        # starts on Recommended or All results. Wait for it, or a slow runner drives
        # the stale Anytime picker and the new one then resets the choice.
        def picker_value():
            try:
                return combo.input_value(timeout=1_500)
            except Exception:  # the picker is briefly absent while the page reruns
                return None

        deadline = time.monotonic() + 30
        while picker_value() not in ("Recommended", "All results") and time.monotonic() < deadline:
            page.wait_for_timeout(250)
    combo.click()
    combo.press("ArrowDown")
    combo.fill(matchup)
    combo.press("ArrowDown")
    combo.press("Enter")
    wait_for_app(page)
    assert combo.input_value() == matchup, f"Expected {matchup}, got {combo.input_value()}"


def dfs_upload_and_optimize(page) -> None:
    uploaders = page.locator('[data-testid="stFileUploader"] input[type="file"]')
    uploaders.nth(0).set_input_files(str(_DFS_SALARY))
    wait_for_app(page)
    page.get_by_text("Salary slate accepted", exact=False).wait_for(timeout=30_000)
    uploaders = page.locator('[data-testid="stFileUploader"] input[type="file"]')
    uploaders.nth(1).set_input_files(str(_DFS_PROJ))
    wait_for_app(page)
    page.get_by_role("button", name="Optimize lineup").click()
    page.get_by_text("Optimized lineup", exact=True).wait_for(timeout=30_000)
    wait_for_app(page)


ACTIONS = {
    "lh_espn": lh_espn,
    "lh_espn_private": lh_espn_private,
    "lh_yahoo": lh_yahoo,
    "lh_yahoo_private": lh_yahoo_private,
    "lh_offline_error": lh_offline_error,
    "lh_load_fixture": lh_load_fixture,
    "lh_tab_leaderboard": lh_tab_leaderboard,
    "lh_tab_hof": lh_tab_hof,
    "lh_tab_rivalries": lh_tab_rivalries,
    "lh_tab_report_cards": lh_tab_report_cards,
    "lh_tab_consistency": lh_tab_consistency,
    "lh_insights_best_values": lh_insights_best_values,
    "lh_insights_draft_room": lh_insights_draft_room,
    "help_open_ats": help_open_ats,
    "help_scroll_models": help_scroll_models,
    "atd_first_td_view": atd_first_td_view,
    "atd_two_plus_view": atd_two_plus_view,
    "dfs_upload_and_optimize": dfs_upload_and_optimize,
}

_W06_MATCHUP_VIEWS = {
    "atd_w06_anytime_ari_lar": ("Anytime TD", "ARI vs LAR"),
    "atd_w06_first_ari_lar": ("First TD", "ARI vs LAR"),
    "atd_w06_two_plus_ari_lar": ("2+ TD", "ARI vs LAR"),
    "atd_w06_anytime_buf_lv": ("Anytime TD", "BUF vs LV"),
    "atd_w06_first_buf_lv": ("First TD", "BUF vs LV"),
    "atd_w06_two_plus_buf_lv": ("2+ TD", "BUF vs LV"),
}
# Week 7 is the first board under the First TD v3 rule; the picker is the same combobox.
_W07_MATCHUP_VIEWS = {
    "atd_w07_first_cin_bal": ("First TD", "CIN vs BAL"),
}
_W06_MATCHUP_VIEWS = {**_W06_MATCHUP_VIEWS, **_W07_MATCHUP_VIEWS}
for _name, (_market, _matchup) in _W06_MATCHUP_VIEWS.items():
    ACTIONS[_name] = (
        lambda page, market=_market, matchup=_matchup:
            atd_select_week06_matchup(page, market, matchup)
    )


def run_action(page, name: str | None) -> None:
    if not name:
        return
    ACTIONS[name](page)
