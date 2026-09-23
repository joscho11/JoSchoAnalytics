"""Proof for the multipage navigation and shared chrome (app.py).

Asserts: the default landing page is Home, Betting sits left of
Fantasy in the top nav, the sidebar renders EMPTY (nav is top, footer is in page
flow), the shared footer is present, and the shared modules are import-safe.
Hermetic: APP_OFFLINE=1 so no network. Run: pytest test_site_nav.py
"""
import ast
import json
import os
import sys
from pathlib import Path

os.environ["APP_OFFLINE"] = "1"   # set before importing streamlit-touching modules

from streamlit.testing.v1 import AppTest

_HERE = Path(__file__).resolve().parents[1]
_SITE_PAGES = _HERE / "site_pages"
sys.path.insert(0, str(_HERE))
ENTRY = str(_HERE / "app.py")   # the multipage entrypoint (post-3e swap)
PAGE_MODULES = (
    "page_home",
    "page_this_week",
    "page_weekly_predictions",
    "page_track_record",
    "page_draft_board",
    "page_rookie_board",
    "page_weekly_fantasy",
    "page_dfs",
    "page_anytime_td",
    "page_film_room",
    "page_league_history",
    "page_help",
    "page_futures",
    "page_cbb_daily",
)


def _run():
    at = AppTest.from_file(ENTRY, default_timeout=180).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    return at


def _titles(at):
    return " ".join(str(t.value) for t in at.title)


def test_default_is_home():
    at = _run()
    titles = _titles(at)
    assert "JoScho Analytics" in titles, \
        f"default landing page should be Home; titles={titles!r}"
    assert "Weekly predictions" not in titles, \
        f"Weekly Predictions must not be the default; titles={titles!r}"
    md = " ".join(str(m.value) for m in at.markdown)
    # Copy widened from "anytime TDs" once 2+ TD and First TD markets shipped.
    assert "Compare touchdown props" in md
    links = " ".join(
        str(getattr(link, "label", "")) for link in at.get("page_link")
    )
    assert "DFS Optimizer" in links


def test_nav_groups_betting_then_fantasy():
    src = Path(ENTRY).read_text(encoding="utf-8")
    assert src.index('"Betting"') < src.index('"Fantasy"'), \
        "Betting must sit left of Fantasy in the top nav"
    assert 'title="Home"' in src
    assert 'url_path="", default=True' in src
    assert "url_path=\"draft-board\", default=True" not in src
    assert "url_path=\"weekly-predictions\", default=True" not in src
    assert 'url_path="college-basketball"' in src
    assert src.index('"Fantasy"') < src.index('"College Basketball"') < src.index('"More"')


def test_college_basketball_has_exactly_one_page():
    src = Path(ENTRY).read_text(encoding="utf-8")
    group = src.split('"College Basketball":', 1)[1].split('],', 1)[0]
    assert group.count("cbb_pg") == 1
    assert '_lazy_render("page_cbb_daily")' in src


def test_sidebar_is_empty_and_footer_present():
    at = _run()
    # nav is position="top"; nothing writes to the sidebar -> empty
    assert len(list(at.sidebar.markdown)) == 0, "sidebar must carry no markdown"
    caps = " ".join(str(c.value) for c in at.caption)
    assert "checked release artifacts" in caps, "footer disclosure missing"
    src = (_HERE / "dashboard_chrome.py").read_text(encoding="utf-8")
    assert '"View public code"' in src and '"Support via Venmo"' in src


def test_header_has_brand_and_venmo_link():
    at = _run()
    # The user's preferred Venmo support link stays in the persistent header.
    hdr = [str(m.value) for m in at.markdown
           if "jsa-brand" in str(m.value) and "JoScho Analytics" in str(m.value)]
    assert hdr, "header brand must render on the page"
    assert "https://venmo.com/u/JoScho" in hdr[0], "header Venmo link missing"
    assert "Tip Jar — Venmo @JoScho" in hdr[0], "header Venmo label changed"
    assert 'aria-label="Support JoScho Analytics via Venmo"' in hdr[0]


def test_phone_nav_button_is_three_bars():
    src = (_HERE / "dashboard_chrome.py").read_text(encoding="utf-8")
    assert "[data-testid=\"stExpandSidebarButton\"]::after" in src
    assert "[data-testid=\"stSidebarCollapseButton\"]::after" in src
    assert "box-shadow:0 -.35rem 0 #fafafa, 0 .35rem 0 #fafafa" in src


