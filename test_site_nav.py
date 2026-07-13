"""Batch-1 proof for the multipage nav skeleton (app.py).

Asserts: the seasonal default lands on the right page on BOTH sides of SEASON_START
(env-forced), the sidebar renders EMPTY (nav is top, footer is in page flow), the
shared footer is present, and the shared modules are import-safe. Hermetic: APP_OFFLINE=1
so no network. Run: pytest test_site_nav.py
"""
import os
import sys
from pathlib import Path

os.environ["APP_OFFLINE"] = "1"   # set before importing streamlit-touching modules

from streamlit.testing.v1 import AppTest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
ENTRY = str(_HERE / "app.py")   # the multipage entrypoint (post-3e swap)


def _run(preseason: bool):
    # SEASON_START far future -> pre-season (board default); far past -> in-season (WP default)
    os.environ["BOARD_REFRESH_SEASON_START"] = "2099-01-01" if preseason else "2000-01-01"
    at = AppTest.from_file(ENTRY, default_timeout=180).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    return at


def _titles(at):
    return " ".join(str(t.value) for t in at.title)


def test_preseason_default_is_draft_board():
    at = _run(preseason=True)
    assert "Draft Board" in _titles(at), \
        f"pre-season should land on the Draft Board; titles={_titles(at)!r}"


def test_inseason_default_is_weekly_predictions():
    at = _run(preseason=False)
    # the real Weekly Predictions page titles "🏈 Week N Predictions: SEASON Season"
    # (only this page carries "Predictions"); the WP stub's literal title is gone.
    assert "Predictions" in _titles(at), \
        f"in-season should land on Weekly Predictions; titles={_titles(at)!r}"


def test_sidebar_is_empty_and_footer_present():
    at = _run(preseason=True)
    # nav is position="top"; nothing writes to the sidebar -> empty
    assert len(list(at.sidebar.markdown)) == 0, "sidebar must carry no markdown"
    assert not any(getattr(b, "key", None) == "tip_jar_btn" for b in at.sidebar.button), \
        "tip jar must NOT be in the sidebar"
    # footer is in the page flow: tip-jar button + the two footer captions
    assert any(getattr(b, "key", None) == "tip_jar_btn" for b in at.button), \
        "footer tip-jar button missing from page flow"
    caps = " ".join(str(c.value) for c in at.caption)
    assert "buy me a coffee" in caps, "footer tip-jar caption missing"
    assert "github.com/joscho11/BettingEdgeContinued" in caps, "footer repo link missing"


def test_shared_modules_import_safe():
    # importing the shared modules must not fire network/data work at import time
    import dashboard_data
    import dashboard_chrome
    for fn in ("load_predictions", "load_totals", "load_calibration"):
        assert hasattr(dashboard_data, fn)
    for fn in ("send_ga_event", "inject_css", "render_footer", "site_pageview_once"):
        assert hasattr(dashboard_chrome, fn)


if __name__ == "__main__":
    test_preseason_default_is_draft_board()
    test_inseason_default_is_weekly_predictions()
    test_sidebar_is_empty_and_footer_present()
    test_shared_modules_import_safe()
    print("OK  nav skeleton: seasonal default both sides, empty sidebar, footer present")
