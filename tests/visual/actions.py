"""Named Playwright actions for visual scenes that are not a plain GET."""
from __future__ import annotations

import re
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
    "dfs_upload_and_optimize": dfs_upload_and_optimize,
}


def run_action(page, name: str | None) -> None:
    if not name:
        return
    ACTIONS[name](page)