def test_links_keep_a_non_color_affordance():
    config = (_HERE / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    skin = (_HERE / "theme_redesign.py").read_text(encoding="utf-8")
    assert "linkUnderline = true" in config
    assert "text-decoration:underline" in skin


def test_shared_modules_import_safe():
    # importing the shared modules must not fire network/data work at import time
    import dashboard_data
    import dashboard_chrome
    for fn in ("load_predictions", "load_totals", "load_calibration"):
        assert hasattr(dashboard_data, fn)
    for fn in ("send_ga_event", "inject_css", "render_header", "render_footer",
               "site_pageview", "site_pageview_once"):
        assert hasattr(dashboard_chrome, fn)


def test_page_analytics_are_route_specific_and_deduplicated(tmp_path):
    harness = tmp_path / "analytics_routes.py"
    harness.write_text(
        f"import sys; sys.path.insert(0, r'{_HERE}')\n"
        "import streamlit as st\n"
        "import dashboard_chrome as c\n"
        "events = []\n"
        "c.send_ga_event = lambda name, extra_params=None: events.append([name, extra_params])\n"
        "st.query_params['private_filter'] = 'never-log-this'\n"
        "c.site_pageview('Home', '')\n"
        "c.site_pageview('Home', '')\n"
        "c.site_pageview('Draft Board', 'draft-board')\n"
        "st.json(events)\n",
        encoding="utf-8",
    )
    at = AppTest.from_file(str(harness)).run()
    assert not at.exception, at.exception
    events = json.loads(at.json[0].value)
    assert [event[0] for event in events] == ["page_view", "page_view"]
    assert [event[1]["page_path"] for event in events] == ["/", "/draft-board"]
    assert "private_filter" not in json.dumps(events)


def test_dfs_is_available_in_the_public_fantasy_nav():
    src = Path(ENTRY).read_text(encoding="utf-8")
    assert '_lazy_render("page_dfs")' in src
    assert (_HERE / "site_pages" / "page_dfs.py").is_file()
    wheel = _HERE / "vendor" / "jsa_dfs_optimizer-0.2.3-py3-none-any.whl"
    assert wheel.is_file() and wheel.stat().st_size > 0
    req = (_HERE / "requirements.txt").read_text(encoding="utf-8")
    assert "./vendor/jsa_dfs_optimizer-0.2.3-py3-none-any.whl" in req
    fantasy = src.split('"Fantasy":', 1)[1].split("]", 1)[0]
    assert "dfs_pg" in fantasy
    assert "wf_pg" in fantasy
    assert fantasy.index("wf_pg") < fantasy.index("dfs_pg")
    assert fantasy.index("dfs_pg") < fantasy.index("board_pg")
    betting = src.split('"Betting":', 1)[1].split("]", 1)[0]
    assert "atd_pg" in betting


def test_nonselected_pages_are_lazy_imported():
    tree = ast.parse(Path(ENTRY).read_text(encoding="utf-8"))
    eager_imports = {
        alias.name
        for node in tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name.startswith("page_")
    }
    assert eager_imports == set()


def test_cloud_refresh_reloads_seasonal_config_before_pages():
    src = Path(ENTRY).read_text(encoding="utf-8")
    assert src.index('"live_2026"') < src.index("site_pages = "), (
        "Cloud must reload live_2026 before Weekly Predictions imports its current constants"
    )
    assert src.index('"seasonal_config"') < src.index("site_pages = "), (
        "Cloud must reload seasonal_config before site_pages or Home "
        "ImportErrors on app_today"
    )


def test_stale_seasonal_config_reload_restores_app_today():
    import page_common
    import seasonal_config

    seasonal_config.__joscho_source_mtime_ns__ = 0
    del seasonal_config.app_today
    try:
        refreshed = page_common.reload_if_stale(sys.modules["seasonal_config"])
        sys.modules["seasonal_config"] = refreshed
        assert callable(refreshed.app_today)
        import page_draft_board
        page_draft_board.__joscho_source_mtime_ns__ = 0
        page_common.reload_if_stale(sys.modules["page_draft_board"])
    finally:
        import importlib
        sys.modules["seasonal_config"] = importlib.reload(
            sys.modules["seasonal_config"]
        )


def test_every_page_renders_offline_clean(tmp_path):
    for module in PAGE_MODULES:
        harness = tmp_path / f"h_{module}.py"
        harness.write_text(
            f"import sys; sys.path[:0] = [r'{_HERE}', r'{_SITE_PAGES}']\n"
            f"import {module} as page\npage.render()\n",
            encoding="utf-8",
        )
        at = AppTest.from_file(str(harness), default_timeout=180).run()
        assert not at.exception, f"{module}: {at.exception}"
        assert not at.error, f"{module}: {[error.value for error in at.error]}"


if __name__ == "__main__":
    test_default_is_home()
    test_nav_groups_betting_then_fantasy()
    test_sidebar_is_empty_and_footer_present()
    test_header_has_brand_and_venmo_link()
    test_phone_nav_button_is_three_bars()
    test_shared_modules_import_safe()
    test_nonselected_pages_are_lazy_imported()
    print("OK  nav: Home default, Betting then Fantasy, empty sidebar, Venmo header, footer actions")
